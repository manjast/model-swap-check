"""M4 dev analysis (docs/spec.md §3.4, §6, §7.3, §8, §9.5): the competence check, dev status between runs,
D-X error counts and the contract freeze. Prints counts, run IDs and intent names only, never a message text
(§2.5).

Usage:
    python analysis/dev.py competence        # §3.4 on the inc dev run; exit 1 if the incumbent does not pass
    python analysis/dev.py status            # every dev run: validity, cost, own tau, weighted dev W and A
    python analysis/dev.py dx-errors RUN_ID  # D-X input: error counts by (truth, answer) at the run's own tau
    python analysis/dev.py dx-use N          # check prompts/dx/iteration-N.md and make it prompts/luna-none-x.md
    python analysis/dev.py freeze            # selections, budget plan and margins -> contracts/contract-v1.yaml
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import numpy as np
import power
import yaml
from pilot import latest_pilot_runs, order_changes, table

from swapcheck import budget as budget_mod
from swapcheck import cost, data, prompt
from swapcheck.baseline import CompetenceCheck, check_competence
from swapcheck.calibrate import Calibration, VoidExperiment, fit_candidate, fit_incumbent
from swapcheck.configs import Configuration, load_configurations
from swapcheck.contract import (
    CONTRACT_PATH,
    AnalysisContract,
    BudgetPlan,
    Contract,
    ContractConfiguration,
    OrderSensitivity,
    SelectionRecords,
    load_contract,
)
from swapcheck.contract import Calibration as FrozenCalibration
from swapcheck.freeze import CONTRACT_TAG, head_commit
from swapcheck.groups import OUT_OF_SCOPE, REPO_ROOT, IntentGroups, load_groups
from swapcheck.outcomes import AnalysisRun, build_run, dev_weights, weighted_rates
from swapcheck.records import ItemRow, RunMeta, read_meta, read_rows
from swapcheck.report import discordance, write_pdisc
from swapcheck.runner import run_validity
from swapcheck.schema import schema_sha256
from swapcheck.selection import (
    GainResult,
    IterationResult,
    ReasoningSelection,
    Vendor,
    select_adaptation,
    select_jev,
    select_reasoning,
)

SEED = 20261021  # §7.3 power and §7.4 bootstrap; §8.1 adds its own indices to it
POWER_SIMS = 4000
POLICY_LIMIT = Fraction(1, 50)  # §7.8, the registered 2% limit
REQUIRED = ("jev-c51", "jev-noul", "luna-dec", "luna-none", "haiku55-off")
LEVELS = ("luna-low", "luna-medium", "haiku55-low", "haiku55-medium")
VENDORS: tuple[tuple[Vendor, str, budget_mod.Vendor], ...] = (
    ("luna", "luna-none", "openai"),
    ("haiku55", "haiku55-off", "anthropic"),
)


@dataclass(frozen=True)
class DevRun:
    meta: RunMeta
    rows: list[ItemRow]
    run: AnalysisRun


@dataclass(frozen=True)
class Inputs:
    runs_dir: Path
    splits: dict[str, list[data.Item]]
    groups: IntentGroups
    configs: dict[str, Configuration]
    dev_counts: dict[str, int]
    cert_counts: dict[str, int]
    runs: list[DevRun]  # every dev run, in start order


def load(runs_dir: Path) -> Inputs:
    groups = load_groups()
    splits = data.load_splits(groups)
    configs = load_configurations()
    runs = []
    for run_dir in (p for p in runs_dir.iterdir() if (p / "run.json").exists()):
        meta = read_meta(run_dir)
        if meta.split != "dev":
            continue
        rows = read_rows(run_dir)
        noul = configs[meta.config_id].jev_design == "noul"
        run = build_run(splits["dev"], rows, split="dev", groups=groups, noul=noul, complete=meta.complete)
        runs.append(DevRun(meta, rows, run))
    runs.sort(key=lambda r: (r.meta.started_at, r.meta.run_id))
    return Inputs(
        runs_dir,
        splits,
        groups,
        configs,
        dict(sorted(Counter(i.intent for i in splits["dev"]).items())),
        dict(sorted(Counter(i.intent for i in splits["cert"]).items())),
        runs,
    )


def find(inputs: Inputs, config_id: str, prompt_sha256: str | None = None) -> DevRun | None:
    """The one dev run of a configuration (and prompt, for D-X iterations); several are an error to resolve."""
    found = [r for r in inputs.runs if r.meta.config_id == config_id and prompt_sha256 in (None, r.meta.prompt_sha256)]
    if len(found) > 1:
        raise SystemExit(f"several dev runs for {config_id}: {', '.join(r.meta.run_id for r in found)}")
    return found[0] if found else None


def valid(run: DevRun) -> DevRun:
    ok, why = run_validity(run.meta, run.rows)
    if not ok:
        raise SystemExit(why)
    return run


def require(inputs: Inputs, config_id: str, prompt_sha256: str | None = None) -> DevRun:
    run = find(inputs, config_id, prompt_sha256)
    if run is None:
        raise SystemExit(
            f"no dev run for {config_id}" + (f" with prompt {prompt_sha256[:12]}" if prompt_sha256 else "")
        )
    return valid(run)


def usable(run: AnalysisRun) -> AnalysisRun:
    """The items with an outcome: an API error has none (§5), so it carries no weight in calibration."""
    return run.take([i for i, status in enumerate(run.status) if status != "api_error"])


def fit_inc(inputs: Inputs, inc: DevRun) -> Calibration:
    run = usable(inc.run)
    return fit_incumbent(run, dev_weights(run.truth, inputs.dev_counts, inputs.cert_counts))


def fit(inputs: Inputs, candidate: DevRun, incumbent: Calibration) -> Calibration:
    run = usable(candidate.run)
    return fit_candidate(run, dev_weights(run.truth, inputs.dev_counts, inputs.cert_counts), incumbent.wrong)


def fit_policy(inputs: Inputs, run: DevRun) -> Calibration:
    """Spec §7.8: the configuration's own smallest tau with weighted dev W <= 2% (1.01 if none)."""
    usable_run = usable(run.run)
    weights = dev_weights(usable_run.truth, inputs.dev_counts, inputs.cert_counts)
    return fit_candidate(usable_run, weights, POLICY_LIMIT)


