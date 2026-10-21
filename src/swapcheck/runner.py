"""Runs (spec §4, §9.2, §9.3, §9.5, §10): warm-ups, fan-out under the concurrency and rate limits,
append-only item rows with resume, the in-run budget stop, finalization, the retry-errors pass and
run validity.

Pricing stays outside: callers pass `cost_fn` (usage → USD), `timeout_usage_fn` (item text → the
charge for a timed-out attempt) and `token_estimate_fn` (item text → rate-limit tokens).
"""

from __future__ import annotations

import asyncio
import gzip
import importlib.metadata
import io
import os
import platform
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from swapcheck.configs import Configuration
from swapcheck.data import Item, item_list_hash
from swapcheck.freeze import CONTRACT_TAG, GUARDED_SPLITS, check_freeze, head_commit
from swapcheck.http import Sender, SendResult
from swapcheck.manifest import ManifestRun, append_run
from swapcheck.prompt import Prompt
from swapcheck.providers.base import WARMUP_TEXT
from swapcheck.records import (
    ITEMS_FINAL,
    ITEMS_PLAIN,
    RUN_JSON,
    Attempt,
    ItemRow,
    RunMeta,
    RunTotals,
    Split,
    Usage,
    Warmup,
    read_meta,
    read_rows,
)
from swapcheck.schema import schema_sha256

CONCURRENCY = 16  # spec §4
MAX_RAW_OUTPUT_CHARS = 2_000  # LLMs only; Jev keeps the full response JSON (spec §10)
STATUSES = ("ok", "invalid_output", "api_error")
MAX_API_ERROR_RATE = (5, 1000)  # 0.5 %, compared exactly in integers (spec §9.2)

CostFn = Callable[[Usage], float]
TimeoutUsageFn = Callable[[str], Usage]
TokenEstimateFn = Callable[[str], int]


class RunnerError(RuntimeError):
    """A run cannot start, resume or be retried as asked."""


class BudgetExceeded(RunnerError):
    """Not even the first requests fit under the spend ceiling: the run does not start."""


@dataclass(frozen=True)
class RunBudget:
    """`spent_before_usd` is everything recorded before this invocation (all runs, including this run's
    earlier rows when resuming); requests stop once it plus this invocation's spend reaches the ceiling."""

    spent_before_usd: float
    ceiling_usd: float
    reason: str = "spend ceiling"  # becomes `incomplete_reason`


@dataclass
class _Ledger:
    budget: RunBudget
    cost_fn: CostFn
    spent: float = 0.0
    reserved: float = 0.0  # worst-case single attempt of every request in flight

    def charge(self, attempts: Sequence[Attempt]) -> None:
        self.spent += sum(self.cost_fn(a.usage) for a in attempts)

    def fits(self, reserve: float) -> bool:
        total = self.budget.spent_before_usd + self.spent + self.reserved
        return total < self.budget.ceiling_usd and total + reserve <= self.budget.ceiling_usd


@dataclass(frozen=True)
class _Requests:
    cfg: Configuration
    prompt: Prompt
    sender: Sender
    cost_fn: CostFn
    timeout_usage_fn: TimeoutUsageFn
    token_estimate_fn: TokenEstimateFn

    def reserve(self, text: str) -> float:
        """Conservative charge held for an in-flight request: one timed-out attempt (full input + max output)."""
        return self.cost_fn(self.timeout_usage_fn(text))

    async def send(self, text: str, cache_key: str | None) -> SendResult:
        adapter = self.sender.adapter
        request = adapter.build_request(self.cfg, self.prompt, text, cache_key)
        return await self.sender.send(
            request,
            tokens=self.token_estimate_fn(text),
            parse=lambda body: adapter.parse_response(self.cfg, self.prompt, body),
            timeout_usage=lambda: self.timeout_usage_fn(text),
        )

    async def item_row(self, item: Item, earlier: Sequence[Attempt] = ()) -> ItemRow:
        result = await self.send(item.text, self.sender.adapter.cache_key(self.cfg, item.digest))
        return _row(self.cfg, item.item_id, result, earlier)


