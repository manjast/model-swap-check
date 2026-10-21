"""T-K1: cost from hand-built attempt rows (spec §9.5, §10, §11). Expected values are hand-computed."""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest
import tiktoken

from swapcheck import cost
from swapcheck.configs import Configuration, load_configurations
from swapcheck.prompt import Prompt, prefix_tokens
from swapcheck.records import (
    ITEMS_FINAL,
    ITEMS_PLAIN,
    RUN_JSON,
    Attempt,
    ItemRow,
    RunMeta,
    RunTotals,
    Usage,
    Warmup,
)

CONFIGS = load_configurations()
PRICES = cost.load_prices()
U = 1e-6  # hand computations below are in micro-dollars


def ok(number: int = 1, **usage: int) -> Attempt:
    return Attempt(number=number, http_status=200, usage=Usage(**usage))


def failed(number: int, status: int) -> Attempt:
    return Attempt(number=number, http_status=status, error=f"http_{status}")


def timed_out(number: int, uncached_input: int, output: int) -> Attempt:
    return Attempt(
        number=number,
        http_status=None,
        error="timeout",
        usage=Usage(uncached_input=uncached_input, output=output),
        usage_estimated=True,
    )


def row(item_id: str, *attempts: Attempt) -> ItemRow:
    return ItemRow(
        item_id=item_id,
        status="ok",
        error_code=None,
        stop_reason="stop",
        raw_output="{}",
        intent="card_arrival",
        confidence=0.9,
        probabilities=None,
        match_probability=None,
        case_normalized=False,
        latency_ms=100.0,
        request_id="req",
        model_id="m",
        attempts=list(attempts),
    )


def warmup(*attempts: Attempt) -> Warmup:
    return Warmup(cache_key=None, attempts=list(attempts))


# luna-none (OpenAI explicit cache): one warm-up, a 429 retry, a timed-out attempt, a cache miss.
LUNA_WARMUPS = [warmup(ok(uncached_input=8, cache_write=2000, output=4))]  # 0.8 + 250 + 2 = 252.8
LUNA_ROWS = [
    row("train-1", ok(uncached_input=20, cache_read=2000, output=10, reasoning=0)),  # 2 + 20 + 5 = 27
    row("train-2", failed(1, 429), ok(2, uncached_input=40, cache_read=2000, output=10, reasoning=0)),  # 29
    row(
        "train-3",
        timed_out(1, uncached_input=2030, output=200),  # 203 + 100 = 303
        ok(2, uncached_input=30, cache_read=2000, output=10, reasoning=0),  # 3 + 20 + 5 = 28
    ),
    row("train-4", ok(uncached_input=2010, output=30, reasoning=0)),  # 201 + 15 = 216
]

# haiku55-medium (Anthropic): thinking tokens reported as a subset of output.
HAIKU_WARMUPS = [warmup(ok(uncached_input=5, cache_write=2500, output=3))]  # 0.5 + 312.5 + 1.5 = 314.5
HAIKU_ROWS = [
    row("train-1", ok(uncached_input=15, cache_read=2500, output=400, reasoning=300)),  # 1.5 + 25 + 200 = 226.5
    row("train-2", failed(1, 529), ok(2, uncached_input=25, cache_read=2500, output=1200, reasoning=1100)),  # 627.5
    row("train-3", ok(uncached_input=20, cache_read=2500, output=100, reasoning=0)),  # 2 + 25 + 50 = 77
]

# jev-c51 (TypeSafe): input only, output free, no warm-ups.
JEV_ROWS = [
    row("train-1", ok(uncached_input=1500, output=30)),  # 63
    row(
        "train-2",
        failed(1, 500),
        timed_out(2, uncached_input=1600, output=0),  # 67.2
        ok(3, uncached_input=1510, output=30),  # 63.42
    ),
]


def test_k1_openai_billed_steady_sparse_and_token_stats() -> None:
    m = cost.cost_model(CONFIGS["luna-none"], LUNA_ROWS, LUNA_WARMUPS, PRICES)
    # billed: (252.8 + 27 + 29 + 303 + 28 + 216) / 4 items
    assert m.billed_per_1000 == pytest.approx(1000 * 855.8 * U / 4)
    assert m.item_mean_usd == pytest.approx(150.75 * U)
    assert m.item_p90_usd == pytest.approx(331 * U)  # "higher" p90 of [27, 29, 216, 331]
    # successful calls: inputs 2020, 2040, 2030, 2010 (mean 2025), outputs mean 15; prefix 2000
    assert m.prefix_tokens == 2000
    assert m.steady_per_1000 == pytest.approx(1000 * (2000 * 0.01 + 25 * 0.10 + 15 * 0.50) * U)
    assert m.sparse_per_1000 == pytest.approx(1000 * (2025 * 0.10 + 15 * 0.50) * U)
    # per item, summed over attempts: uncached [20, 40, 2060, 2010], cache read [2000, 2000, 2000, 0]
    assert m.tokens["uncached_input"] == cost.ClassStats(mean=1032.5, p90=2060)
    assert m.tokens["cache_read"] == cost.ClassStats(mean=1500, p90=2000)
    assert m.tokens["output"] == cost.ClassStats(mean=65, p90=210)
    assert m.tokens["cache_write"] == cost.ClassStats(mean=0, p90=0)