def pct(value: Fraction | float) -> str:
    return f"{float(value) * 100:.2f}"


def competence(inputs: Inputs, inc: DevRun) -> CompetenceCheck:
    """§3.4 on the 2,000 in-scope dev items; an invalid output or API error is a wrong prediction."""
    in_scope = set(inputs.groups.in_scope)
    items = [it for it in inputs.splits["dev"] if it.intent in in_scope]
    predicted = {r.item_id: r.intent if r.status == "ok" else None for r in inc.rows}
    return check_competence([(it.text, it.intent) for it in items], [predicted[it.item_id] for it in items])


def competence_line(check: CompetenceCheck) -> str:
    n = len(check.baseline_predictions)
    return (
        f"§3.4 on {n} in-scope dev items: baseline top-1 {check.baseline_accuracy * n}/{n} "
        f"({pct(check.baseline_accuracy)}%), incumbent {check.incumbent_accuracy * n}/{n} "
        f"({pct(check.incumbent_accuracy)}%): {'PASS' if check.passed else 'FAIL'}"
    )


def cmd_competence(args: argparse.Namespace) -> int:
    inputs = load(args.runs_dir)
    check = competence(inputs, require(inputs, "inc"))
    print(competence_line(check))
    return 0 if check.passed else 1


def cmd_status(args: argparse.Namespace) -> int:
    inputs = load(args.runs_dir)
    inc = find(inputs, "inc")
    incumbent: Calibration | None = None
    if inc is not None and run_validity(inc.meta, inc.rows)[0]:
        try:
            incumbent = fit_inc(inputs, inc)
        except VoidExperiment as exc:
            print(f"§6: {exc}")
    out = []
    for r in inputs.runs:
        ok, why = run_validity(r.meta, r.rows)
        statuses = Counter(row.status for row in r.rows)
        cal = None
        if incumbent is not None and ok:
            cal = incumbent if r.meta.config_id == "inc" else fit(inputs, r, incumbent)
        out.append(
            (
                r.meta.config_id,
                r.meta.run_id,
                r.meta.prompt_sha256[:12],
                len(r.rows),
                statuses["invalid_output"],
                statuses["api_error"],
                "yes" if ok else why,
                r.meta.totals.billed_usd,
                cal.tau if cal else None,
                pct(cal.wrong) if cal else None,
                pct(cal.automation) if cal else None,
            )
        )
    head = ("config", "run", "prompt", "items", "invalid", "api_error", "valid", "billed $", "tau", "W %", "A %")
    print(table(head, out))
    spent = cost.spent_usd(inputs.runs_dir, cost.load_prices(), inputs.configs)
    print("\nspent: " + ", ".join(f"{p} ${v:.4f}" for p, v in spent.items()))
    return 0


