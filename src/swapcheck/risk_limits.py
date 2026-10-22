"""Spec §7.10 (amendment 3): risk-limit sensitivity, descriptive. `swapcheck risk-limits` writes
`decisions/A3-limits.md` at the thresholds frozen in `contract-v3`, from the `cert` runs of `contract-v1` and
`contract-v2`."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from statistics import NormalDist

import numpy as np

from swapcheck.contract import Calibration, Contract
from swapcheck.data import Item
from swapcheck.decide import DecisionRefusal, counts, load_cert_runs, pp, wilson, wilson_bounds
from swapcheck.groups import IntentGroups
from swapcheck.jev_policy import gated_rows
from swapcheck.outcomes import AnalysisRun, build_run, pair_runs
from swapcheck.stats import gate_g3

REPORT = "A3-limits.md"
J2 = "jev-noul"  # routed on §7.9's J2 signal, not on its Choice confidence


def _percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def _limit(value: float) -> str:
    return f"{value * 100:g}%"


def _dev(cal: Calibration) -> str:
    return f"{_percent(cal.dev_w)} / {_percent(cal.dev_a)}"


def _counts(run: AnalysisRun, tau: float) -> tuple[int, int]:
    """Wrong auto-routes and auto-routes at tau."""
    auto = run.auto_mask(tau)
    return int(np.count_nonzero(auto & ~run.correct)), int(np.count_nonzero(auto))


def _cells(run: AnalysisRun, tau: float, limit: float | None) -> str:
    """n, W with its interval, the one-sided 95% upper bound of W (against the limit, if any), A with its interval."""
    wrong, auto = _counts(run, tau)
    n = len(run)
    upper = wilson_bounds(wrong, n, NormalDist().inv_cdf(0.95))[1]
    held = "" if limit is None else f": {'below' if upper < limit else 'not below'} {_limit(limit)}"
    return f"{n} | {wilson(wrong, n)} | {pp(upper)}{held} | {wilson(auto, n)}"


def write_risk_limits(
    runs_dir: Path,
    base: Contract,
    jev: Contract,
    contract: Contract,
    items: Sequence[Item],
    groups: IntentGroups,
    output_dir: Path,
) -> str:
    """Verify every run against the contract it was made under before writing the deterministic report."""
    rl = contract.risk_limits
    if rl is None:
        raise DecisionRefusal([f"{contract.tag} has no risk limits (§7.10)"])
    sources = {base.tag: base, jev.tag: jev}
    wanted = {(tag, cid) for cid, tag in rl.run_contracts.items()}
    loaded, problems = load_cert_runs(runs_dir, (base, jev, contract), wanted, items)
    if "inc" not in rl.run_contracts or rl.run_contracts.keys() != rl.thresholds.keys():
        problems.append("the risk limits need the incumbent and exactly one threshold list per configuration")
    for cid, tag in sorted(rl.run_contracts.items()):
        source = sources.get(tag)
        if source is None:
            problems.append(f"{cid}: its run contract {tag} is neither {base.tag} nor {jev.tag}")
        elif cid not in contract.configurations or contract.configurations[cid] != source.configurations.get(cid):
            problems.append(f"{cid}: configuration hashes differ between {tag} and {contract.tag}")
        if len(rl.thresholds.get(cid, ())) != len(rl.limits):
            problems.append(f"{cid}: thresholds do not match the {len(rl.limits)} limits")
    if problems:
        raise DecisionRefusal(problems)

    def arm(cid: str) -> AnalysisRun:
        rows = loaded[cid][1]
        return build_run(items, gated_rows(rows) if cid == J2 else rows, split="cert", groups=groups, noul=cid == J2)

    full = arm("inc")
    inc = full.take([i for i, status in enumerate(full.status) if status != "api_error"])
    candidates = [cid for cid in rl.thresholds if cid != "inc"]
    paired = {cid: pair_runs(full, arm(cid)) for cid in candidates}
    header = " | ".join(_limit(limit) for limit in rl.limits)
    lines = [
        "# Amendment 3: risk-limit sensitivity (§7.10)",
        "",
        f"Contract `{contract.tag}` (analysis code `{rl.code_version}`), on the cert runs of `{base.tag}` and "
        f"`{jev.tag}`. Descriptive and post hoc; no verdict. Every earlier record stays as written.",
        "",
        "Each configuration runs at τ_L, its smallest threshold with weighted dev W ≤ L (the §6 rule; 1.01 if none); "
        "`jev-noul` runs on the J2 signal of §7.9. Cert estimates are unweighted, on the items paired with the "
        "incumbent's run (API errors in either arm dropped), with two-sided 95% Wilson score intervals. W upper is "
        "the one-sided 95% upper Wilson bound of W. A vs inc is the paired A difference (configuration minus "
        "incumbent) at the same limit, with one-sided 95% Tango bounds.",
        "",
        "| Configuration | Run | Run contract | Paired n | Dropped |",
        "|---|---|---|---:|---:|",
        f"| `inc` | `{loaded['inc'][0].run_id}` | `{rl.run_contracts['inc']}` | {len(inc)} | {len(full) - len(inc)} |",
        *(
            f"| `{cid}` | `{loaded[cid][0].run_id}` | `{rl.run_contracts[cid]}` | {len(paired[cid].runs[0])} | "
            f"{paired[cid].dropped} |"
            for cid in candidates
        ),
        "",
        "## Summary: cert W / A",
        "",
        f"| Configuration | {header} |",
        "|---|" + "---|" * len(rl.limits),
    ]
    for cid in rl.thresholds:
        run = inc if cid == "inc" else paired[cid].runs[1]
        cells = []
        for cal in rl.thresholds[cid]:
            wrong, auto = _counts(run, cal.tau)
            cells.append(f"{_percent(wrong / len(run))} / {_percent(auto / len(run))}")
        lines.append(f"| `{cid}` | {' | '.join(cells)} |")
    for k, limit in enumerate(rl.limits):
        ti = rl.thresholds["inc"][k]
        lines += [
            "",
            f"## Limit {_limit(limit)}",
            "",
            "| Configuration | τ_L | Weighted dev W / A | n | W [95% CI] | W upper | A [95% CI] | A vs inc [L, U] |",
            "|---|---:|---|---:|---|---|---|---|",
            f"| `inc` | {ti.tau:.2f} | {_dev(ti)} | {_cells(inc, ti.tau, limit)} | — |",
        ]
        for cid in candidates:
            tc = rl.thresholds[cid][k]
            ir, cr = paired[cid].runs
            b = gate_g3(*counts(cr.auto_mask(tc.tau), ir.auto_mask(ti.tau))).bounds
            lines.append(
                f"| `{cid}` | {tc.tau:.2f} | {_dev(tc)} | {_cells(cr, tc.tau, limit)} | "
                f"{pp(b.estimate)} [{pp(b.lower)}, {pp(b.upper)}] |"
            )
    lines += [
        "",
        "## Incumbent at fixed thresholds",
        "",
        "Not fitted. τ = 0 auto-routes every in-catalog answer; τ = 0.90 is the confidence `gpt-4o-mini` states "
        "most often.",
        "",
        "| τ | Weighted dev W / A | n | W [95% CI] | W upper | A [95% CI] |",
        "|---:|---|---:|---|---|---|",
        *(f"| {cal.tau:.2f} | {_dev(cal)} | {_cells(inc, cal.tau, None)} |" for cal in rl.incumbent_fixed),
    ]
    text = "\n".join(lines) + "\n"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / REPORT).write_text(text, encoding="utf-8")
    return text
