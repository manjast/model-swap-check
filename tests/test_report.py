"""Own-tau, final-plan per-slice discordance regression oracles (§7.3)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from swapcheck import cli, report
from swapcheck.configs import load_configurations
from swapcheck.contract import AnalysisContract, Calibration, Contract
from swapcheck.data import Item
from swapcheck.groups import IntentGroups
from swapcheck.outcomes import AnalysisRun, build_run
from swapcheck.records import ItemRow
from swapcheck.report import worst_dev_discordance

GROUPS = IntentGroups({"cards": ["a"], "cash": ["b"]}, ["oos"])
ITEMS = [Item(str(i), "synthetic", intent) for i, intent in enumerate(["a", "a", "b", "b", "oos", "oos"])]


def contract() -> Contract:
    return Contract(
        tag="contract-v1",
        configurations={},
        item_lists={},
        analysis=AnalysisContract.model_validate(
            {
                "incumbent_tau": 0.7,
                "configurations": {
                    cid: {"tau": 0.9, "dev_w": 0.0, "dev_a": 0.0} for cid in ["luna-none", "haiku55-off"]
                },
                "dev_counts": {},
                "cert_counts": {},
                "delta_w": 0.01,
                "delta_s": 0.03,
                "power": {},
                "slices": list(GROUPS.slices),
                "seeds": {},
                "code_version": "test",
                "budget": {
                    "planned_cert_runs": ["inc", "luna-none", "aa", "haiku55-off", "jev-c51", "luna-dec"],
                    "drop_order": ["luna-medium"],
                    "not_run": {"D-A2": "budget"},
                },
                "selections": {
                    "reasoning": {},
                    "jev_design": "c51",
                    "dx_iteration": 0,
                    "dx_prompt_sha256": "test",
                    "records": {},
                },
                "order_sensitivity": {},
                "policy": {},
            }
        ),
    )


def run(predictions: list[tuple[str, float]], *, error: int | None = None) -> AnalysisRun:
    rows = [
        ItemRow(
            item_id=item.item_id,
            status="api_error" if i == error else "ok",
            error_code=None,
            stop_reason=None,
            raw_output=None,
            intent=intent,
            confidence=confidence,
            probabilities=None,
            match_probability=None,
            case_normalized=False,
            latency_ms=None,
            request_id=None,
            model_id=None,
            attempts=[],
        )
        for i, (item, (intent, confidence)) in enumerate(zip(ITEMS, predictions, strict=True))
    ]
    return build_run(ITEMS, rows, split="dev", groups=GROUPS)


def test_worst_per_slice_own_tau_excludes_interfaces_and_dropped() -> None:
    baseline = [("out_of_scope" if item.intent == "oos" else item.intent, 0.99) for item in ITEMS]
    # A below its own tau must not become wrong, even though it exceeds tau_inc.
    a = [("b", 0.8), ("b", 0.95), ("a", 0.95), ("b", 0.95), ("out_of_scope", 1), ("out_of_scope", 1)]
    b = [("a", 0.95), ("a", 0.95), ("a", 0.95), ("a", 0.95), ("out_of_scope", 1), ("out_of_scope", 1)]
    runs = {"inc": run(baseline), "luna-none": run(a), "haiku55-off": run(b)}
    # Excluded runs need neither data nor a calibrated threshold.
    assert worst_dev_discordance(runs, contract()) == {"cards": 0.5, "cash": 1.0, "out_of_scope": 0.01}


def test_pairwise_api_errors_are_removed_and_rows_are_id_aligned() -> None:
    baseline = [("out_of_scope" if item.intent == "oos" else item.intent, 1.0) for item in ITEMS]
    predictions = [("b", 1.0), ("a", 1.0), ("b", 1.0), ("b", 1.0), ("out_of_scope", 1), ("out_of_scope", 1)]
    a = run(predictions, error=1).take([5, 4, 3, 2, 1, 0])
    result = worst_dev_discordance({"inc": run(baseline), "luna-none": a, "haiku55-off": run(baseline)}, contract())
    assert result == {"cards": 1.0, "cash": 0.01, "out_of_scope": 0.01}
    assert json.loads(json.dumps(result)) == result  # power.py consumes a bare slice->float mapping


def test_missing_analysis_and_unknown_analysis_fields_refuse() -> None:
    old = Contract(tag="old", configurations={}, item_lists={})
    assert old.analysis is None
    with pytest.raises(ValueError, match="no analysis"):
        worst_dev_discordance({}, old)
    analysis = contract().analysis
    assert analysis is not None
    with pytest.raises(ValidationError, match="extra_forbidden"):
        AnalysisContract.model_validate(analysis.model_dump() | {"typo": 1})


def test_report_and_decide_cli_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: list[argparse.Namespace] = []

    def capture(args: argparse.Namespace) -> int:
        seen.append(args)
        return 0

    monkeypatch.setattr(cli, "cmd_report", capture)
    monkeypatch.setattr(cli, "cmd_decide", capture)
    assert cli.main(["report", "--pdisc-json", str(tmp_path / "p.json")]) == 0
    assert (
        cli.main(["decide", "--runs-dir", str(tmp_path), "--contract", "frozen.yaml", "--output-dir", "rendered"]) == 0
    )
    assert seen[0].pdisc_json == tmp_path / "p.json"
    assert seen[1].runs_dir == tmp_path
    assert seen[1].contract == Path("frozen.yaml")
    assert seen[1].output_dir == Path("rendered")
    assert load_configurations()["luna-dec"].is_decision_interface


def test_interface_power_files_separate_and_noul_eligible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    frozen = contract()
    assert frozen.analysis is not None
    frozen.analysis.budget.planned_cert_runs.remove("jev-c51")
    frozen.analysis.budget.planned_cert_runs.append("jev-noul")
    for cid in ["jev-noul", "luna-dec"]:
        frozen.analysis.configurations[cid] = Calibration(tau=0.9, dev_w=0, dev_a=0)
    for cid in frozen.analysis.budget.planned_cert_runs:
        directory = tmp_path / cid
        directory.mkdir()
        (directory / "run.json").write_text("{}", encoding="utf-8")

    def metadata(directory: Path) -> SimpleNamespace:
        return SimpleNamespace(split="dev", config_id=directory.name, complete=True, retry_errors_in_progress=False)

    def rows(directory: Path) -> list[ItemRow]:
        return [
            ItemRow(
                item_id=item.item_id,
                status="ok",
                error_code=None,
                stop_reason=None,
                raw_output=None,
                intent="b"
                if directory.name in {"jev-noul", "luna-dec"}
                else ("out_of_scope" if item.intent == "oos" else item.intent),
                confidence=1,
                probabilities=None,
                match_probability=0.49,
                case_normalized=False,
                latency_ms=None,
                request_id=None,
                model_id=None,
                attempts=[],
            )
            for item in ITEMS
        ]

    monkeypatch.setattr(report, "read_meta", metadata)
    monkeypatch.setattr(report, "read_rows", rows)
    target = tmp_path / "pdisc.json"
    pooled = report.write_pdisc(tmp_path, frozen, ITEMS, GROUPS, target)
    assert pooled == dict.fromkeys(GROUPS.slices, 0.01)
    assert json.loads((tmp_path / "pdisc.D-J.json").read_text()) == pooled
    assert json.loads((tmp_path / "pdisc.D-O.json").read_text()) == {"cards": 1.0, "cash": 0.01, "out_of_scope": 1.0}
    # Dropping the interface removes its required run and its separate output.
    frozen.analysis.budget.planned_cert_runs.remove("luna-dec")
    other = tmp_path / "dropped.json"
    report.write_pdisc(tmp_path, frozen, ITEMS, GROUPS, other)
    assert not (tmp_path / "dropped.D-O.json").exists()


@pytest.mark.parametrize(("iteration", "selected_run"), [(2, "dx-2"), (0, "none")])
def test_dx_uses_only_the_frozen_iteration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, iteration: int, selected_run: str
) -> None:
    """Iteration 0 is the incumbent prompt: its dev run is luna-none's, and no luna-none-x run counts."""
    frozen = contract()
    assert frozen.analysis is not None
    frozen.analysis.budget.planned_cert_runs[:] = ["inc", "luna-none-x"]
    frozen.analysis.configurations["luna-none-x"] = Calibration(tau=0.9, dev_w=0, dev_a=0)
    selections = frozen.analysis.selections.model_copy(
        update={"dx_iteration": iteration, "dx_prompt_sha256": "incumbent" if iteration == 0 else "iteration-2"}
    )
    frozen = frozen.model_copy(update={"analysis": frozen.analysis.model_copy(update={"selections": selections})})
    runs = {
        "inc": "incumbent",
        "none": "incumbent",
        "dx-1": "iteration-1",
        "dx-2": "iteration-2",
        "dx-3": "iteration-3",
    }
    for name in runs:
        (tmp_path / name).mkdir()
        (tmp_path / name / "run.json").write_text("{}", encoding="utf-8")

    def metadata(directory: Path) -> SimpleNamespace:
        config_id = {"inc": "inc", "none": "luna-none"}.get(directory.name, "luna-none-x")
        return SimpleNamespace(
            split="dev",
            config_id=config_id,
            prompt_sha256=runs[directory.name],
            complete=True,
            retry_errors_in_progress=False,
        )

    def rows(directory: Path) -> list[ItemRow]:
        # The incumbent is always right; the selected iteration alone misroutes the two `cards` items to `b`.
        wrong_cards = directory.name == selected_run
        return [
            ItemRow(
                item_id=item.item_id,
                status="ok",
                error_code=None,
                stop_reason=None,
                raw_output=None,
                intent="b"
                if wrong_cards and item.intent == "a"
                else "out_of_scope"
                if item.intent == "oos"
                else item.intent,
                confidence=1,
                probabilities=None,
                match_probability=None,
                case_normalized=False,
                latency_ms=None,
                request_id=None,
                model_id=None,
                attempts=[],
            )
            for item in ITEMS
        ]

    monkeypatch.setattr(report, "read_meta", metadata)
    monkeypatch.setattr(report, "read_rows", rows)
    pooled = report.write_pdisc(tmp_path, frozen, ITEMS, GROUPS, tmp_path / "pdisc.json")
    assert pooled == {"cards": 1.0, "cash": 0.01, "out_of_scope": 0.01}
