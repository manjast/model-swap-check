"""Verdicts, A/A floor, operational flags and certification refusal (T-V1..V3, R8/R10)."""

from __future__ import annotations

import gzip
from pathlib import Path

import numpy as np
import pytest
from test_golden import build_golden, load_golden

from swapcheck.contract import AnalysisContract
from swapcheck.decide import (
    DECISIONS,
    FAMILY_CONFIDENCE,
    DecisionRefusal,
    _noise,
    evaluate,
    naive_swap,
    operational_flags,
    verdict,
    write_decisions,
)
from swapcheck.manifest import load_manifest, save_manifest
from swapcheck.outcomes import AnalysisRun
from swapcheck.records import ItemRow, read_meta, read_rows
from swapcheck.stats import GateStatus, gate_g2


@pytest.fixture
def analysis() -> AnalysisContract:
    a = load_golden()[1].analysis
    assert a is not None
    return a


def arm(a: AnalysisContract, *, n: int = 7000, wrong: int = 0, invalid: int = 0) -> AnalysisRun:
    slices = tuple(a.slices[i % 7] for i in range(n))
    return AnalysisRun(
        split="cert",
        item_ids=tuple(map(str, range(n))),
        truth=tuple(f"intent-{s}" for s in slices),
        slices=slices,
        status=tuple("invalid_output" if i < invalid else "ok" for i in range(n)),
        intent=tuple("prediction" for _ in range(n)),
        confidence=np.full(n, 0.9),
        eligible=np.array([i >= invalid for i in range(n)]),
        correct=np.array([i >= wrong for i in range(n)]),
    )


@pytest.mark.parametrize(
    "statuses,expected",
    [
        (("PASS", "PASS", "PASS", "PASS"), "SHIP"),
        (("UNRESOLVED", "PASS", "PASS", "PASS"), "INCONCLUSIVE"),
        (("PASS", "UNRESOLVED", "PASS", "PASS"), "INCONCLUSIVE"),
        (("PASS", "PASS", "UNRESOLVED", "PASS"), "INCONCLUSIVE"),
        (("FAIL", "PASS", "PASS", "PASS"), "BLOCK"),
        (("PASS", "FAIL", "PASS", "PASS"), "BLOCK"),
        (("PASS", "PASS", "FAIL", "PASS"), "BLOCK"),
        (("PASS", "PASS", "PASS", "FAIL"), "BLOCK"),
        (("UNRESOLVED", "FAIL", "PASS", "PASS"), "BLOCK"),
    ],
)
def test_verdict_truth_table(statuses: tuple[GateStatus, ...], expected: str) -> None:
    assert verdict(statuses) == expected
    assert verdict(statuses, noise_failed=True) == "INCONCLUSIVE"


def test_constructed_ship_block_and_threshold_101(analysis: AnalysisContract) -> None:
    inc = arm(analysis)
    assert verdict(evaluate(inc, inc, 0.7, 0.7, analysis).statuses) == "SHIP"
    candidate = arm(analysis, wrong=500)
    assert evaluate(inc, candidate, 0.7, 0.7, analysis).g1.status == "FAIL"
    assert verdict(evaluate(inc, candidate, 0.7, 0.7, analysis).statuses) == "BLOCK"
    none = evaluate(inc, inc, 0.7, 1.01, analysis)
    assert none.g3.status == "FAIL"
    assert verdict(none.statuses) == "BLOCK"
    assert evaluate(inc, arm(analysis, invalid=36), 0.7, 0.7, analysis).g4 == "FAIL"
    assert evaluate(inc, arm(analysis, invalid=35), 0.7, 0.7, analysis).g4 == "PASS"


def test_g2_composite_and_family_column(analysis: AnalysisContract) -> None:
    all_pass = {s: (0, 0, 1000) for s in analysis.slices}
    assert gate_g2(all_pass, 0.03).status == "PASS"
    unresolved = {**all_pass, analysis.slices[0]: (0, 0, 30)}
    assert gate_g2(unresolved, 0.03).status == "UNRESOLVED"
    harm = {**unresolved, analysis.slices[1]: (100, 0, 1000)}
    assert gate_g2(harm, 0.03).status == "FAIL"
    # The family confidence is deliberately stricter, even with only one certified option.
    inc = arm(analysis, n=980)
    assert evaluate(inc, inc, 0.7, 0.7, analysis).g2 == "PASS"
    assert evaluate(inc, inc, 0.7, 0.7, analysis, FAMILY_CONFIDENCE).g2 == "UNRESOLVED"