def cmd_dx_errors(args: argparse.Namespace) -> int:
    """Counts only: §2.5 allows reading dev errors for D-X, and rewording descriptions needs no message text.

    The candidate is matched to the incumbent's dev W, so what limits A is how confident its wrong routes are:
    the table lists every wrong route with its highest confidence, most confident first."""
    inputs = load(args.runs_dir)
    run = next((r for r in inputs.runs if r.meta.run_id == args.run_id), None)
    if run is None or run.meta.config_id not in ("luna-none", "luna-none-x"):
        raise SystemExit("give the run ID of a luna-none or luna-none-x dev run (§8.3)")
    incumbent = fit_inc(inputs, require(inputs, "inc"))
    cal = fit(inputs, valid(run), incumbent)
    r = usable(run.run)
    weights = dev_weights(r.truth, inputs.dev_counts, inputs.cert_counts)
    print(f"{run.meta.run_id}: tau {cal.tau}, weighted W {pct(cal.wrong)}%, A {pct(cal.automation)}%")
    print(f"matched to the incumbent's weighted dev W {pct(incumbent.wrong)}%\n")
    levels = sorted({float(c) for c, e in zip(r.confidence, r.eligible, strict=True) if e}, reverse=True)
    buckets = []
    for level in levels[: args.top]:
        at = r.eligible & (r.confidence == level)
        rates = weighted_rates(r, level, weights)
        wrong_here = int(np.count_nonzero(at & ~r.correct))
        buckets.append((level, int(np.count_nonzero(at)), wrong_here, pct(rates.wrong), pct(rates.automation)))
    print(table(("confidence", "items", "wrong", "W % at this tau", "A % at this tau"), buckets))
    wrong: Counter[tuple[str, str]] = Counter()
    top: dict[tuple[str, str], float] = {}
    for i in np.flatnonzero(r.eligible & ~r.correct):
        truth = f"{r.truth[i]} (not in catalog)" if r.slices[i] == OUT_OF_SCOPE else r.truth[i]
        key = (truth, str(r.intent[i]))
        wrong[key] += 1
        top[key] = max(top.get(key, 0.0), float(r.confidence[i]))
    rows = sorted(wrong, key=lambda k: (-top[k], -wrong[k], k))[: args.top]
    print(f"\nwrong routes at any tau: {wrong.total()}\n")
    print(table(("truth", "routed as", "items", "highest confidence"), [(*k, wrong[k], top[k]) for k in rows]))
    return 0


def cmd_dx_use(args: argparse.Namespace) -> int:
    if args.iteration not in range(1, budget_mod.DX_ITERATIONS + 1):
        raise SystemExit(f"iterations are 1..{budget_mod.DX_ITERATIONS} (§8.3)")
    path = prompt.DX_DIR / f"iteration-{args.iteration}.md"
    adapted, incumbent = prompt.load_prompt(path), prompt.load_prompt()
    if not prompt.keeps_catalog(adapted, incumbent):
        raise SystemExit(f"{path}: the catalog intents or examples differ from the incumbent prompt (§8.3)")
    prompt.ADAPTED_PROMPT.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    sha, changed = adapted.sha256()[:12], prompt.changed_lines(adapted, incumbent)
    print(f"{prompt.ADAPTED_PROMPT.name} = iteration {args.iteration}: prompt {sha}, {changed} changed lines")
    return 0


def gain_record(g: GainResult) -> dict[str, object]:
    return {
        "qualifies": g.qualifies,
        "difference_pp": round(float(g.difference) * 100, 4),
        "bootstrap_p10_pp": round(g.bootstrap_lower * 100, 4),
        "sign_p": round(float(g.sign_p), 6),
        "n10": g.n10,
        "n01": g.n01,
        "n": g.n,
        "dropped": g.dropped,
        "tau_inc": g.incumbent.tau,
        "tau_x": g.x.tau,
        "tau_y": g.y.tau,
        "seed": list(g.seed),
        "incumbent_unreachable_resamples": g.incumbent_unreachable_resamples,
    }


def frozen(cal: Calibration) -> FrozenCalibration:
    return FrozenCalibration(tau=cal.tau, dev_w=float(cal.wrong), dev_a=float(cal.automation))


def frozen_configurations(configs: dict[str, Configuration]) -> dict[str, ContractConfiguration]:
    out = {}
    for cid, cfg in configs.items():
        if cfg.pilot_only:
            continue
        p = prompt.load_prompt(cfg.prompt_path)
        out[cid] = ContractConfiguration(
            config_sha256=cfg.sha256(), prompt_sha256=p.sha256(), schema_sha256=schema_sha256(cfg, p)
        )
    return out