def default_run_id(config_id: str, split: str, now: datetime) -> str:
    return f"{config_id}-{split}-{now.astimezone(UTC):%Y%m%dT%H%M%SZ}"


def _timestamp(now: datetime) -> str:
    return f"{now.astimezone(UTC):%Y-%m-%dT%H:%M:%SZ}"


def _row(cfg: Configuration, item_id: str, result: SendResult, earlier: Sequence[Attempt]) -> ItemRow:
    attempts = [*earlier, *(a.model_copy(update={"number": len(earlier) + a.number}) for a in result.attempts)]
    final = result.final
    parsed = result.parsed
    if parsed is None:
        return ItemRow(
            item_id=item_id,
            status="api_error",
            error_code=result.error_code,
            stop_reason=None,
            raw_output=result.error_body,
            intent=None,
            confidence=None,
            probabilities=None,
            match_probability=None,
            case_normalized=False,
            latency_ms=final.latency_ms,
            request_id=final.request_id,
            model_id=None,
            attempts=attempts,
        )
    raw = parsed.raw_output[:MAX_RAW_OUTPUT_CHARS] if cfg.is_llm else parsed.raw_output
    return ItemRow(
        item_id=item_id,
        status=parsed.status,
        error_code=parsed.error_code,
        stop_reason=parsed.stop_reason,
        raw_output=raw,
        intent=parsed.intent,
        confidence=parsed.confidence,
        probabilities=parsed.probabilities,
        match_probability=parsed.match_probability,
        case_normalized=parsed.case_normalized,
        latency_ms=final.latency_ms,
        request_id=final.request_id,
        model_id=parsed.model_id,
        attempts=attempts,
    )


def _totals(rows: Sequence[ItemRow], warmups: Sequence[Warmup], cost_fn: CostFn) -> RunTotals:
    attempts = [a for r in rows for a in r.attempts] + [a for w in warmups for a in w.attempts]
    reasoning = [a.usage.reasoning for a in attempts if a.usage.reasoning is not None]
    tokens = Usage(
        uncached_input=sum(a.usage.uncached_input for a in attempts),
        cache_read=sum(a.usage.cache_read for a in attempts),
        cache_write=sum(a.usage.cache_write for a in attempts),
        output=sum(a.usage.output for a in attempts),
        reasoning=sum(reasoning) if reasoning else None,
    )
    return RunTotals(
        by_status={s: sum(r.status == s for r in rows) for s in STATUSES},
        tokens=tokens,
        billed_usd=sum(cost_fn(a.usage) for a in attempts),
        case_normalized=sum(r.case_normalized for r in rows),
        n_429=sum(a.http_status == 429 for a in attempts),
    )


def _identity(cfg: Configuration, prompt: Prompt, split: Split, items: Sequence[Item]) -> dict[str, Any]:
    return {
        "config_id": cfg.id,
        "config_sha256": cfg.sha256(),
        "split": split,
        "item_list_sha256": item_list_hash(list(items)),
        "prompt_sha256": prompt.sha256(),
        "schema_sha256": schema_sha256(cfg, prompt),
        "requested_model": cfg.model,
    }


def _check_identity(meta: RunMeta, identity: dict[str, Any]) -> None:
    differing = [name for name, value in identity.items() if getattr(meta, name) != value]
    if differing:
        raise RunnerError(f"run {meta.run_id} was started with different {', '.join(differing)}")


def _versions(request_headers: dict[str, str]) -> dict[str, str]:
    versions = {
        "python": platform.python_version(),
        "httpx": httpx.__version__,
        "swapcheck": importlib.metadata.version("model-swap-check"),
    }
    # API version headers the adapter sends, e.g. `anthropic-version` (spec §10)
    versions.update({k.lower(): v for k, v in request_headers.items() if k.lower().endswith("-version")})
    return versions


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _write_meta(run_dir: Path, meta: RunMeta) -> None:
    _atomic_write(run_dir / RUN_JSON, (meta.model_dump_json(indent=2) + "\n").encode())