def test_aa_unstable_incumbent_fails_noise_floor(analysis: AnalysisContract) -> None:
    first, repeat = arm(analysis), arm(analysis, wrong=700)
    failed, lines = _noise(first, repeat, analysis)
    assert failed
    assert "outcome flip rate 10.00 pp" in "\n".join(lines)
    assert "G1 FAIL; G2 FAIL" in "\n".join(lines)
    assert verdict(("FAIL", "PASS", "PASS", "PASS"), noise_failed=failed) == "INCONCLUSIVE"
    assert "noise floor not measured" in _noise(first, None, analysis)[1][0]
    assert "WARNING" in "\n".join(_noise(arm(analysis, n=210), arm(analysis, n=210), analysis)[1])


@pytest.mark.parametrize(
    "cost,latency,expected",
    [
        (1.5, 2.0, []),
        (1.50001, 2.0, ["COST"]),
        (1.5, 2.00001, ["LATENCY"]),
        (1.50001, 2.00001, ["COST", "LATENCY"]),
    ],
)
def test_flags_are_strict_ratios_not_gates(cost: float, latency: float, expected: list[str]) -> None:
    assert operational_flags(1.0, cost, 1.0, latency) == expected
    assert verdict(("PASS",) * 4) == "SHIP"


def _save_rows(path: Path, rows: list[ItemRow]) -> None:
    (path / "items.jsonl.gz").write_bytes(
        gzip.compress("".join(r.model_dump_json() + "\n" for r in rows).encode(), mtime=0)
    )


def test_records_deterministic_rounded_short_not_run_and_interfaces(tmp_path: Path) -> None:
    build_golden(tmp_path / "fixture")
    args = load_golden(tmp_path / "fixture")
    one = write_decisions(*args, tmp_path / "one")
    two = write_decisions(*args, tmp_path / "two")
    assert one == two
    assert list(one) == list(DECISIONS)
    for key in one:
        assert (tmp_path / "one" / f"{key}.md").read_bytes() == (tmp_path / "two" / f"{key}.md").read_bytes()
    assert "Reason: no dev gain" in one["D-A2"]
    assert "Reason: budget" in one["D-B2"]
    assert "## Gates" not in one["D-A2"] and "## Gates" not in one["D-B2"]
    assert "not applicable" in one["D-J"] and "not applicable" in one["D-O"]
    assert "not applicable" not in one["D-A1"]
    assert "Wilson" in one["D-A1"] and "0.00 pp" in one["D-A1"]
    assert "Family-adjusted" in one["D-A1"]
    assert "Reasoning tokens/message mean/p95" in one["D-A1"]
    assert "2026-10-21T" not in "".join(one.values())
    assert "started_at" not in "".join(one.values())


@pytest.mark.parametrize("kind", ["hash", "unlisted", "api_error", "retry"])
def test_refuses_bad_provenance_and_invalid_run_before_writing(tmp_path: Path, kind: str) -> None:
    build_golden(tmp_path / "fixture")
    runs, contract, items, groups = load_golden(tmp_path / "fixture")
    path = runs / "golden-luna-none-cert"
    if kind in ("hash", "retry"):
        meta = read_meta(path)
        update = {"prompt_sha256": "changed"} if kind == "hash" else {"retry_errors_in_progress": True}
        (path / "run.json").write_text(meta.model_copy(update=update).model_dump_json(), encoding="utf-8")
    elif kind == "unlisted":
        manifest = load_manifest(runs)
        manifest.runs = [r for r in manifest.runs if r.config_id != "luna-none"]
        save_manifest(runs, manifest)
    else:
        rows = read_rows(path)
        rows[1] = rows[1].model_copy(update={"status": "api_error"})  # 2/210 exceeds 0.5%.
        _save_rows(path, rows)
    out = tmp_path / "decisions"
    with pytest.raises(DecisionRefusal) as exc:
        write_decisions(runs, contract, items, groups, out)
    assert exc.value.problems
    assert not out.exists()


def test_refuses_cert_items_that_differ_from_the_contract(tmp_path: Path) -> None:
    build_golden(tmp_path / "fixture")
    runs, contract, items, groups = load_golden(tmp_path / "fixture")
    out = tmp_path / "decisions"
    with pytest.raises(DecisionRefusal, match="cert items differ"):
        write_decisions(runs, contract, list(items)[::-1], groups, out)  # same items, other split order
    assert not out.exists()


