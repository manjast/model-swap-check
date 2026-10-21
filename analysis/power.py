"""Power of the non-inferiority gate on the wrong-auto rate (docs/spec.md §7.3).

Question answered: if a candidate is truly as good as the incumbent (or truly worse by
exactly the margin), how often does the pre-registered gate certify it?

Model of the data: for each message the paired outcome is one of
  both wrong-auto / neither / only candidate wrong-auto (n10) / only incumbent wrong-auto (n01).
Only the discordant pairs matter. `p_disc` is the share of messages where exactly one of
the two configurations auto-routes wrongly; `delta_true` is the true difference
P(n10) - P(n01) in wrong-auto rate.

Gate (normal approximation of the paired difference; the shipped gate uses a paired
bootstrap, and the test plan checks the two agree at these sample sizes):
  d = (n10 - n01) / n,  se = sqrt(((n10 + n01) / n - d**2) / n),  certify iff d + z * se < margin.

Standard library only (Python >= 3.12 for random.binomialvariate).

Usage:
  python analysis/power.py                       # planning table with assumed p_disc values
  python analysis/power.py --pdisc-json dev.json # M4: per-slice p_disc measured on dev
"""

from __future__ import annotations

import argparse
import json
import math
import random
from statistics import NormalDist

Z_95_ONE_SIDED = NormalDist().inv_cdf(0.95)

# Certification-set slice sizes from docs/spec.md §2.3 (asserted by the M0 split tests).
CERT_SLICES: dict[str, int] = {
    "cards": 1682,
    "card_payments": 1698,
    "cash": 1116,
    "transfers": 1553,
    "top_ups": 994,
    "account_other": 1368,
    "out_of_scope": 3132,
}


def analytic_power(n: int, p_disc: float, margin: float, delta_true: float = 0.0) -> float:
    """P(certify) under the normal approximation."""
    var = (p_disc - delta_true**2) / n
    se = math.sqrt(var)
    return NormalDist().cdf((margin - delta_true) / se - Z_95_ONE_SIDED)


def _draw_discordant(n: int, p_disc: float, delta_true: float, rng: random.Random) -> tuple[int, int]:
    n_disc = rng.binomialvariate(n, p_disc)
    q = (p_disc + delta_true) / (2 * p_disc)  # share of discordant pairs where only the candidate is wrong
    n10 = rng.binomialvariate(n_disc, q)
    return n10, n_disc - n10


def _certified(n10: int, n01: int, n: int, margin: float) -> bool:
    d = (n10 - n01) / n
    se = math.sqrt(max((n10 + n01) / n - d * d, 0.0) / n)
    return d + Z_95_ONE_SIDED * se < margin


def simulate(
    slices: dict[str, int],
    p_disc: dict[str, float],
    overall_margin: float,
    slice_margin: float,
    delta_true: float,
    sims: int,
    seed: int,
) -> dict[str, float]:
    """Monte Carlo P(certify) for the overall gate, each slice gate and the joint (all must pass)."""
    rng = random.Random(seed)
    passed = {name: 0 for name in slices} | {"overall": 0, "joint": 0}
    n_total = sum(slices.values())
    for _ in range(sims):
        tot10 = tot01 = 0
        all_ok = True
        for name, n in slices.items():
            n10, n01 = _draw_discordant(n, p_disc[name], delta_true, rng)
            tot10 += n10
            tot01 += n01
            ok = _certified(n10, n01, n, slice_margin)
            passed[name] += ok
            all_ok &= ok
        overall_ok = _certified(tot10, tot01, n_total, overall_margin)
        passed["overall"] += overall_ok
        passed["joint"] += all_ok and overall_ok
    return {k: v / sims for k, v in passed.items()}


def planning_table(sims: int, seed: int) -> None:
    print("Joint P(certify) for an equally good candidate (delta_true = 0), all 7 slices + overall")
    print(f"cert n = {sum(CERT_SLICES.values())}, slices = {CERT_SLICES}")
    print("p_disc assumption: in-scope slices p, out_of_scope slice 2p\n")
    margins = [(0.005, 0.02), (0.005, 0.025), (0.0075, 0.025), (0.0075, 0.03), (0.01, 0.03)]
    print("p_disc  " + "  ".join(f"{o*100:.2f}/{s*100:.1f}pp" for o, s in margins))
    for p in (0.03, 0.05, 0.08):
        pd = {k: (2 * p if k == "out_of_scope" else p) for k in CERT_SLICES}
        row = [simulate(CERT_SLICES, pd, o, s, 0.0, sims, seed)["joint"] for o, s in margins]
        print(f"{p:5.2f}   " + "  ".join(f"{r:>12.0%}" for r in row))
    print("\nFalse release at the margin (delta_true = margin), overall gate alone, should be <= 5%:")
    n = sum(CERT_SLICES.values())
    for p in (0.03, 0.08):
        r = simulate({"all": n}, {"all": p}, 0.005, 1.0, 0.005, sims, seed)["overall"]
        print(f"  p_disc {p:.2f}, margin 0.5pp: {r:.1%}")


def from_dev(path: str, sims: int, seed: int) -> None:
    """M4: choose margins from measured dev discordance (spec §7.3 selection rule)."""
    with open(path, encoding="utf-8") as fh:
        p_disc: dict[str, float] = json.load(fh)
    missing = set(CERT_SLICES) - set(p_disc)
    if missing:
        raise SystemExit(f"p_disc missing for slices: {sorted(missing)}")
    grid = [(o, s) for o in (0.005, 0.0075, 0.01) for s in (0.015, 0.02, 0.025, 0.03)]
    for o, s in grid:
        res = simulate(CERT_SLICES, p_disc, o, s, 0.0, sims, seed)
        print(f"overall {o*100:.2f}pp slice {s*100:.1f}pp -> joint {res['joint']:.0%}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdisc-json", help="JSON mapping slice -> worst-case p_disc measured on dev")
    ap.add_argument("--sims", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=20261021)
    args = ap.parse_args()
    if args.pdisc_json:
        from_dev(args.pdisc_json, args.sims, args.seed)
    else:
        planning_table(args.sims, args.seed)


if __name__ == "__main__":
    main()