def _write_final_rows(run_dir: Path, rows: Sequence[ItemRow]) -> None:
    """Deterministic gzip (mtime 0, no file name): the same rows always give the same bytes."""
    data = "".join(r.model_dump_json() + "\n" for r in rows).encode()
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0) as gz:
        gz.write(data)
    _atomic_write(run_dir / ITEMS_FINAL, buf.getvalue())


def _drop_partial_line(path: Path) -> None:
    """A killed run can leave a partial last line; cut the file after its last newline."""
    data = path.read_bytes()
    end = data.rfind(b"\n") + 1
    if end != len(data):
        with path.open("r+b") as f:
            f.truncate(end)
            f.flush()
            os.fsync(f.fileno())


class _RowWriter:
    def __init__(self, path: Path) -> None:
        self._file = path.open("a", encoding="utf-8")

    def write(self, row: ItemRow) -> None:
        self._file.write(row.model_dump_json() + "\n")
        self._file.flush()
        os.fsync(self._file.fileno())

    def close(self) -> None:
        self._file.close()


async def _fan_out[T](
    work: Sequence[T],
    *,
    reserve_of: Callable[[T], float],
    process: Callable[[T], Awaitable[ItemRow]],
    on_row: Callable[[ItemRow], None],
    ledger: _Ledger,
    concurrency: int,
) -> bool:
    """Process `work` in order with at most `concurrency` in flight; before each start, stop if the
    budget no longer fits. Returns True when stopped for budget."""
    semaphore = asyncio.Semaphore(concurrency)

    async def worker(unit: T, reserve: float) -> None:
        try:
            row = await process(unit)
            ledger.charge(row.attempts)
            on_row(row)
        finally:
            ledger.reserved -= reserve
            semaphore.release()

    async with asyncio.TaskGroup() as group:
        for unit in work:
            await semaphore.acquire()
            reserve = reserve_of(unit)
            if not ledger.fits(reserve):
                semaphore.release()
                return True
            ledger.reserved += reserve
            group.create_task(worker(unit, reserve))
    return False


def _index(items: Sequence[Item]) -> dict[str, int]:
    index = {item.item_id: i for i, item in enumerate(items)}
    if len(index) != len(items):
        raise RunnerError("item IDs must be unique")
    return index


