"""Runner with a fake provider: T-R3 (rows), T-R4, T-R5, T-R6 (in-run stop), T-R8, T-R9 (spec §4, §9, §10)."""

from __future__ import annotations

import asyncio
import gzip
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import (
    FakeClock,
    clone_repo,
    cost,
    items,
    make_repo,
    max_in_any_window,
    ok_body,
    ok_handler,
    request_text,
    retry_sync,
    run_sync,
)

from swapcheck.configs import Configuration, load_configurations
from swapcheck.prompt import Prompt
from swapcheck.providers.base import WARMUP_TEXT
from swapcheck.ratelimit import Limit, RateLimiter
from swapcheck.records import ITEMS_FINAL, ITEMS_PLAIN, ItemRow, RunMeta, RunTotals, Usage, read_meta, read_rows
from swapcheck.runner import BudgetExceeded, RunBudget, RunnerError, run_validity

CONFIGS = load_configurations()
ROW_FIELDS = {
    "item_id",
    "status",
    "error_code",
    "stop_reason",
    "raw_output",
    "intent",
    "confidence",
    "probabilities",
    "match_probability",
    "case_normalized",
    "latency_ms",
    "request_id",
    "model_id",
    "attempts",
}  # spec §10
USAGE_FIELDS = {"uncached_input", "cache_read", "cache_write", "output", "reasoning"}


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return make_repo(tmp_path_factory.mktemp("template") / "repo")


@pytest.fixture
def repo(template: Path, tmp_path: Path) -> Path:
    return clone_repo(template, tmp_path / "repo")


def gz_lines(run_dir: Path) -> list[dict[str, Any]]:
    text = gzip.decompress((run_dir / ITEMS_FINAL).read_bytes()).decode()
    return [json.loads(line) for line in text.splitlines()]


# --- T-R4 ---------------------------------------------------------------------------------------


def test_r4_concurrency_at_most_16_and_all_warmups_before_fan_out(incumbent: Prompt, repo: Path) -> None:
    events: list[tuple[str, str, str | None]] = []
    in_flight = 0
    peak = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, peak
        body = json.loads(request.content)
        events.append(("start", body["text"], body["cache_key"]))
        in_flight += 1
        peak = max(peak, in_flight)
        for _ in range(3):
            await asyncio.sleep(0)
        in_flight -= 1
        events.append(("end", body["text"], body["cache_key"]))
        return httpx.Response(200, json=ok_body())

    meta = run_sync(CONFIGS["inc"], incumbent, "dev", items(60), handler, repo)

    assert peak == 16
    warmup_starts = [e for e in events if e[0] == "start" and e[1] == WARMUP_TEXT]
    assert sorted(e[2] or "" for e in warmup_starts) == sorted(f"k{i}" for i in range(16))
    last_warmup_end = max(i for i, e in enumerate(events) if e[0] == "end" and e[1] == WARMUP_TEXT)
    first_item_start = min(i for i, e in enumerate(events) if e[0] == "start" and e[1] != WARMUP_TEXT)
    assert last_warmup_end < first_item_start
    assert len(meta.warmups) == 16 and all(w.attempts[0].usage.cache_read == 1000 for w in meta.warmups)


