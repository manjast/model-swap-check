"""Own-threshold dev discordance for the final LLM certification plan (§7.3)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np

from swapcheck.configs import Configuration, load_configurations
from swapcheck.contract import Contract
from swapcheck.data import Item
from swapcheck.groups import IntentGroups
from swapcheck.outcomes import AnalysisRun, build_run, pair_runs
from swapcheck.records import read_meta, read_rows

P_DISC_FLOOR = 0.01


def planned_llm_configs(contract: Contract, configs: Mapping[str, Configuration]) -> list[str]:
    """Exclude incumbent, interfaces and configurations dropped before cert."""
    if contract.analysis is None:
        raise ValueError("contract has no analysis plan")
    return [
        cid
        for cid in contract.analysis.budget.planned_cert_runs
        if cid not in {"inc", "aa"} and not configs[cid].is_decision_interface
    ]


def worst_dev_discordance(
    runs: Mapping[str, AnalysisRun],
    contract: Contract,
    *,
    configs: Mapping[str, Configuration] | None = None,
) -> dict[str, float]:
    """Unweighted per-slice wrong-auto XOR, paired without API errors.

    Each candidate uses its frozen own tau, the incumbent its production tau.
    The maximum is taken independently per slice, then floored at one percent.
    """
    selected = planned_llm_configs(contract, load_configurations() if configs is None else configs)
    if not selected:
        raise ValueError("final cert plan has no LLM candidates")
    return _discordance(runs, contract, selected)


def _discordance(runs: Mapping[str, AnalysisRun], contract: Contract, selected: Sequence[str]) -> dict[str, float]:
    analysis = contract.analysis
    if analysis is None:
        raise ValueError("contract has no analysis plan")
    if not selected:
        raise ValueError("discordance requires a candidate")
    result = dict.fromkeys(analysis.slices, P_DISC_FLOOR)
    for cid in selected:
        incumbent, candidate = runs["inc"], runs[cid]
        for run in (incumbent, candidate):
            if run.split != "dev" or not run.complete:
                raise ValueError(f"{cid}: discordance requires complete dev runs")
            if len(set(run.item_ids)) != len(run):
                raise ValueError(f"{cid}: duplicate dev item IDs")
        if set(incumbent.item_ids) != set(candidate.item_ids):
            raise ValueError(f"{cid}: dev item sets differ")
        paired = pair_runs(incumbent, candidate)
        inc, cand = paired.runs
        wrong_inc = inc.auto_mask(analysis.incumbent_tau) & ~inc.correct
        wrong_cand = cand.auto_mask(analysis.configurations[cid].tau) & ~cand.correct
        discordant = wrong_inc ^ wrong_cand
        for name in analysis.slices:
            mask = np.array([s == name for s in inc.slices], dtype=np.bool_)
            n = int(np.count_nonzero(mask))
            if not n:
                raise ValueError(f"{cid}: no paired dev items in slice {name}")
            result[name] = max(result[name], int(np.count_nonzero(discordant & mask)) / n)
    return result


def interface_dev_discordance(
    runs: Mapping[str, AnalysisRun],
    contract: Contract,
    *,
    configs: Mapping[str, Configuration] | None = None,
) -> dict[str, dict[str, float]]:
    """Separate power inputs for planned interfaces, never pooled into LLM margins."""
    configurations = load_configurations() if configs is None else configs
    if contract.analysis is None:
        raise ValueError("contract has no analysis plan")
    return {
        "D-J" if configurations[cid].provider == "typesafe" else "D-O": _discordance(runs, contract, [cid])
        for cid in contract.analysis.budget.planned_cert_runs
        if cid != "aa" and configurations[cid].is_decision_interface  # `aa` is `inc` on the A/A split
    }


def write_pdisc(
    runs_dir: Path,
    contract: Contract,
    items: Sequence[Item],
    groups: IntentGroups,
    path: Path,
    *,
    configs: Mapping[str, Configuration] | None = None,
) -> dict[str, float]:
    """Load unique complete dev runs and write the power script's slice->float JSON."""
    configurations = load_configurations() if configs is None else configs
    if contract.analysis is None:
        raise ValueError("contract has no analysis plan")
    required = {"inc", *(cid for cid in contract.analysis.budget.planned_cert_runs if cid != "aa")}
    runs: dict[str, AnalysisRun] = {}
    for meta_path in sorted(runs_dir.glob("*/run.json")):
        meta = read_meta(meta_path.parent)
        if meta.split != "dev" or meta.config_id not in required:
            continue
        # Every D-X iteration is a `luna-none-x` dev run; only the frozen selection counts (§8.3).
        if meta.config_id == "luna-none-x" and meta.prompt_sha256 != contract.analysis.selections.dx_prompt_sha256:
            continue
        if meta.config_id in runs:
            raise ValueError(f"multiple dev runs for {meta.config_id}")
        if not meta.complete or meta.retry_errors_in_progress:
            raise ValueError(f"{meta.config_id}: dev run is incomplete")
        rows = read_rows(meta_path.parent)
        if {row.item_id for row in rows} != {item.item_id for item in items}:
            raise ValueError(f"{meta.config_id}: dev item set differs from supplied split")
        runs[meta.config_id] = build_run(
            items, rows, split="dev", groups=groups, noul=configurations[meta.config_id].jev_design == "noul"
        )
    missing = required - runs.keys()
    if missing:
        raise ValueError(f"missing dev runs: {sorted(missing)}")
    result = worst_dev_discordance(runs, contract, configs=configurations)
    interfaces = interface_dev_discordance(runs, contract, configs=configurations)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for decision, values in interfaces.items():
        sibling = path.with_name(f"{path.stem}.{decision}.json")
        sibling.write_text(json.dumps(values, indent=2) + "\n", encoding="utf-8")
    return result
