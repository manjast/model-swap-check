"""Power of the wrong-auto non-inferiority gates G1 + G2 (docs/spec.md §7).

Question: if a candidate is truly as good as the incumbent, how often do G1 (overall) and
G2 (every slice) both certify it? And if it is truly worse by exactly the margin, how often
is it wrongly certified?

Data model per slice: only discordant pairs matter. `p_disc` = share of messages where
exactly one of the two configurations auto-routes wrongly; `delta` = true difference in
wrong-auto rate (candidate minus incumbent).

Calibration noise (spec §6): the candidate's threshold is matched to the incumbent's dev
wrong-auto rate, so on cert the two operating points differ by dev sampling error. Each
simulated experiment therefore draws one common shift
    delta_0 ~ Normal(0, sqrt(p_disc_overall / dev_n))
added to every slice's true difference (clamped so the cell probabilities stay valid).

Gate (normal approximation of the paired difference; the shipped gate is a multinomial
paired bootstrap and test T-S4 checks the two agree):
    d = (n10 - n01) / n,  se = sqrt(((n10 + n01) / n - d**2) / n),  certify iff d + z * se < margin

Standard library only (Python >= 3.12 for random.binomialvariate).

Usage:
    python analysis/power.py                        # planning table, assumed p_disc
    python analysis/power.py --pdisc-json dev.json  # M4: select margins from measured dev discordance
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from statistics import NormalDist

ALPHA = 0.05
P_DISC_FLOOR = 0.01  # pre-registered minimum per slice (spec §7.3)
DEV_N = 3075
POWER_TARGET = 0.80
OVERALL_MARGINS = (0.005, 0.0075, 0.01)
SLICE_MARGINS = (0.015, 0.02, 0.025, 0.03)
FALLBACK = (0.01, 0.03)

# Certification-set slice sizes from docs/spec.md §2.3 (asserted by test T-D3).
CERT_SLICES: dict[str, int] = {
    "cards": 1407,
    "card_payments": 1473,
    "cash": 966,
    "transfers": 1328,
    "top_ups": 844,
    "account_other": 1143,
    "out_of_scope": 2597,
}


def _z(alpha: float) -> float:
    return NormalDist().inv_cdf(1 - alpha)


def _draw_discordant(n: int, p_disc: float, delta: float, rng: random.Random) -> tuple[int, int]:
    delta = max(-p_disc, min(p_disc, delta))
    n_disc = rng.binomialvariate(n, p_disc)
    n10 = rng.binomialvariate(n_disc, (p_disc + delta) / (2 * p_disc))
    return n10, n_disc - n10


def _certified(n10: int, n01: int, n: int, margin: float, z: float) -> bool:
    d = (n10 - n01) / n
    se = math.sqrt(max((n10 + n01) / n - d * d, 0.0) / n)
    return d + z * se < margin


def simulate(
    p_disc: dict[str, float],
    overall_margin: float,
    slice_margin: float,
    delta_true: float = 0.0,
    dev_n: int | None = DEV_N,
    sims: int = 4000,
    seed: int = 20261021,
    alpha: float = ALPHA,
) -> dict[str, float]:
    """Monte Carlo P(certify) for G1, each slice of G2, and G1 and G2 jointly."""
    for name, p in p_disc.items():
        if not 0 < p <= 1:
            raise ValueError(f"p_disc for {name} must be in (0, 1], got {p}")
    z = _z(alpha)
    rng = random.Random(seed)
    n_total = sum(CERT_SLICES.values())
    p_overall = sum(p_disc[s] * n for s, n in CERT_SLICES.items()) / n_total
    shift_sd = math.sqrt(p_overall / dev_n) if dev_n else 0.0
    passed = {name: 0 for name in CERT_SLICES} | {"overall": 0, "joint": 0}
    for _ in range(sims):
        shift = rng.gauss(0.0, shift_sd) if shift_sd else 0.0
        tot10 = tot01 = 0
        all_slices = True
        for name, n in CERT_SLICES.items():
            n10, n01 = _draw_discordant(n, p_disc[name], delta_true + shift, rng)
            tot10 += n10
            tot01 += n01
            ok = _certified(n10, n01, n, slice_margin, z)
            passed[name] += ok
            all_slices &= ok
        overall_ok = _certified(tot10, tot01, n_total, overall_margin, z)
        passed["overall"] += overall_ok
        passed["joint"] += all_slices and overall_ok
    return {k: v / sims for k, v in passed.items()}


def select_margins(p_disc: dict[str, float], sims: int, seed: int) -> tuple[tuple[float, float], float, bool]:
    """Spec §7.3: strictest (overall, slice) pair with joint power >= target; else the fallback."""
    for o in OVERALL_MARGINS:
        for s in SLICE_MARGINS:
            power = simulate(p_disc, o, s, sims=sims, seed=seed)["joint"]
            print(f"  overall {o * 100:.2f} pp, slice {s * 100:.1f} pp: joint power {power:.4f}")
            if power >= POWER_TARGET:
                return (o, s), power, True
    power = simulate(p_disc, *FALLBACK, sims=sims, seed=seed)["joint"]
    return FALLBACK, power, False


def load_pdisc(path: str) -> dict[str, float]:
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    missing = set(CERT_SLICES) - set(raw)
    if missing:
        raise SystemExit(f"p_disc missing for slices: {sorted(missing)}")
    return {s: max(float(raw[s]), P_DISC_FLOOR) for s in CERT_SLICES}


def planning_table(sims: int, seed: int) -> None:
    print(f"cert slices {CERT_SLICES} (n = {sum(CERT_SLICES.values())}), dev n = {DEV_N}")
    print("Joint power of G1 + G2 for an equally good candidate, with calibration noise.")
    print("Assumption: in-scope slices p_disc = p, out_of_scope slice = 2p.\n")
    pairs = [(0.005, 0.02), (0.0075, 0.025), (0.01, 0.025), (0.01, 0.03)]
    print("p      " + "".join(f"{o * 100:.2f}/{s * 100:.1f}pp   " for o, s in pairs))
    for p in (0.03, 0.05, 0.08):
        pd = {k: (2 * p if k == "out_of_scope" else p) for k in CERT_SLICES}
        print(f"{p:.2f}   " + "".join(f"{simulate(pd, o, s, sims=sims, seed=seed)['joint']:>12.1%}   " for o, s in pairs))
    print("\nFalse release with the true difference at the margin (G1 alone, no calibration noise):")
    for p in (0.03, 0.08):
        pd = {k: p for k in CERT_SLICES}
        rate = simulate(pd, 0.005, 1.0, delta_true=0.005, dev_n=None, sims=sims, seed=seed)["overall"]
        print(f"  p_disc {p:.2f}, margin 0.50 pp: {rate:.2%}  (target 5%, Monte Carlo SE {math.sqrt(0.05 * 0.95 / sims):.2%})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdisc-json", help="JSON: slice -> worst dev discordance across candidates")
    ap.add_argument("--sims", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=20261021)
    args = ap.parse_args()
    if not args.pdisc_json:
        planning_table(args.sims, args.seed)
        return
    p_disc = load_pdisc(args.pdisc_json)
    (o, s), power, reached = select_margins(p_disc, args.sims, args.seed)
    print(f"selected: overall {o * 100:.2f} pp, slice {s * 100:.1f} pp, joint power {power:.4f}")
    if not reached:
        print(f"no pair reached {POWER_TARGET:.0%}; fallback used, power stated in the contract")
        sys.exit(2)


if __name__ == "__main__":
    main()