@pytest.mark.parametrize(
    ("config_id", "limit"),
    [
        ("luna-none", Limit(per="minute", requests=8, tokens=100_000)),
        ("haiku55-off", Limit(per="minute", requests=100, tokens=500)),  # 5 requests of 100 tokens
        ("jev-c51", Limit(per="second", requests=5, tokens=100_000)),
    ],
)
def test_r4_rate_limit_never_exceeded_in_any_window(
    incumbent: Prompt, repo: Path, config_id: str, limit: Limit
) -> None:
    clock = FakeClock()
    starts: list[tuple[float, int]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        starts.append((clock.monotonic(), 100))
        clock.t += 0.05
        return httpx.Response(200, json=ok_body())

    run_sync(
        CONFIGS[config_id],
        incumbent,
        "dev",
        items(30),
        handler,
        repo,
        clock=clock,
        limiter=RateLimiter(limit, clock),
        tokens=100,
    )
    worst_requests, worst_tokens = max_in_any_window(starts, limit.window_s)
    assert worst_requests <= limit.requests and worst_tokens <= limit.tokens
    assert len(starts) == 30 + (1 if CONFIGS[config_id].is_llm else 0)


# --- T-R3: final failure → api_error, every attempt kept --------------------------------------------


def test_r3_final_failure_is_api_error_with_every_attempt(incumbent: Prompt, repo: Path) -> None:
    its = items(4)

    async def handler(request: httpx.Request) -> httpx.Response:
        text = request_text(request)
        if text == its[1].text:
            return httpx.Response(503, json={"error": {"message": "overloaded"}})
        if text == its[2].text:
            return httpx.Response(400, json={"error": {"message": "bad request"}})
        return httpx.Response(200, json=ok_body())

    meta = run_sync(CONFIGS["luna-none"], incumbent, "dev", its, handler, repo, run_id="r")
    rows = {r.item_id: r for r in read_rows(repo / "runs" / "r")}
    assert rows["test-1"].status == "api_error" and rows["test-1"].error_code == "http_503"
    assert [a.http_status for a in rows["test-1"].attempts] == [503] * 6
    assert rows["test-2"].error_code == "http_400" and len(rows["test-2"].attempts) == 1
    assert rows["test-2"].raw_output is not None and "bad request" in rows["test-2"].raw_output
    assert rows["test-0"].status == rows["test-3"].status == "ok"
    assert meta.totals.by_status == {"ok": 2, "invalid_output": 0, "api_error": 2}


# --- T-R5 ---------------------------------------------------------------------------------------


class Killed(Exception):
    pass


def test_r5_resume_skips_recorded_items_and_drops_partial_line(incumbent: Prompt, repo: Path) -> None:
    cfg, its = CONFIGS["luna-none"], items(10)
    run_dir = repo / "runs" / "r1"

    async def dies_at_item_4(request: httpx.Request) -> httpx.Response:
        if request_text(request) == its[4].text:
            raise Killed
        return httpx.Response(200, json=ok_body())

    with pytest.raises(BaseExceptionGroup):
        run_sync(cfg, incumbent, "dev", its, dies_at_item_4, repo, run_id="r1", concurrency=1)
    assert [r.item_id for r in read_rows(run_dir)] == [f"test-{i}" for i in range(4)]
    started = read_meta(run_dir)
    assert started.complete is False and started.ended_at is None
    with (run_dir / ITEMS_PLAIN).open("a") as f:
        f.write('{"item_id": "test-4", "sta')  # killed mid-write

    requested: list[str] = []

    async def records(request: httpx.Request) -> httpx.Response:
        requested.append(request_text(request))
        return httpx.Response(200, json=ok_body())

    meta = run_sync(cfg, incumbent, "dev", its, records, repo, run_id="r1")
    assert sorted(t for t in requested if t != WARMUP_TEXT) == sorted(it.text for it in its[4:])
    assert [r.item_id for r in read_rows(run_dir)] == [it.item_id for it in its]
    assert meta.complete and not (run_dir / ITEMS_PLAIN).exists()

    with pytest.raises(RunnerError, match="finalized"):
        run_sync(cfg, incumbent, "dev", its, records, repo, run_id="r1")

    requested.clear()
    run_sync(cfg, incumbent, "dev", its, records, repo, run_id="r2")
    assert sorted(t for t in requested if t != WARMUP_TEXT) == sorted(it.text for it in its)


def test_r5_resume_refuses_a_different_item_list(incumbent: Prompt, repo: Path) -> None:
    cfg = CONFIGS["luna-none"]

    async def dies(request: httpx.Request) -> httpx.Response:
        if request_text(request) == items(5)[2].text:
            raise Killed
        return httpx.Response(200, json=ok_body())

    with pytest.raises(BaseExceptionGroup):
        run_sync(cfg, incumbent, "dev", items(5), dies, repo, run_id="r", concurrency=1)
    with pytest.raises(RunnerError, match="item_list_sha256"):
        run_sync(cfg, incumbent, "dev", items(6), ok_handler(), repo, run_id="r")


# --- T-R6 (runner part): in-run stop at the ceiling -----------------------------------------------


def test_r6_run_stops_at_its_ceiling_and_is_incomplete(incumbent: Prompt, repo: Path) -> None:
    budget = RunBudget(spent_before_usd=0.005, ceiling_usd=0.03)
    meta = run_sync(CONFIGS["luna-none"], incumbent, "dev", items(60), ok_handler(), repo, run_id="r", budget=budget)
    rows = read_rows(repo / "runs" / "r")
    assert meta.complete is False and meta.incomplete_reason == "spend ceiling"
    assert 0 < len(rows) < 60
    assert budget.spent_before_usd + meta.totals.billed_usd <= budget.ceiling_usd
    assert run_validity(meta, rows)[0] is False


def test_r6_unaffordable_run_does_not_start(incumbent: Prompt, repo: Path) -> None:
    requested: list[str] = []

    async def records(request: httpx.Request) -> httpx.Response:
        requested.append(request_text(request))
        return httpx.Response(200, json=ok_body())

    budget = RunBudget(spent_before_usd=0.03, ceiling_usd=0.03)
    with pytest.raises(BudgetExceeded):
        run_sync(CONFIGS["luna-none"], incumbent, "dev", items(5), records, repo, run_id="r", budget=budget)
    assert requested == [] and not (repo / "runs" / "r").exists()


# --- T-R8 ---------------------------------------------------------------------------------------


class FailingFor:
    """Answers 400 for the given texts and 200 otherwise, recording every requested text."""

    def __init__(self, texts: set[str]) -> None:
        self.texts = texts
        self.requested: list[str] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        text = request_text(request)
        self.requested.append(text)
        if text in self.texts:
            return httpx.Response(400, json={"error": {"message": "bad"}})
        return httpx.Response(200, json=ok_body())


def test_r8_invalid_run_becomes_valid_after_one_retry_pass(incumbent: Prompt, repo: Path) -> None:
    cfg, its = CONFIGS["luna-none"], items(200)
    run_dir = repo / "runs" / "r"
    broken = {it.text for it in its[:3]}  # 1.5 % > 0.5 %
    meta = run_sync(cfg, incumbent, "dev", its, FailingFor(broken), repo, run_id="r")
    valid, reason = run_validity(meta, read_rows(run_dir))
    assert not valid and "3/200" in reason

    fixed = FailingFor(set())
    meta = retry_sync(run_dir, cfg, incumbent, its, fixed, repo)
    assert sorted(fixed.requested) == sorted(broken)  # only the api_error rows
    rows = read_rows(run_dir)
    assert run_validity(meta, rows)[0] is True
    assert (meta.retry_errors_passes, meta.retry_errors_rewritten) == (1, 3)
    assert read_meta(run_dir) == meta
    retried = rows[0]
    assert retried.status == "ok"
    assert [(a.number, a.http_status) for a in retried.attempts] == [(1, 400), (2, 200)]
    assert meta.totals.by_status == {"ok": 200, "invalid_output": 0, "api_error": 0}

    with pytest.raises(RunnerError, match="already had its retry-errors pass"):
        retry_sync(run_dir, cfg, incumbent, its, fixed, repo)


def test_r8_run_still_invalid_when_errors_persist_after_the_pass(incumbent: Prompt, repo: Path) -> None:
    cfg, its = CONFIGS["luna-none"], items(200)
    broken = {it.text for it in its[:2]}
    run_sync(cfg, incumbent, "dev", its, FailingFor(broken), repo, run_id="r")
    meta = retry_sync(repo / "runs" / "r", cfg, incumbent, its, FailingFor(broken), repo)
    assert run_validity(meta, read_rows(repo / "runs" / "r"))[0] is False


def meta_stub(complete: bool = True) -> RunMeta:
    totals = RunTotals(by_status={}, tokens=Usage(), billed_usd=0.0, case_normalized=0, n_429=0)
    return RunMeta(
        run_id="r",
        config_id="inc",
        config_sha256="c",
        split="cert",
        item_list_sha256="i",
        prompt_sha256="p",
        schema_sha256="s",
        requested_model="m",
        returned_model_ids=[],
        versions={},
        git_commit="g",
        contract_tag_commit="t",
        warmups=[],
        started_at="2026-10-21T00:00:00Z",
        ended_at="2026-10-21T01:00:00Z",
        complete=complete,
        incomplete_reason=None if complete else "budget cap",
        retry_errors_passes=0,
        retry_errors_rewritten=0,
        totals=totals,
    )


def stub_rows(n: int, errors: int) -> list[ItemRow]:
    return [
        ItemRow(
            item_id=f"test-{i}",
            status="api_error" if i < errors else "ok",
            error_code=None,
            stop_reason=None,
            raw_output=None,
            intent=None,
            confidence=None,
            probabilities=None,
            match_probability=None,
            case_normalized=False,
            latency_ms=None,
            request_id=None,
            model_id=None,
            attempts=[],
        )
        for i in range(n)
    ]


@pytest.mark.parametrize(("errors", "valid"), [(0, True), (5, True), (6, False)])
def test_r8_error_rate_threshold_is_half_a_percent_inclusive(errors: int, valid: bool) -> None:
    assert run_validity(meta_stub(), stub_rows(1000, errors))[0] is valid


def test_r8_incomplete_run_is_invalid() -> None:
    valid, reason = run_validity(meta_stub(complete=False), stub_rows(10, 0))
    assert not valid and "budget cap" in reason


# --- T-R9 ---------------------------------------------------------------------------------------


def test_r9_llm_records_match_spec_fields_and_totals(incumbent: Prompt, repo: Path) -> None:
    cfg, its = CONFIGS["luna-none"], items(3)
    run_dir = repo / "runs" / "r"
    rate_limited_once = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal rate_limited_once
        text = request_text(request)
        if text == its[0].text:
            body = ok_body(intent="lost_or_stolen_card", output="x" * 2_500)
        elif text == its[1].text:
            if not rate_limited_once:
                rate_limited_once = True
                return httpx.Response(429, json={"error": {"code": "rate_limit_exceeded"}})
            body = ok_body(intent="lost_or_stolen_card", case_normalized=True)
        elif text == its[2].text:
            body = ok_body(intent="lost_or_stolen_card", status="invalid_output")
        else:
            body = ok_body(intent="lost_or_stolen_card")
        return httpx.Response(200, json=body, headers={"x-request-id": f"req-{text}"})

    meta = run_sync(cfg, incumbent, "dev", its, handler, repo, run_id="r")

    lines = gz_lines(run_dir)
    assert [line["item_id"] for line in lines] == ["test-0", "test-1", "test-2"]
    for line in lines:
        assert set(line) == ROW_FIELDS
        assert all(set(a["usage"]) == USAGE_FIELDS for a in line["attempts"])
        ItemRow.model_validate(line)
        assert line["probabilities"] is None and line["match_probability"] is None
        assert line["intent"] == "lost_or_stolen_card"
    assert "card_arrival" not in json.dumps(lines)  # the ground-truth intent of every item
    assert lines[0]["raw_output"] == "x" * 2_000
    assert [a["http_status"] for a in lines[1]["attempts"]] == [429, 200]
    assert lines[1]["request_id"] == "req-customer message 1"

    assert not (run_dir / ITEMS_PLAIN).exists()
    assert gzip.decompress((run_dir / ITEMS_FINAL).read_bytes())  # valid gzip
    assert (run_dir / ITEMS_FINAL).read_bytes()[4:8] == b"\x00\x00\x00\x00"  # mtime 0
    assert read_meta(run_dir) == meta
    assert meta.complete and meta.incomplete_reason is None and meta.ended_at is not None
    assert meta.totals.by_status == {"ok": 2, "invalid_output": 1, "api_error": 0}
    assert meta.totals.tokens == Usage(uncached_input=400, cache_read=4_000, output=40)  # 3 items + 1 warm-up
    assert meta.totals.billed_usd == pytest.approx(4 * cost(Usage(uncached_input=100, cache_read=1_000, output=10)))
    assert (meta.totals.n_429, meta.totals.case_normalized) == (1, 1)
    assert meta.returned_model_ids == ["fake-model-2026"]
    assert meta.versions["fake-version"] == "2026-10-01" and {"python", "httpx", "swapcheck"} <= set(meta.versions)
    assert meta.contract_tag_commit is None and len(meta.git_commit) == 40


@pytest.mark.parametrize(("config_id", "match_probability"), [("jev-c51", None), ("jev-noul", 0.8)])
def test_r9_jev_records_keep_full_response(
    incumbent: Prompt, repo: Path, config_id: str, match_probability: float | None
) -> None:
    cfg: Configuration = CONFIGS[config_id]
    probabilities = {intent: 1 / len(incumbent.enum) for intent in incumbent.enum}
    body = ok_body(
        probabilities=probabilities,
        match_probability=match_probability,
        usage={"uncached_input": 3_000, "output": 50},
        padding="p" * 3_000,
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    meta = run_sync(cfg, incumbent, "dev", items(2), handler, repo, run_id="r")
    lines = gz_lines(repo / "runs" / "r")
    for line in lines:
        assert set(line) == ROW_FIELDS
        assert line["raw_output"] == json.dumps(body) and len(line["raw_output"]) > 2_000
        assert line["probabilities"] == probabilities
        assert line["match_probability"] == match_probability
    assert meta.warmups == []
    assert meta.totals.tokens == Usage(uncached_input=6_000, output=100)


def test_r9_finalized_rows_are_byte_identical_across_runs(incumbent: Prompt, repo: Path) -> None:
    cfg, its = CONFIGS["luna-none"], items(20)
    run_sync(cfg, incumbent, "dev", its, ok_handler(), repo, run_id="a")
    run_sync(cfg, incumbent, "dev", its, ok_handler(), repo, run_id="b")
    a, b = (repo / "runs" / name / ITEMS_FINAL for name in "ab")
    assert a.read_bytes() == b.read_bytes()
