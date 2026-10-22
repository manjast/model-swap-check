"""Frozen certification decisions (spec §7).

Decision indices 1..7 follow the §1 table: D-A1, D-A2, D-B1, D-B2,
D-J, D-O, D-X. They also key the pre-registered bootstrap seeds.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import NormalDist

import numpy as np
from numpy.typing import NDArray

from swapcheck.budget import NOISE_FLOOR_WARNING
from swapcheck.configs import Configuration, load_configurations
from swapcheck.contract import AnalysisContract, Contract, OrderSensitivity
from swapcheck.cost import Prices, cost_model, load_prices
from swapcheck.data import Item, item_list_hash
from swapcheck.groups import IntentGroups
from swapcheck.manifest import load_manifest, verify_manifest
from swapcheck.outcomes import AnalysisRun, build_run, pair_runs
from swapcheck.records import ItemRow, RunMeta, read_meta, read_rows
from swapcheck.runner import run_validity
from swapcheck.stats import (
    GateName,
    GateResult,
    GateStatus,
    cluster_bootstrap,
    gate_g1,
    gate_g2,
    gate_g3,
    gate_g4,
    sample_size_needed,
)

DECISIONS = ("D-A1", "D-A2", "D-B1", "D-B2", "D-J", "D-O", "D-X")
FAMILY_CONFIDENCE = 1 - 0.05 / 7
NOT_TESTED = (
    "Reasoning efforts above medium; Claude Haiku 4.5; gpt-4.1-mini; Jev 1.14 (jev-preview) "
    "and other decision models (Laya, Kev); live-chat latency limits; multi-turn conversations; "
    "languages other than English; streaming; real production traffic."
)
BoolArray = NDArray[np.bool_]


class DecisionRefusal(RuntimeError):
    """All known certification provenance/validity problems, before any output is written."""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = list(problems)
        super().__init__("decide refused:\n" + "\n".join(f"- {p}" for p in problems))


def candidate_ids(a: AnalysisContract) -> dict[str, str | None]:
    return dict(
        zip(
            DECISIONS,
            (
                "luna-none",
                a.selections.reasoning.get("luna"),
                "haiku55-off",
                a.selections.reasoning.get("haiku55"),
                a.selections.jev_design,
                "luna-dec",
                "luna-none-x",
            ),
            strict=True,
        )
    )


def pp(value: float) -> str:
    return f"{value * 100:.2f} pp"


def counts(candidate: BoolArray, incumbent: BoolArray) -> tuple[int, int, int]:
    return int(np.count_nonzero(candidate & ~incumbent)), int(np.count_nonzero(incumbent & ~candidate)), candidate.size


@dataclass(frozen=True)
class Gates:
    g1: GateResult
    slices: Mapping[str, GateResult]
    g2: GateStatus
    g3: GateResult
    g4: GateStatus

    @property
    def statuses(self) -> tuple[GateStatus, ...]:
        return self.g1.status, self.g2, self.g3.status, self.g4


def evaluate(
    inc: AnalysisRun, cand: AnalysisRun, ti: float, tc: float, a: AnalysisContract, confidence: float = 0.95
) -> Gates:
    iw, cw = inc.auto_mask(ti) & ~inc.correct, cand.auto_mask(tc) & ~cand.correct
    sliced = {s: counts(cw[np.array(cand.slices) == s], iw[np.array(inc.slices) == s]) for s in a.slices}
    g2 = gate_g2(sliced, a.delta_s, confidence)
    valid = sum(s == "ok" for s in cand.status)
    total = sum(s != "api_error" for s in cand.status)
    return Gates(
        gate_g1(*counts(cw, iw), a.delta_w, confidence),
        g2.slices,
        g2.status,
        gate_g3(*counts(cand.auto_mask(tc), inc.auto_mask(ti)), confidence),
        gate_g4(valid, total),
    )


def verdict(statuses: Sequence[GateStatus], *, noise_failed: bool = False) -> str:
    if noise_failed:
        return "INCONCLUSIVE"
    if "FAIL" in statuses:
        return "BLOCK"
    return "SHIP" if all(s == "PASS" for s in statuses) else "INCONCLUSIVE"


def _wilson(k: int, n: int) -> str:
    if not n:
        return "undefined"
    z = NormalDist().inv_cdf(0.975)
    p = k / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    radius = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return f"{pp(p)} [{pp(center - radius)}, {pp(center + radius)}]"


def naive_swap(run: AnalysisRun, tau_inc: float, slices: Sequence[str]) -> list[str]:
    lines = [
        "Two-sided 95% Wilson score intervals (unweighted, descriptive; no verdict).",
        "",
        "| Scope | n | W [95% CI] | A [95% CI] |",
        "|---|---:|---|---|",
    ]
    for name in ("overall", *slices):
        r = run if name == "overall" else run.take([i for i, s in enumerate(run.slices) if s == name])
        auto = r.auto_mask(tau_inc)
        lines.append(
            f"| {name} | {len(r)} | {_wilson(int(np.count_nonzero(auto & ~r.correct)), len(r))} | "
            f"{_wilson(int(np.count_nonzero(auto)), len(r))} |"
        )
    return lines


def _gate_row(name: str, gate: GateResult, family: GateResult) -> str:
    b = gate.bounds
    harm = "" if gate.harm_lower is None else f"; harm L {pp(gate.harm_lower)}"
    return (
        f"| {name} | {pp(b.estimate)} | [{pp(b.lower)}, {pp(b.upper)}]{harm} | "
        f"[{pp(b.wald_lower)}, {pp(b.wald_upper)}] | {pp(gate.margin)} | {gate.status} | {family.status} |"
    )


def _size_line(name: str, c: tuple[int, int, int], margin: float, *, lower: bool = False) -> str:
    size = sample_size_needed(*c, margin, direction="lower" if lower else "upper")
    return f"- {name}: total paired n needed = {size.n if size.n is not None else size.reason}."


def _number(value: float | None) -> str:
    return "not reported" if value is None else f"{value:.2f}"


def _latency(rows: Sequence[ItemRow], q: float) -> float | None:
    values = [r.latency_ms for r in rows if r.latency_ms is not None]
    return float(np.quantile(values, q, method="higher")) if values else None


def _operations(
    inc_meta: RunMeta,
    cand_meta: RunMeta,
    inc_rows: Sequence[ItemRow],
    cand_rows: Sequence[ItemRow],
    configs: Mapping[str, Configuration],
    prices: Prices,
) -> list[str]:
    models = [
        cost_model(configs[m.config_id], rows, m.warmups, prices) if rows else None
        for m, rows in ((inc_meta, inc_rows), (cand_meta, cand_rows))
    ]
    lines = [
        "## Cost and speed (not gated)",
        "",
        "| Arm | Billed $/1,000 | Steady $/1,000 | Sparse $/1,000 | "
        "Latency p50/p95 ms | Reasoning tokens/message mean/p95 |",
        "|---|---:|---:|---:|---|---|",
    ]
    for model, rows in zip(models, (inc_rows, cand_rows), strict=True):
        if model is None:
            name = inc_meta.config_id if rows is inc_rows else cand_meta.config_id
            lines.append(f"| {name} | undefined (no items) | undefined | undefined | not reported | not reported |")
            continue
        lines.append(
            f"| {model.config_id} | {_number(model.billed_per_1000)} | {_number(model.steady_per_1000)} | "
            f"{_number(model.sparse_per_1000)} | "
            f"{_number(_latency(rows, 0.5))}/{_number(_latency(rows, 0.95))} | "
            f"{_number(model.reasoning_mean)}/{_number(model.reasoning_p95)} |"
        )
    flags = operational_flags(
        models[0].steady_per_1000 if models[0] else None,
        models[1].steady_per_1000 if models[1] else None,
        _latency(inc_rows, 0.95),
        _latency(cand_rows, 0.95),
    )
    lines += [
        "",
        "Flags: " + (", ".join(flags) if flags else "none") + ". Flags never change the verdict.",
        "Latency is indicative, not a live-chat limit; all calls and retries are included in billed cost.",
    ]
    for label, rows in (("incumbent", inc_rows), ("candidate", cand_rows)):
        for cached in (False, True):
            subset = [r for r in rows if bool(r.attempts and r.attempts[-1].usage.cache_read) == cached]
            lines.append(
                f"- {label}, {'with' if cached else 'without'} cache reads: latency p50/p95 ms "
                f"{_number(_latency(subset, 0.5))}/{_number(_latency(subset, 0.95))}."
            )
    return lines


def operational_flags(
    inc_cost: float | None, cand_cost: float | None, inc_p95: float | None, cand_p95: float | None
) -> list[str]:
    flags = []
    if inc_cost is not None and cand_cost is not None and cand_cost > 1.5 * inc_cost:
        flags.append("COST")
    if inc_p95 is not None and cand_p95 is not None and cand_p95 > 2 * inc_p95:
        flags.append("LATENCY")
    return flags


def _noise(inc: AnalysisRun, aa: AnalysisRun | None, a: AnalysisContract) -> tuple[bool, list[str]]:
    if aa is None:
        return False, [NOISE_FLOOR_WARNING]
    paired = pair_runs(inc, aa)
    first, repeat = paired.runs
    if not len(first) or set(first.slices) != set(a.slices) or not aa.complete or not inc.complete:
        return False, ["WARNING: A/A noise floor UNRESOLVED (insufficient data)."]
    g = evaluate(first, repeat, a.incumbent_tau, a.incumbent_tau, a)
    auto1, auto2 = first.auto_mask(a.incumbent_tau), repeat.auto_mask(a.incumbent_tau)
    flip = (auto1 != auto2) | (auto1 & auto2 & (first.correct != repeat.correct))
    failed = "FAIL" in (g.g1.status, g.g2)
    lines = [
        f"A/A G1 {g.g1.status}; G2 {g.g2}; outcome flip rate {pp(float(np.mean(flip)))}; "
        f"paired n={len(first)}, dropped={paired.dropped}."
    ]
    if failed:
        lines.append("A/A noise floor FAIL: every verdict is INCONCLUSIVE.")
    elif "UNRESOLVED" in (g.g1.status, g.g2):
        lines.append("WARNING: A/A noise floor UNRESOLVED.")
    return failed, lines


def _order_sensitivity(cfg: str, s: OrderSensitivity | None) -> str:
    """The pilot's option-order measurement; above 5% it is a stated limitation (spec §14)."""
    if s is None:
        return f"Option-order sensitivity of `{cfg}`: not recorded."
    line = f"Option-order sensitivity (pilot): {s.changed}/{s.items} choices changed with the 50 intents reversed."
    if 20 * s.changed > s.items:  # share > 5 %, compared exactly
        line += " Limitation: above 5%, so this verdict holds for the catalog order used here only."
    return line