def clean_code(paths: Sequence[str]) -> None:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "status", "--porcelain", "--", *paths], capture_output=True, text=True, check=True
    )
    if result.stdout:
        raise SystemExit(f"commit these first; the contract records the code version:\n{result.stdout}")


def cmd_freeze(args: argparse.Namespace) -> int:
    clean_code(("src", "analysis", "config"))
    inputs = load(args.runs_dir)
    configs = inputs.configs

    inc = require(inputs, "inc")
    check = competence(inputs, inc)
    print(competence_line(check))
    if not check.passed:
        raise SystemExit("§3.4 failed: the project stops, nothing is frozen")
    try:
        incumbent = fit_inc(inputs, inc)
    except VoidExperiment as exc:
        raise SystemExit(f"§6: the experiment is void: {exc}") from exc

    runs = {"inc": inc} | {cid: require(inputs, cid) for cid in REQUIRED}
    for cid in LEVELS:
        found = find(inputs, cid)
        if found is not None and found.meta.complete:  # skipped or stopped at its ceiling: not in E (§8.1)
            runs[cid] = valid(found)
    cals = {"inc": incumbent} | {cid: fit(inputs, r, incumbent) for cid, r in runs.items() if cid != "inc"}

    # §8.3: iteration 0 is luna-none itself; every luna-none-x dev run must be a logged iteration.
    incumbent_prompt = prompt.load_prompt()
    dx_prompts = {0: incumbent_prompt}
    dx_runs = {0: runs["luna-none"]}
    for path in sorted(prompt.DX_DIR.glob("iteration-*.md")):
        n = int(path.stem.removeprefix("iteration-"))
        dx_prompts[n] = prompt.load_prompt(path)
        if not prompt.keeps_catalog(dx_prompts[n], incumbent_prompt):
            raise SystemExit(f"{path}: the catalog intents or examples differ from the incumbent prompt (§8.3)")
        dx_runs[n] = require(inputs, "luna-none-x", dx_prompts[n].sha256())
    logged = {r.meta.run_id for r in dx_runs.values()}
    unlogged = sorted(
        r.meta.run_id for r in inputs.runs if r.meta.config_id == "luna-none-x" and r.meta.run_id not in logged
    )
    if unlogged:
        raise SystemExit(f"luna-none-x dev runs without an iteration file in {prompt.DX_DIR}: {unlogged}")
    adaptation = select_adaptation(
        [IterationResult(0, 0, cals["luna-none"])]
        + [
            IterationResult(n, prompt.changed_lines(p, incumbent_prompt), fit(inputs, dx_runs[n], incumbent))
            for n, p in dx_prompts.items()
            if n
        ]
    )
    dx = adaptation.selected.iteration
    cals["luna-none-x"] = adaptation.selected.calibration
    source = prompt.INCUMBENT_PROMPT if dx == 0 else prompt.DX_DIR / f"iteration-{dx}.md"
    prompt.ADAPTED_PROMPT.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    # §8.1 and §8.2
    reasoning: dict[Vendor, ReasoningSelection] = {}
    for vendor, base, _ in VENDORS:
        levels: dict[str, AnalysisRun | None] = {
            "none" if vendor == "luna" else "off": runs[base].run,
            "low": runs[f"{vendor}-low"].run if f"{vendor}-low" in runs else None,
            "medium": runs[f"{vendor}-medium"].run if f"{vendor}-medium" in runs else None,
        }
        reasoning[vendor] = select_reasoning(inc.run, levels, inputs.dev_counts, inputs.cert_counts, vendor=vendor)
    jev = select_jev(cals["jev-c51"], cals["jev-noul"])

    # §9.5 projection before the freeze, at the per-item p90 cost of each dev run
    prices = cost.load_prices()
    dev_runs = {**runs, "luna-none-x": dx_runs[dx]}
    p90 = {
        cid: cost.cost_model(configs[cid], r.rows, r.meta.warmups, prices).item_p90_usd for cid, r in dev_runs.items()
    }
    spent = cost.spent_usd(inputs.runs_dir, prices, configs)
    outcomes = {
        provider: budget_mod.ReasoningOutcome(reasoning[vendor].selected, "low" in reasoning[vendor].qualified)
        for vendor, _, provider in VENDORS
    }
    plan = budget_mod.freeze_projection(spent, p90, outcomes, jev.selected, configs, budget_mod.load_budget())

    def reasoning_config(vendor: Vendor) -> str | None:
        """The R configuration after a budget substitution (§8.1); None when E is empty."""
        sub = next((s for s in plan.substitutions if s.run == f"{vendor}-R"), None)
        if sub is not None:
            return sub.to_config
        level = reasoning[vendor].selected
        return None if level is None else f"{vendor}-{level}"

    contract_configs = frozen_configurations(configs)
    for cid, r in dev_runs.items():
        expected = contract_configs[r.meta.config_id]
        made = (r.meta.config_sha256, r.meta.prompt_sha256, r.meta.schema_sha256)
        if made != (expected.config_sha256, expected.prompt_sha256, expected.schema_sha256):
            raise SystemExit(f"{cid}: dev run {r.meta.run_id} was not made with the configuration being frozen")

    records: dict[str, object] = {
        "competence": {
            "items": len(check.baseline_predictions),
            "baseline_accuracy": round(float(check.baseline_accuracy), 6),
            "incumbent_accuracy": round(float(check.incumbent_accuracy), 6),
        },
        "dev_runs": {cid: r.meta.run_id for cid, r in dev_runs.items()},
        "api_errors_left_out": {cid: r.run.status.count("api_error") for cid, r in dev_runs.items()},
        "reasoning": {
            vendor: {
                "qualified": list(reasoning[vendor].qualified),
                "selected_level": reasoning[vendor].selected,
                "config": reasoning_config(vendor),
                "comparisons": {name: gain_record(g) for name, g in reasoning[vendor].comparisons.items()},
            }
            for vendor, _, _ in VENDORS
        },
        "jev": {cid: {"tau": cals[cid].tau, "dev_a": float(cals[cid].automation)} for cid in ("jev-c51", "jev-noul")},
        "dx_iterations": [
            {
                "iteration": it.iteration,
                "prompt_sha256": dx_prompts[it.iteration].sha256(),
                "changed_lines": it.changed_lines,
                "run_id": dx_runs[it.iteration].meta.run_id,
                "tau": it.calibration.tau,
                "dev_w": float(it.calibration.wrong),
                "dev_a": float(it.calibration.automation),
            }
            for it in adaptation.iterations
        ],
        "budget": {
            "spent_usd": {p: round(v, 4) for p, v in spent.items()},
            "dev_p90_item_usd": {cid: round(v, 8) for cid, v in p90.items()},
            "projected_usd": {p: round(v, 4) for p, v in plan.projected_usd.items()},
            "substitutions": [f"{s.run}: {s.from_config} -> {s.to_config}" for s in plan.substitutions],
            "dropped": list(plan.dropped),
            "warnings": list(plan.warnings),
        },
    }
    analysis = AnalysisContract(
        incumbent_tau=incumbent.tau,
        configurations={cid: frozen(cal) for cid, cal in cals.items()},
        dev_counts=inputs.dev_counts,
        cert_counts=inputs.cert_counts,
        delta_w=0.0,  # set below from the measured discordance (§7.3), which needs the plan above
        delta_s=0.0,
        power={},
        slices=inputs.groups.slices,
        seeds={"bootstrap": SEED, "reasoning": SEED, "power": SEED},
        code_version=head_commit(REPO_ROOT),
        budget=BudgetPlan(
            planned_cert_runs=["aa" if r.split == "aa" else r.config_id for r in plan.runs],
            drop_order=list(budget_mod.CERT_DROP_ORDER),
            not_run={n.decision: n.reason for n in plan.not_run},
        ),
        selections=SelectionRecords(
            reasoning={vendor: reasoning_config(vendor) for vendor, _, _ in VENDORS},
            jev_design=jev.selected,
            dx_iteration=dx,
            dx_prompt_sha256=dx_prompts[dx].sha256(),
            records=records,
        ),
        order_sensitivity={
            cid: OrderSensitivity(changed=changed, items=items)
            for cid, (changed, items) in order_changes(latest_pilot_runs(inputs.runs_dir)).items()
        },
        policy={
            cid: frozen(fit_policy(inputs, r))
            for cid, r in dev_runs.items()
            if cid in {planned.config_id for planned in plan.runs}
        },
    )
    contract = Contract(
        tag=CONTRACT_TAG,
        configurations=contract_configs,
        item_lists={split: data.item_list_hash(inputs.splits[split]) for split in ("dev", "cert", "aa")},
        analysis=analysis,
    )

    # §7.3: margins from the worst own-threshold LLM discordance in the final plan, then each decision's power
    worst = write_pdisc(
        inputs.runs_dir, contract, inputs.splits["dev"], inputs.groups, args.pdisc_json, configs=configs
    )
    print("\n§7.3 margin grid, joint power of G1 + G2 for an equally good candidate:")
    (delta_w, delta_s), joint, reached = power.select_margins(worst, POWER_SIMS, SEED)
    analysis_runs = {cid: r.run for cid, r in dev_runs.items()}
    own = {
        budget_mod.RUN_DECISION[r.name]: discordance(analysis_runs, contract, [r.config_id])
        for r in plan.runs
        if r.name in budget_mod.RUN_DECISION
    }
    by_decision = {
        d: round(power.simulate(v, delta_w, delta_s, sims=POWER_SIMS, seed=SEED)["joint"], 4) for d, v in own.items()
    }
    margins = {"joint_power": round(joint, 4), "reached_target": reached, "sims": POWER_SIMS}
    analysis = analysis.model_copy(
        update={
            "delta_w": delta_w,
            "delta_s": delta_s,
            "power": dict(sorted(by_decision.items())),
            "dev_discordance": {"llm": worst} | dict(sorted(own.items())),
            "selections": analysis.selections.model_copy(update={"records": records | {"margins": margins}}),
        }
    )
    contract = contract.model_copy(update={"analysis": analysis})
    CONTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    header = "# Written by `python analysis/dev.py freeze` (spec §7.7). A change is a new contract version.\n"
    CONTRACT_PATH.write_text(
        header + yaml.safe_dump(contract.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    if load_contract(CONTRACT_PATH) != contract:
        raise SystemExit("the written contract does not read back unchanged")
    print(summary(analysis, check))
    return 0


def summary(a: AnalysisContract, check: CompetenceCheck) -> str:
    rec = a.selections.records
    lines = [
        f"\nwrote {CONTRACT_PATH.relative_to(REPO_ROOT)}",
        "",
        competence_line(check),
        "",
        "§6 calibration, weighted dev (%):",
        table(
            ("config", "tau", "W", "A"),
            [(cid, c.tau, pct(c.dev_w), pct(c.dev_a)) for cid, c in a.configurations.items()],
        ),
        "",
        f"§8.1 reasoning: luna -> {a.selections.reasoning['luna']}, haiku55 -> {a.selections.reasoning['haiku55']}",
        yaml.safe_dump(rec["reasoning"], sort_keys=False),
        f"§8.2 Jev design: {a.selections.jev_design}",
        f"§8.3 D-X: iteration {a.selections.dx_iteration}, prompt {a.selections.dx_prompt_sha256[:12]}",
        yaml.safe_dump(rec["dx_iterations"], sort_keys=False),
        "§9.5 cert plan: " + ", ".join(a.budget.planned_cert_runs),
        f"NOT RUN: {a.budget.not_run or 'none'}",
        yaml.safe_dump(rec["budget"], sort_keys=False),
        f"§7.3 margins: delta_W {a.delta_w * 100:.2f} pp, delta_S {a.delta_s * 100:.1f} pp; {rec['margins']}",
        "power per decision: " + ", ".join(f"{d} {v:.3f}" for d, v in a.power.items()),
        "",
        "§7.8 policy thresholds, own weighted dev W <= 2% (%):",
        table(("config", "tau", "W", "A"), [(cid, c.tau, pct(c.dev_w), pct(c.dev_a)) for cid, c in a.policy.items()]),
        "",
        "dev discordance (%):",
        table(("set", *a.slices), [(k, *(pct(v[s]) for s in a.slices)) for k, v in a.dev_discordance.items()]),
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs-dir", type=Path, default=REPO_ROOT / "runs")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("competence").set_defaults(func=cmd_competence)
    sub.add_parser("status").set_defaults(func=cmd_status)
    p_err = sub.add_parser("dx-errors")
    p_err.add_argument("run_id")
    p_err.add_argument("--top", type=int, default=40)
    p_err.set_defaults(func=cmd_dx_errors)
    p_use = sub.add_parser("dx-use")
    p_use.add_argument("iteration", type=int)
    p_use.set_defaults(func=cmd_dx_use)
    p_freeze = sub.add_parser("freeze")
    p_freeze.add_argument("--pdisc-json", type=Path, default=REPO_ROOT / "scratch" / "dev-pdisc.json")
    p_freeze.set_defaults(func=cmd_freeze)
    args = ap.parse_args()
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
