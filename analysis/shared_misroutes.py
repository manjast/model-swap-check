"""Shared misroutes in the `cert` runs (docs/cert.md): descriptive and post hoc, no verdict.

Prints Markdown: how many of `jev-c51`'s wrong auto-routes at confidence 1.00 got the same queue from each other
configuration, and, at each configuration's amendment 3 thresholds, the share of shared misroutes (every
configuration picks the same queue, the label says otherwise) it auto-routes against the share of its own correct
answers. `jev-noul` is left out: it routes on the J2 signal, not on a confidence of its own. Reads labels and
structured fields only: no message text.

Usage:
    python analysis/shared_misroutes.py [--runs-dir runs]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from swapcheck.agreement import shared_misroutes
from swapcheck.contract import load_contract
from swapcheck.data import load_splits
from swapcheck.decide import DecisionRefusal, load_cert_runs
from swapcheck.groups import REPO_ROOT, load_groups
from swapcheck.outcomes import build_run

CONTRACTS = REPO_ROOT / "contracts"
REFERENCE, TOP = "jev-c51", 1.0


def _percent(value: float) -> str:
    return f"{value * 100:.0f}%"


def report(runs_dir: Path) -> str:
    base, jev, v3 = (load_contract(CONTRACTS / f"contract-v{k}.yaml") for k in (1, 2, 3))
    rl = v3.risk_limits
    assert rl is not None
    cids = [cid for cid in rl.thresholds if cid != "jev-noul"]
    groups = load_groups()
    items = load_splits(groups)["cert"]
    loaded, problems = load_cert_runs(runs_dir, (base, jev, v3), {(rl.run_contracts[c], c) for c in cids}, items)
    if problems:
        raise DecisionRefusal(problems)
    runs = {cid: build_run(items, loaded[cid][1], split="cert", groups=groups) for cid in cids}
    taus = {cid: [cal.tau for cal in rl.thresholds[cid]] for cid in cids}
    taus[REFERENCE] = [*taus[REFERENCE], TOP]  # the reference's top confidence, after its τ_L values
    r = shared_misroutes(runs, taus, REFERENCE, TOP)
    top = r.gates[REFERENCE].pop()
    limits = " | ".join(f"{limit * 100:g}%" for limit in rl.limits)
    return "\n".join(
        [
            f"Items answered by all {len(cids)} configurations: {r.n} (dropped {r.dropped}).",
            f"`{REFERENCE}` wrong auto-routes at confidence {TOP:.2f}: {r.reference_wrong}. Same queue from: "
            + ", ".join(f"`{cid}` {n}" for cid, n in r.same_answer.items())
            + ".",
            f"Shared misroutes: {r.shared} ({r.shared / r.n * 100:.2f}% of items; label out of scope for "
            f"{r.shared_out_of_scope}). At confidence {TOP:.2f}, `{REFERENCE}` auto-routes "
            f"{_percent(top.shared)} of them and {_percent(top.correct)} of its own correct answers.",
            "",
            "Share of shared misroutes / share of own correct answers auto-routed, at each limit's τ_L:",
            "",
            f"| Configuration | {limits} |",
            "|---|" + "---:|" * len(rl.limits),
            *(
                f"| `{cid}` | "
                + " | ".join(f"{_percent(g.shared)} / {_percent(g.correct)} (τ {g.tau:.2f})" for g in gates)
                + " |"
                for cid, gates in r.gates.items()
            ),
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs-dir", type=Path, default=REPO_ROOT / "runs")
    print(report(parser.parse_args().runs_dir))


if __name__ == "__main__":
    main()