def test_k1_anthropic_billed_steady_sparse_and_reasoning() -> None:
    m = cost.cost_model(CONFIGS["haiku55-medium"], HAIKU_ROWS, HAIKU_WARMUPS, PRICES)
    assert m.billed_per_1000 == pytest.approx(1000 * 1245.5 * U / 3)
    assert m.item_p90_usd == pytest.approx(627.5 * U)
    # inputs 2515, 2525, 2520 (mean 2520), outputs mean 1700/3; prefix 2500
    mean_out = 1700 / 3
    assert m.steady_per_1000 == pytest.approx(1000 * (2500 * 0.01 + 20 * 0.10 + mean_out * 0.50) * U)
    assert m.sparse_per_1000 == pytest.approx(1000 * (2520 * 0.10 + mean_out * 0.50) * U)
    # thinking is part of output, never billed twice: output p90 is 1200, not 2300
    assert m.tokens["output"].p90 == 1200
    assert m.reasoning_mean == pytest.approx(1400 / 3)
    assert m.reasoning_p95 == 1100


def test_k1_typesafe_input_only() -> None:
    m = cost.cost_model(CONFIGS["jev-c51"], JEV_ROWS, [], PRICES)
    assert m.billed_per_1000 == pytest.approx(1000 * (63 + 67.2 + 63.42) * U / 2)
    assert m.item_p90_usd == pytest.approx(130.62 * U)
    assert m.prefix_tokens == 0
    assert m.steady_per_1000 == pytest.approx(1000 * 1505 * 0.042 * U)
    assert m.sparse_per_1000 == m.steady_per_1000
    assert m.reasoning_mean is None and m.reasoning_p95 is None


@pytest.mark.parametrize(("config_id", "max_output"), [("luna-none", 200), ("haiku55-medium", 4096), ("jev-noul", 0)])
def test_k1_timeout_charged_as_full_input_plus_max_output(incumbent: Prompt, config_id: str, max_output: int) -> None:
    text = "I still have not received my new card, what should I do?"
    expected_input = prefix_tokens(incumbent) + len(tiktoken.get_encoding("o200k_base").encode(text))
    usage = cost.timeout_usage(CONFIGS[config_id], incumbent, text)
    assert usage == Usage(uncached_input=expected_input, output=max_output)


def test_k1_every_configuration_is_priced() -> None:
    for cfg in CONFIGS.values():
        PRICES.for_model(cfg.model)
    with pytest.raises(KeyError, match="no price"):
        cost.attempt_cost_usd(PRICES, CONFIGS["inc"].model_copy(update={"model": "gpt-4o-mini"}), Usage())


def _meta(run_id: str, cfg: Configuration, warmups: list[Warmup], complete: bool) -> RunMeta:
    return RunMeta(
        run_id=run_id,
        config_id=cfg.id,
        config_sha256=cfg.sha256(),
        split="pilot",
        item_list_sha256="x",
        prompt_sha256="x",
        schema_sha256="x",
        requested_model=cfg.model,
        returned_model_ids=[],
        versions={},
        git_commit="x",
        contract_tag_commit=None,
        warmups=warmups,
        started_at="2026-10-21T00:00:00Z",
        ended_at=None,
        complete=complete,
        incomplete_reason=None,
        retry_errors_passes=0,
        retry_errors_rewritten=0,
        totals=RunTotals(by_status={}, tokens=Usage(), billed_usd=0.0, case_normalized=0, n_429=0),
    )


def _write_run(
    runs: Path,
    run_id: str,
    cfg: Configuration,
    rows: list[ItemRow],
    warmups: list[Warmup],
    *,
    final: bool,
    trailing: str = "",
) -> None:
    d = runs / run_id
    d.mkdir(parents=True)
    (d / RUN_JSON).write_text(_meta(run_id, cfg, warmups, final).model_dump_json(), encoding="utf-8")
    body = "".join(r.model_dump_json() + "\n" for r in rows)
    if final:
        (d / ITEMS_FINAL).write_bytes(gzip.compress(body.encode()))
    else:
        (d / ITEMS_PLAIN).write_text(body + trailing, encoding="utf-8")


def test_k1_spent_counts_every_attempt_and_warmup_including_in_progress_runs(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    _write_run(runs, "r1", CONFIGS["luna-none"], LUNA_ROWS, LUNA_WARMUPS, final=True)
    # in-progress Anthropic run killed mid-line: the partial row is not charged
    partial = '{"item_id": "tr'
    _write_run(runs, "r2", CONFIGS["haiku55-medium"], HAIKU_ROWS, HAIKU_WARMUPS, final=False, trailing=partial)
    _write_run(runs, "r3", CONFIGS["jev-c51"], JEV_ROWS, [], final=True)
    # a second OpenAI run (inc, implicit cache: reads at 0.075, no write charge), only warm-ups so far
    _write_run(runs, "r4", CONFIGS["inc"], [], [warmup(ok(uncached_input=100, cache_read=1920, output=5))], final=False)
    (runs / "manifest.yaml").write_text("runs: {}\n", encoding="utf-8")

    spent = cost.spent_usd(runs, PRICES, CONFIGS)
    assert spent["openai"] == pytest.approx((855.8 + 15 + 144 + 3) * U)
    assert spent["anthropic"] == pytest.approx(1245.5 * U)
    assert spent["typesafe"] == pytest.approx(193.62 * U)


def test_k1_spent_refuses_rows_without_run_json(tmp_path: Path) -> None:
    d = tmp_path / "orphan"
    d.mkdir()
    (d / ITEMS_PLAIN).write_text(LUNA_ROWS[0].model_dump_json() + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot be attributed"):
        cost.spent_usd(tmp_path, PRICES, CONFIGS)
