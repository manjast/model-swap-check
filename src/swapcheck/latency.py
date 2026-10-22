"""Sequential, descriptive latency study and deterministic replay (spec section 9.6)."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
from pydantic import BaseModel, ConfigDict

from swapcheck import cost, runner
from swapcheck.budget import BUDGET_STOP, BudgetConfig
from swapcheck.configs import Configuration
from swapcheck.data import Item
from swapcheck.freeze import head_commit
from swapcheck.http import Clock, Sender, SendResult, SystemClock
from swapcheck.manifest import ManifestRun, load_manifest
from swapcheck.prompt import Prompt
from swapcheck.providers.base import WARMUP_TEXT
from swapcheck.records import ITEMS_PLAIN, ItemRow, RunMeta, Usage, Warmup, read_meta, read_rows
from swapcheck.schema import schema_sha256

ORDER = ("inc", "luna-none", "luna-dec", "haiku55-off", "jev-c51", "jev-noul")


class LatencyError(RuntimeError):
    """A study cannot start or its evidence cannot be reported."""


class Call(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round: int
    position: int
    config_id: str
    item_id: str


class Probe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round: int
    host: str
    connect_ms: float | None
    error: str | None = None


class Study(BaseModel):
    model_config = ConfigDict(extra="forbid")

    study_id: str
    client: str
    git_commit: str
    started_at: str
    ended_at: str | None = None
    rounds: int
    configuration_order: list[str]
    run_ids: dict[str, str]
    hosts: dict[str, str]
    calls: list[Call] = []
    probes: list[Probe] = []
    complete: bool = False
    incomplete_reason: str | None = None


def _save(path: Path, study: Study) -> None:
    runner._atomic_write(path, (study.model_dump_json(indent=2) + "\n").encode())


async def tcp_probe(host: str, clock: Clock) -> float:
    start = clock.monotonic()
    async with asyncio.timeout(60):
        _, writer = await asyncio.open_connection(host, 443)
    elapsed = (clock.monotonic() - start) * 1000
    writer.close()
    await writer.wait_closed()
    return elapsed


def frozen_entries(
    runs_dir: Path, configs: Mapping[str, Configuration], prompts: Mapping[str, Prompt]
) -> dict[str, ManifestRun]:
    manifest = load_manifest(runs_dir)
    result: dict[str, ManifestRun] = {}
    for cid in ORDER:
        entries = [entry for entry in manifest.runs if entry.config_id == cid and entry.split == "cert"]
        if len(entries) != 1:
            raise LatencyError(f"{cid}: expected exactly one frozen cert manifest entry")
        entry = entries[0]
        expected = (configs[cid].sha256(), prompts[cid].sha256(), schema_sha256(configs[cid], prompts[cid]))
        if (entry.config_sha256, entry.prompt_sha256, entry.schema_sha256) != expected:
            raise LatencyError(f"{cid}: configuration, prompt or schema differs from frozen cert settings")
        result[cid] = entry
    return result


async def run_study(
    *,
    client: str,
    rounds: int,
    items: Sequence[Item],
    configs: Mapping[str, Configuration],
    prompts: Mapping[str, Prompt],
    senders: Mapping[str, Sender],
    prices: cost.Prices,
    budget: BudgetConfig,
    runs_dir: Path,
    repo_root: Path,
    clock: Clock | None = None,
    probe: Callable[[str, Clock], Awaitable[float]] = tcp_probe,
) -> Study:
    """Run without resume; persist every completed paid request before starting the next."""
    if rounds < 1 or rounds > len(items):
        raise LatencyError(f"rounds must be between 1 and {len(items)}")
    if not client.strip():
        raise LatencyError("client must describe the city and network")
    entries = frozen_entries(runs_dir, configs, prompts)
    clock = clock or SystemClock()
    selected = list(items[:rounds])
    now = clock.now()
    study_id = f"latency-{now:%Y%m%dT%H%M%SZ}"
    study_dir = runs_dir / study_id
    ids = {cid: runner.default_run_id(cid, "latency", now) for cid in ORDER}
    if study_dir.exists() or any((runs_dir / rid).exists() for rid in ids.values()):
        raise LatencyError(f"{study_id}: already exists; latency studies cannot resume")
    spent = cost.spent_usd(runs_dir, prices, configs)
    hosts: dict[str, str] = {}
    requests: dict[str, runner._Requests] = {}
    metas: dict[str, RunMeta] = {}
    rows: dict[str, list[ItemRow]] = {cid: [] for cid in ORDER}
    invocation_spend: dict[str, float] = {}
    for cid in ORDER:
        cfg, p, sender = configs[cid], prompts[cid], senders[cid]
        sample = sender.adapter.build_request(cfg, p, WARMUP_TEXT, None)
        host = urlsplit(sample.url).hostname
        if host is None:
            raise LatencyError(f"{cid}: request URL has no host")
        hosts[cid] = host
        sender.trace_timing = True

        def cost_fn(usage: Usage, cfg: Configuration = cfg) -> float:
            return cost.attempt_cost_usd(prices, cfg, usage)

        def timeout_fn(text: str, cfg: Configuration = cfg, p: Prompt = p) -> Usage:
            return cost.timeout_usage(cfg, p, text)

        def reservation_fn(text: str, cfg: Configuration = cfg, p: Prompt = p) -> float:
            return cost.reservation_usd(prices, cfg, cost.timeout_usage(cfg, p, text))

        ledger = runner._Ledger(runner.RunBudget(spent.get(cfg.provider, 0.0), budget.limit(cfg.provider)), cost_fn)
        requests[cid] = runner._Requests(cfg, p, sender, ledger, timeout_fn, reservation_fn, lambda _: 0)
        metas[cid] = RunMeta(
            run_id=ids[cid],
            **runner._identity(cfg, p, "latency", selected),
            study_id=study_id,
            returned_model_ids=[],
            versions=runner._versions(sample.headers),
            git_commit=head_commit(repo_root),
            contract_tag_commit=entries[cid].contract_tag_commit,
            warmups=[],
            started_at=runner._timestamp(now),
            ended_at=None,
            complete=False,
            incomplete_reason=None,
            retry_errors_passes=0,
            retry_errors_rewritten=0,
            totals=runner._totals([], [], cost_fn),
        )
    study = Study(
        study_id=study_id,
        client=client,
        git_commit=head_commit(repo_root),
        started_at=runner._timestamp(now),
        rounds=rounds,
        configuration_order=list(ORDER),
        run_ids=ids,
        hosts=hosts,
    )
    study_dir.mkdir(parents=True)
    path = study_dir / "study.json"
    _save(path, study)
    for cid in ORDER:
        (runs_dir / ids[cid]).mkdir()
        runner._write_meta(runs_dir / ids[cid], metas[cid])

    async def send(cid: str, text: str, key: str | None) -> SendResult:
        req = requests[cid]
        provider = req.cfg.provider
        # Other configurations share a provider cap, but have different token prices.
        req.ledger.budget = runner.RunBudget(
            spent.get(provider, 0.0) + invocation_spend.get(provider, 0.0) - req.ledger.spent,
            budget.limit(provider),
        )
        before = req.ledger.spent
        result = await req.send(text, key, req.gate(text))
        invocation_spend[provider] = invocation_spend.get(provider, 0.0) + req.ledger.spent - before
        return result

    reason: str | None = None
    for cid in ORDER:
        req = requests[cid]
        for key in req.sender.adapter.warmup_cache_keys(req.cfg):
            result = await send(cid, WARMUP_TEXT, key)
            if result.attempts:
                metas[cid].warmups.append(Warmup(cache_key=key, attempts=result.attempts))
                metas[cid].totals = runner._totals(rows[cid], metas[cid].warmups, req.ledger.cost_fn)
                runner._write_meta(runs_dir / ids[cid], metas[cid])
            if result.error_code == "budget":
                reason = BUDGET_STOP
                break
        if reason is not None:
            break
    for r, item in enumerate(selected):
        if reason is not None:
            break
        for host in dict.fromkeys(hosts.values()):
            try:
                elapsed = await probe(host, clock)
                observation = Probe(round=r, host=host, connect_ms=elapsed)
            except (OSError, TimeoutError) as exc:
                observation = Probe(round=r, host=host, connect_ms=None, error=type(exc).__name__)
            study.probes.append(observation)
            _save(path, study)
        rotation = ORDER[r % len(ORDER) :] + ORDER[: r % len(ORDER)]
        for position, cid in enumerate(rotation):
            req = requests[cid]
            result = await send(cid, item.text, req.sender.adapter.cache_key(req.cfg, item.digest))
            if result.attempts:
                row = runner._row(req.cfg, item.item_id, result, ())
                writer = runner._RowWriter(runs_dir / ids[cid] / ITEMS_PLAIN)
                try:
                    writer.write(row)
                finally:
                    writer.close()
                rows[cid].append(row)
                study.calls.append(Call(round=r, position=position, config_id=cid, item_id=item.item_id))
                _save(path, study)
            if result.error_code == "budget":
                reason = BUDGET_STOP
                break
    end = runner._timestamp(clock.now())
    for cid in ORDER:
        meta = metas[cid]
        meta.complete = reason is None
        meta.incomplete_reason = reason
        meta.ended_at = end
        meta.returned_model_ids = sorted({row.model_id for row in rows[cid] if row.model_id is not None})
        meta.totals = runner._totals(rows[cid], meta.warmups, requests[cid].ledger.cost_fn)
        runner._write_final_rows(runs_dir / ids[cid], rows[cid])
        runner._write_meta(runs_dir / ids[cid], meta)
        (runs_dir / ids[cid] / ITEMS_PLAIN).unlink(missing_ok=True)
    study.complete = reason is None
    study.incomplete_reason = reason
    study.ended_at = end
    _save(path, study)
    return study


def _quantile(values: Sequence[float], q: float) -> str:
    return f"{float(np.quantile(values, q, method='higher')):.0f}" if values else "n/a"


def _pair(values: Sequence[float]) -> str:
    return f"{_quantile(values, 0.5)} / {_quantile(values, 0.95)}"


def write_report(runs_dir: Path, output_dir: Path) -> Path:
    paths = sorted(runs_dir.glob("*/study.json"))
    if len(paths) != 1:
        raise LatencyError(f"expected exactly one complete latency study; found {len(paths)} studies")
    study = Study.model_validate_json(paths[0].read_text(encoding="utf-8"))
    if not study.complete or study.ended_at is None:
        raise LatencyError(f"{study.study_id}: incomplete latency study")
    if study.configuration_order != list(ORDER) or set(study.run_ids) != set(ORDER):
        raise LatencyError("study configuration order is invalid")
    if len(study.calls) != study.rounds * len(ORDER):
        raise LatencyError("study call schedule is incomplete")
    lines = [
        "# Latency study",
        "",
        f"Study: `{study.study_id}`",
        "",
        f"UTC window: {study.started_at} to {study.ended_at}",
        "",
        f"Client: {study.client}",
        "",
        f"Git commit: `{study.git_commit}`",
        "",
        f"Rounds: {study.rounds}",
        "",
        "All timings are milliseconds, rounded to whole ms; quantiles use method=higher.",
        "Warm-ups are excluded. Errors are counted, not timed. No routing outcomes are analysed.",
        "",
        "| Configuration | Successful final attempts | Retries | Errors | Total p50 / p95 | Headers p50 / p95 | "
        "Server p50 / p95 | Headers minus server p50 / p95 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    connections: dict[str, list[tuple[float, float | None]]] = {}
    for cid in ORDER:
        run_dir = runs_dir / study.run_ids[cid]
        if not (run_dir / "run.json").exists():
            raise LatencyError(f"{cid}: study run is missing")
        meta, rows = read_meta(run_dir), read_rows(run_dir)
        calls = [call for call in study.calls if call.config_id == cid]
        if (
            not meta.complete
            or meta.split != "latency"
            or meta.study_id != study.study_id
            or len(rows) != study.rounds
            or [row.item_id for row in rows] != [call.item_id for call in calls]
        ):
            raise LatencyError(f"{cid}: incomplete or inconsistent study run")
        successes = [
            row.attempts[-1]
            for row in rows
            if row.attempts
            and row.attempts[-1].error is None
            and row.attempts[-1].http_status is not None
            and 200 <= row.attempts[-1].http_status < 300
        ]
        totals = [a.latency_ms for a in successes if a.latency_ms is not None]
        headers = [a.timing.headers_ms for a in successes if a.timing is not None and a.timing.headers_ms is not None]
        servers: list[float] = []
        residuals: list[float] = []
        if cid in ("inc", "luna-none", "luna-dec"):
            for attempt in successes:
                try:
                    server = float(attempt.headers["openai-processing-ms"])
                except (KeyError, ValueError):
                    continue
                if not math.isfinite(server):
                    continue
                servers.append(server)
                if attempt.timing is not None and attempt.timing.headers_ms is not None:
                    residuals.append(attempt.timing.headers_ms - server)
        for row in rows:
            for attempt in row.attempts:
                timing = attempt.timing
                if timing is not None and timing.connect_ms is not None:
                    connections.setdefault(study.hosts[cid], []).append((timing.connect_ms, timing.tls_ms))
        retries = sum(max(0, len(row.attempts) - 1) for row in rows)
        lines.append(
            f"| {cid} | {len(successes)} | {retries} | {len(rows) - len(successes)} | {_pair(totals)} | "
            f"{_pair(headers)} | {_pair(servers)} | {_pair(residuals)} |"
        )
    lines += [
        "",
        "| Host | TCP probe p50 / p95 | Probe errors | New connections | Connect p50 | TLS p50 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for host in sorted(set(study.hosts.values())):
        observations = [p for p in study.probes if p.host == host]
        if len(observations) != study.rounds:
            raise LatencyError(f"{host}: incomplete TCP probes")
        values = [p.connect_ms for p in observations if p.connect_ms is not None]
        opened = connections.get(host, [])
        lines.append(
            f"| {host} | {_pair(values)} | {sum(p.error is not None for p in observations)} | {len(opened)} | "
            f"{_quantile([v[0] for v in opened], 0.5)} | "
            f"{_quantile([v[1] for v in opened if v[1] is not None], 0.5)} |"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "latency.md"
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output