async def run(
    cfg: Configuration,
    prompt: Prompt,
    split: Split,
    items: Sequence[Item],
    *,
    sender: Sender,
    runs_dir: Path,
    repo_root: Path,
    cost_fn: CostFn,
    timeout_usage_fn: TimeoutUsageFn,
    token_estimate_fn: TokenEstimateFn,
    budget: RunBudget,
    run_id: str | None = None,
    contract_tag: str = CONTRACT_TAG,
    concurrency: int = CONCURRENCY,
) -> RunMeta:
    """Start or resume (same `run_id`) one run and finalize it. Returns the final `run.json` content.

    `cert`/`aa` runs pass the freeze guard and are recorded in `runs/manifest.yaml` first (spec §9.5).
    """
    if not 1 <= concurrency <= CONCURRENCY:
        raise ValueError(f"concurrency must be 1..{CONCURRENCY}")
    index = _index(items)
    requests = _Requests(cfg, prompt, sender, cost_fn, timeout_usage_fn, token_estimate_fn)
    adapter = sender.adapter
    run_id = run_id or default_run_id(cfg.id, split, sender.clock.now())
    run_dir = runs_dir / run_id
    identity = _identity(cfg, prompt, split, items)

    existing = read_meta(run_dir) if (run_dir / RUN_JSON).exists() else None
    if existing is not None:
        if existing.ended_at is not None:
            raise RunnerError(f"run {run_id} is already finalized; only a retry-errors pass may change it")
        _check_identity(existing, identity)
        if (run_dir / ITEMS_PLAIN).exists():
            # a finalize interrupted before run.json: until it completes, the plain file is the record
            (run_dir / ITEMS_FINAL).unlink(missing_ok=True)
    rows = read_rows(run_dir)
    unknown = {r.item_id for r in rows} - index.keys()
    if unknown:
        raise RunnerError(f"run {run_id} has rows for items outside the split, e.g. {sorted(unknown)[0]}")
    done = {r.item_id for r in rows}
    pending = [item for item in items if item.item_id not in done]

    ledger = _Ledger(budget, cost_fn)
    warmup_keys = adapter.warmup_cache_keys(cfg)
    if pending:
        first = sum(requests.reserve(WARMUP_TEXT) for _ in warmup_keys) + requests.reserve(pending[0].text)
        if not ledger.fits(first):
            raise BudgetExceeded(
                f"{cfg.id}: spent ${budget.spent_before_usd:.4f} leaves no room for the first requests "
                f"under the ${budget.ceiling_usd:.4f} ceiling"
            )

    contract_tag_commit: str | None = None
    if split in GUARDED_SPLITS:
        contract_tag_commit = check_freeze(repo_root, contract_tag)
        if existing is not None and existing.contract_tag_commit != contract_tag_commit:
            raise RunnerError(f"run {run_id} was started under another contract tag commit")
        manifest_fields = {k: v for k, v in identity.items() if k != "requested_model"}
        entry = ManifestRun(
            contract_tag=contract_tag, contract_tag_commit=contract_tag_commit, run_id=run_id, **manifest_fields
        )
        append_run(runs_dir, entry)

    run_dir.mkdir(parents=True, exist_ok=True)
    plain = run_dir / ITEMS_PLAIN
    if plain.exists():
        _drop_partial_line(plain)
    if existing is None:
        sample = adapter.build_request(cfg, prompt, WARMUP_TEXT, None)
        meta = RunMeta(
            run_id=run_id,
            **identity,
            returned_model_ids=[],
            versions=_versions(sample.headers),
            git_commit=head_commit(repo_root),
            contract_tag_commit=contract_tag_commit,
            warmups=[],
            started_at=_timestamp(sender.clock.now()),
            ended_at=None,
            complete=False,
            incomplete_reason=None,
            retry_errors_passes=0,
            retry_errors_rewritten=0,
            totals=_totals(rows, [], cost_fn),
        )
        _write_meta(run_dir, meta)
    else:
        meta = existing

    # Warm-ups (spec §4): one per cache key, all finished before the fan-out; a resume with items left warms again.
    async def warmup(key: str | None) -> Warmup:
        result = await requests.send(WARMUP_TEXT, key)
        ledger.charge(result.attempts)
        return Warmup(cache_key=key, attempts=result.attempts)

    if warmup_keys and pending:
        warmups = await asyncio.gather(*(warmup(key) for key in warmup_keys))
        meta = meta.model_copy(update={"warmups": [*meta.warmups, *warmups]})
        meta = meta.model_copy(update={"totals": _totals(rows, meta.warmups, cost_fn)})
        _write_meta(run_dir, meta)

    writer = _RowWriter(plain)
    try:
        stopped = await _fan_out(
            pending,
            reserve_of=lambda item: requests.reserve(item.text),
            process=requests.item_row,
            on_row=writer.write,
            ledger=ledger,
            concurrency=concurrency,
        )
    finally:
        writer.close()

    rows = sorted(read_rows(run_dir), key=lambda r: index[r.item_id])
    complete = not stopped and len(rows) == len(items)
    _write_final_rows(run_dir, rows)
    meta = meta.model_copy(
        update={
            "returned_model_ids": sorted({r.model_id for r in rows if r.model_id is not None}),
            "ended_at": _timestamp(sender.clock.now()),
            "complete": complete,
            "incomplete_reason": None if complete else budget.reason,
            "totals": _totals(rows, meta.warmups, cost_fn),
        }
    )
    _write_meta(run_dir, meta)
    plain.unlink()
    return meta