def _render(
    decision: str,
    index: int,
    cfg: str,
    inc: AnalysisRun,
    cand: AnalysisRun,
    a: AnalysisContract,
    items: Sequence[Item],
    noise_failed: bool,
    noise: list[str],
    inc_meta: RunMeta,
    cand_meta: RunMeta,
    inc_rows: Sequence[ItemRow],
    cand_rows: Sequence[ItemRow],
    configs: Mapping[str, Configuration],
    prices: Prices,
) -> str:
    paired = pair_runs(inc, cand)
    ir, cr = paired.runs
    tc, ti = a.configurations[cfg].tau, a.incumbent_tau
    lines = [f"# {decision}: inc → {cfg}", "", f"Analysis code: `{a.code_version}`; decision_index={index}.", ""]
    enough = inc.complete and cand.complete and len(ir) > 0 and set(ir.slices) == set(a.slices)
    gates = evaluate(ir, cr, ti, tc, a) if enough else None
    result = verdict(gates.statuses, noise_failed=noise_failed) if gates else "INCONCLUSIVE"
    lines += [f"**Verdict: {result}**", "", f"Conditions: candidate τ = {tc:.2f}; incumbent τ = {ti:.2f}."]
    if decision == "D-X":
        lines.append(
            f"Use adapted prompt SHA-256 `{a.selections.dx_prompt_sha256}` "
            f"(dev iteration {a.selections.dx_iteration}), not the incumbent prompt."
        )
    if decision in ("D-J", "D-O"):
        lines.append(_order_sensitivity(cfg, a.order_sensitivity.get(cfg)))
    lines += [
        f"Paired n={len(ir)}; dropped API-error/absent items={paired.dropped}.",
        f"Frozen dev W={pp(a.configurations[cfg].dev_w)}; A={pp(a.configurations[cfg].dev_a)}; "
        f"power at frozen margins={pp(a.power[decision])}.",
        "",
    ]
    if gates:
        family = evaluate(ir, cr, ti, tc, a, FAMILY_CONFIDENCE)
        lines += [
            "## Gates",
            "",
            "Family-adjusted column: one-sided 1 - 0.05/7 over all seven decisions (including NOT RUN).",
            "",
            "| Gate | Estimate | Tango [L,U] | Wald [L,U] | Margin | 95% status | Family-adjusted |",
            "|---|---:|---|---|---:|---|---|",
            _gate_row("G1 W overall", gates.g1, family.g1),
            f"| G2 W slices | — | see slice table | — | {pp(a.delta_s)} | {gates.g2} | {family.g2} |",
            _gate_row("G3 A overall", gates.g3, family.g3),
            f"| G4 V | {pp(sum(s == 'ok' for s in cr.status) / len(cr))} | — | — | 99.50 pp | "
            f"{gates.g4} | {family.g4} |",
            "",
            "### Slices",
            "",
            "| Slice | Estimate | Tango [L,U] | Wald [L,U] | Margin | 95% status | Family-adjusted |",
            "|---|---:|---|---|---:|---|---|",
        ]
        lines += [_gate_row(s, gates.slices[s], family.slices[s]) for s in a.slices]
        iw, cw = ir.auto_mask(ti) & ~ir.correct, cr.auto_mask(tc) & ~cr.correct
        lines += ["", "### Sample sizes for UNRESOLVED gates", ""]
        sizes = []
        if gates.g1.status == "UNRESOLVED":
            sizes.append(_size_line("G1", counts(cw, iw), a.delta_w))
        for s, gate in gates.slices.items():
            if gate.status == "UNRESOLVED":
                mask = np.array(ir.slices) == s
                sizes.append(_size_line(f"G2/{s}", counts(cw[mask], iw[mask]), a.delta_s))
        if gates.g3.status == "UNRESOLVED":
            sizes.append(_size_line("G3", counts(cr.auto_mask(tc), ir.auto_mask(ti)), -0.03, lower=True))
        lines += sizes or ["None."]
        lines += ["", "## Cluster-bootstrap sensitivity", "", "10,000 intent-cluster resamples; descriptive only."]
        changes = []
        bootstrap_specs: tuple[tuple[GateName, BoolArray, BoolArray, float | None], ...] = (
            ("G1", cw, iw, a.delta_w),
            ("G2", cw, iw, a.delta_s),
            ("G3", cr.auto_mask(tc), ir.auto_mask(ti), None),
        )
        for bootstrap_gate, cm, im, margin in bootstrap_specs:
            sensitivity = cluster_bootstrap(
                ir.truth, ir.slices, cm, im, a.slices, gate=bootstrap_gate, decision_index=index, margin=margin
            )
            if sensitivity.changed:
                changes.append(f"- {bootstrap_gate}: {sensitivity.original_status} → {sensitivity.bootstrap_status}.")
        lines += changes or ["No gate status changes."]
    else:
        lines += ["Insufficient data: incomplete run or missing paired slices; no gate estimates are asserted."]
    lines += [
        "",
        "## Noise floor",
        "",
        *noise,
        "Dev wrong-auto discordance used for power/margins:",
        "",
        "| Slice | Frozen dev discordance |",
        "|---|---:|",
        *[
            f"| {s} | "
            + (
                pp(a.dev_discordance.get(decision, a.dev_discordance.get("llm", {}))[s])
                if s in a.dev_discordance.get(decision, a.dev_discordance.get("llm", {}))
                else "not recorded"
            )
            + " |"
            for s in a.slices
        ],
        "",
        "## Naive swap at incumbent τ",
        "",
    ]
    lines += (
        ["not applicable (decision interface, not a model-ID swap)."]
        if decision in ("D-J", "D-O")
        else naive_swap(cr, ti, a.slices)
    )
    lines += [
        "",
        "## Newly wrong auto-routes",
        "",
        "Messages are quoted from the split under test; Banking77 texts are CC BY 4.0 (Casanueva et al., 2020).",
    ]
    iw, cw = ir.auto_mask(ti) & ~ir.correct, cr.auto_mask(tc) & ~cr.correct
    newly = {cr.item_ids[i]: i for i in np.flatnonzero(cw & ~iw)}
    errors = sorted((item for item in items if item.item_id in newly), key=lambda item: item.digest)[:20]
    for item in errors:
        i = newly[item.item_id]
        lines.append(
            f"- `{item.item_id}` truth=`{item.intent}` candidate=`{cr.intent[i]}`: "
            + json.dumps(item.text, ensure_ascii=True)
        )
    if not errors:
        lines.append("None.")
    lines += [
        "",
        *_operations(inc_meta, cand_meta, inc_rows, cand_rows, configs, prices),
        "",
        "## Not tested",
        "",
        NOT_TESTED,
        "",
    ]
    return "\n".join(lines)