def test_dx_conditions_and_noise_downgrade(tmp_path: Path) -> None:
    build_golden(tmp_path / "fixture")
    runs, contract, items, groups = load_golden(tmp_path / "fixture")
    a = contract.analysis
    assert a is not None
    # Certify the adapted configuration using the same recorded synthetic behavior.
    path = runs / "golden-luna-none-cert"
    meta = read_meta(path)
    adapted_dir = runs / "golden-luna-none-x-cert"
    adapted_dir.mkdir()
    adapted = meta.model_copy(
        update={
            "run_id": adapted_dir.name,
            "config_id": "luna-none-x",
            **contract.configurations["luna-none-x"].model_dump(),
        }
    )
    (adapted_dir / "run.json").write_text(adapted.model_dump_json(), encoding="utf-8")
    _save_rows(adapted_dir, read_rows(path))
    manifest = load_manifest(runs)
    entry = next(r for r in manifest.runs if r.config_id == "luna-none")
    manifest.runs.append(
        entry.model_copy(
            update={
                "run_id": adapted_dir.name,
                "config_id": "luna-none-x",
                **contract.configurations["luna-none-x"].model_dump(),
            }
        )
    )
    manifest.not_run = [r for r in manifest.not_run if r.decision_id != "D-X"]
    save_manifest(runs, manifest)
    budget = a.budget.model_copy(
        update={
            "not_run": {k: v for k, v in a.budget.not_run.items() if k != "D-X"},
            "planned_cert_runs": [*a.budget.planned_cert_runs, "luna-none-x"],
        }
    )
    selected = a.selections.model_copy(update={"dx_iteration": 2})
    contract = contract.model_copy(update={"analysis": a.model_copy(update={"budget": budget, "selections": selected})})
    rendered = write_decisions(runs, contract, items, groups, tmp_path / "out")
    assert "Use adapted prompt SHA-256" in rendered["D-X"]
    assert "dev iteration 2" in rendered["D-X"]
    assert "candidate τ = 0.70" in rendered["D-X"]
    # A genuinely unstable repeat overrides even the Decisions API's G4 BLOCK.
    aa_dir = runs / "golden-inc-aa"
    aa_rows = [row.model_copy(update={"intent": "card_arrival", "confidence": 0.99}) for row in read_rows(aa_dir)]
    _save_rows(aa_dir, aa_rows)
    downgraded = write_decisions(runs, contract, items, groups, tmp_path / "unstable")
    for decision in ("D-A1", "D-B1", "D-J", "D-O", "D-X"):
        assert "**Verdict: INCONCLUSIVE**" in downgraded[decision]
        assert "A/A noise floor FAIL" in downgraded[decision]
    bad = selected.model_copy(update={"dx_prompt_sha256": "other"})
    with pytest.raises(DecisionRefusal, match="adapted prompt hash"):
        write_decisions(
            runs,
            contract.model_copy(update={"analysis": a.model_copy(update={"budget": budget, "selections": bad})}),
            items,
            groups,
            tmp_path / "bad",
        )


def test_naive_swap_hand_count_at_incumbent_threshold(analysis: AnalysisContract) -> None:
    run = arm(analysis, n=210, wrong=21)
    lines = "\n".join(naive_swap(run, 0.7, analysis.slices))
    assert "| overall | 210 | 10.00 pp" in lines
    assert "100.00 pp" in lines
    none = "\n".join(naive_swap(run, 1.01, analysis.slices))
    assert "| overall | 210 | 0.00 pp" in none


def test_operational_flags_and_reported_tokens_never_change_rendered_verdict(tmp_path: Path) -> None:
    build_golden(tmp_path / "fixture")
    args = load_golden(tmp_path / "fixture")
    before = write_decisions(*args, tmp_path / "before")["D-A1"]
    run_dir = args[0] / "golden-luna-none-cert"
    expensive = []
    for row in read_rows(run_dir):
        attempts = [
            attempt.model_copy(update={"usage": attempt.usage.model_copy(update={"output": 1000, "reasoning": 40})})
            for attempt in row.attempts
        ]
        expensive.append(row.model_copy(update={"latency_ms": 1000.0, "attempts": attempts}))
    _save_rows(run_dir, expensive)
    after = write_decisions(*args, tmp_path / "after")["D-A1"]
    assert "**Verdict: BLOCK**" in before and "**Verdict: BLOCK**" in after
    assert "Flags: COST, LATENCY" in after
    assert "40.00/40.00" in after  # Every recorded message has exactly 40 reasoning tokens.


@pytest.mark.parametrize("empty", [False, True])
def test_incomplete_candidate_yields_insufficient_data_not_refusal(tmp_path: Path, empty: bool) -> None:
    build_golden(tmp_path / "fixture")
    args = load_golden(tmp_path / "fixture")
    run_dir = args[0] / "golden-luna-none-cert"
    meta = read_meta(run_dir).model_copy(update={"complete": False, "incomplete_reason": "budget cap"})
    (run_dir / "run.json").write_text(meta.model_dump_json(), encoding="utf-8")
    if empty:
        _save_rows(run_dir, [])
    record = write_decisions(*args, tmp_path / "out")["D-A1"]
    assert "**Verdict: INCONCLUSIVE**" in record
    assert "Insufficient data" in record
    assert "## Gates" not in record