async def retry_errors(
    run_dir: Path,
    cfg: Configuration,
    prompt: Prompt,
    items: Sequence[Item],
    *,
    sender: Sender,
    repo_root: Path,
    cost_fn: CostFn,
    timeout_usage_fn: TimeoutUsageFn,
    token_estimate_fn: TokenEstimateFn,
    budget: RunBudget,
    contract_tag: str = CONTRACT_TAG,
    concurrency: int = CONCURRENCY,
) -> RunMeta:
    """The single `--retry-errors` pass of a finalized run (spec §9.2): re-request only `api_error` rows
    and rewrite them in place. A rewritten row keeps its earlier attempts, so their charges stay counted."""
    if not 1 <= concurrency <= CONCURRENCY:
        raise ValueError(f"concurrency must be 1..{CONCURRENCY}")
    meta = read_meta(run_dir)
    if meta.ended_at is None or not (run_dir / ITEMS_FINAL).exists():
        raise RunnerError(f"run {meta.run_id} is not finalized; resume it first")
    if meta.retry_errors_passes >= 1:
        raise RunnerError(f"run {meta.run_id} already had its retry-errors pass")
    _check_identity(meta, _identity(cfg, prompt, meta.split, items))
    if meta.split in GUARDED_SPLITS and check_freeze(repo_root, contract_tag) != meta.contract_tag_commit:
        raise RunnerError(f"run {meta.run_id} was made under another contract tag commit")

    by_id = {item.item_id: item for item in items}
    rows = read_rows(run_dir)
    errors = [r for r in rows if r.status == "api_error"]
    requests = _Requests(cfg, prompt, sender, cost_fn, timeout_usage_fn, token_estimate_fn)
    ledger = _Ledger(budget, cost_fn)
    if errors and not ledger.fits(requests.reserve(by_id[errors[0].item_id].text)):
        raise BudgetExceeded(f"{cfg.id}: no room under the ${budget.ceiling_usd:.4f} ceiling for the retry pass")

    rewritten: dict[str, ItemRow] = {}

    async def process(row: ItemRow) -> ItemRow:
        return await requests.item_row(by_id[row.item_id], earlier=row.attempts)

    def keep(new_row: ItemRow) -> None:
        rewritten[new_row.item_id] = new_row

    await _fan_out(
        errors,
        reserve_of=lambda row: requests.reserve(by_id[row.item_id].text),
        process=process,
        on_row=keep,
        ledger=ledger,
        concurrency=concurrency,
    )
    rows = [rewritten.get(r.item_id, r) for r in rows]
    _write_final_rows(run_dir, rows)
    meta = meta.model_copy(
        update={
            "returned_model_ids": sorted({r.model_id for r in rows if r.model_id is not None}),
            "retry_errors_passes": meta.retry_errors_passes + 1,
            "retry_errors_rewritten": meta.retry_errors_rewritten + len(rewritten),
            "totals": _totals(rows, meta.warmups, cost_fn),
        }
    )
    _write_meta(run_dir, meta)
    return meta


def run_validity(meta: RunMeta, rows: Sequence[ItemRow]) -> tuple[bool, str]:
    """Whether `decide` may use a run (spec §9.2): complete and an API error rate ≤ 0.5 %."""
    if not meta.complete:
        return False, f"run {meta.run_id} is incomplete: {meta.incomplete_reason or 'not finalized'}"
    if not rows:
        return False, f"run {meta.run_id} has no item rows"
    errors = sum(r.status == "api_error" for r in rows)
    num, den = MAX_API_ERROR_RATE
    if errors * den > num * len(rows):
        hint = "" if meta.retry_errors_passes else "; one retry-errors pass is allowed"
        return False, f"run {meta.run_id}: API error rate {errors}/{len(rows)} exceeds 0.5 %{hint}"
    return True, f"run {meta.run_id}: API error rate {errors}/{len(rows)}"