def write_decisions(
    runs_dir: Path,
    contract: Contract,
    items: Sequence[Item],
    groups: IntentGroups,
    output_dir: Path,
    *,
    configs: Mapping[str, Configuration] | None = None,
    prices: Prices | None = None,
) -> dict[str, str]:
    """Verify all inputs before writing deterministic records; items are injectable for offline replay."""
    a = contract.analysis
    if a is None:
        raise DecisionRefusal(["contract has no frozen analysis"])
    manifest = load_manifest(runs_dir)
    problems = verify_manifest(manifest, contract, runs_dir)
    # Truth is joined from `items`; runs are checked against the contract, so the items must be too.
    if item_list_hash(list(items)) != contract.item_lists.get("cert"):
        problems.append("cert items differ from the contract's cert item list")
    candidates = candidate_ids(a)
    not_run = {n.decision_id: n.reason for n in manifest.not_run if n.contract_tag == contract.tag}
    if not_run != a.budget.not_run:
        problems.append("manifest NOT RUN decisions differ from frozen budget plan")
    loaded: dict[tuple[str, str], tuple[RunMeta, list[ItemRow]]] = {}
    for entry in manifest.runs:
        if entry.contract_tag != contract.tag or entry.split not in ("cert", "aa"):
            continue
        if not (runs_dir / entry.run_id / "run.json").exists():
            continue
        meta, rows = read_meta(runs_dir / entry.run_id), read_rows(runs_dir / entry.run_id)
        ok, why = run_validity(meta, rows)
        # Budget-stopped runs yield insufficient-data decisions, not false rejection of the analysis.
        if not ok and (meta.complete or meta.retry_errors_in_progress):
            problems.append(why)
        loaded[entry.config_id, entry.split] = meta, rows
    for decision, cfg in candidates.items():
        if decision in not_run:
            continue
        if cfg is None or (cfg, "cert") not in loaded:
            problems.append(f"{decision}: required cert run missing ({cfg})")
        elif cfg not in a.configurations:
            problems.append(f"{decision}: missing frozen calibration for {cfg}")
        if decision not in a.power:
            problems.append(f"{decision}: missing frozen power")
    if ("inc", "cert") not in loaded:
        problems.append("required incumbent cert run missing")
    if "aa" in a.budget.planned_cert_runs and ("inc", "aa") not in loaded:
        problems.append("planned A/A run missing")
    if "D-X" not in not_run:
        adapted = contract.configurations.get("luna-none-x")
        if a.selections.dx_iteration not in range(4) or not a.selections.dx_prompt_sha256:
            problems.append("D-X adapted prompt selection is not frozen")
        elif adapted is None or adapted.prompt_sha256 != a.selections.dx_prompt_sha256:
            problems.append("D-X adapted prompt hash differs from frozen selection")
    if problems:
        raise DecisionRefusal(problems)
    config_map = load_configurations() if configs is None else configs
    price_map = load_prices() if prices is None else prices
    im, rows = loaded["inc", "cert"]
    inc = build_run(items, rows, split="cert", groups=groups, complete=im.complete)
    aa = None
    if ("inc", "aa") in loaded:
        am, ar = loaded["inc", "aa"]
        aa = build_run(items, ar, split="cert", groups=groups, complete=am.complete)
        # Same truth join, but only the A/A item IDs participate in the comparison.
        aa_ids = set(aa.item_ids)
        inc_aa = inc.take([i for i, item_id in enumerate(inc.item_ids) if item_id in aa_ids])
    else:
        inc_aa = inc
    failed, noise = _noise(inc_aa, aa, a)
    rendered = {}
    for index, decision in enumerate(DECISIONS, 1):
        cfg = candidates[decision]
        if decision in not_run:
            dev = {
                name: {"tau": cal.tau, "W": pp(cal.dev_w), "A": pp(cal.dev_a)}
                for name, cal in sorted(a.configurations.items())
            }
            rendered[decision] = (
                f"# {decision}\n\n**Verdict: NOT RUN**\n\nReason: {not_run[decision]}.\n\n"
                "Frozen dev numbers:\n```json\n" + json.dumps(dev, sort_keys=True) + "\n```\n"
            )
            continue
        assert cfg is not None
        cm, candidate_rows = loaded[cfg, "cert"]
        cand = build_run(
            items, candidate_rows, split="cert", groups=groups, noul=cfg == "jev-noul", complete=cm.complete
        )
        rendered[decision] = _render(
            decision,
            index,
            cfg,
            inc,
            cand,
            a,
            items,
            failed,
            noise,
            im,
            cm,
            rows,
            candidate_rows,
            config_map,
            price_map,
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    for decision, text in rendered.items():
        (output_dir / f"{decision}.md").write_text(text, encoding="utf-8")
    return rendered
