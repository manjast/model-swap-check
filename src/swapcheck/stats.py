"""Paired Tango score gates and intent-cluster sensitivity (spec §7.1-§7.4).

All rates and margins are proportions, not percentage points. Inputs contain only paired,
non-API-error items; the outcome layer owns that exclusion. No analysis-script imports are used.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import NormalDist
from typing import Literal

import numpy as np
from numpy.typing import NDArray

GateStatus = Literal["PASS", "FAIL", "UNRESOLVED"]
GateName = Literal["G1", "G2", "G3"]
IntArray = NDArray[np.int64]
FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]
SLICE_HARM_CONFIDENCE = 1 - 0.05 / 7
BOOTSTRAP_RESAMPLES = 10_000


@dataclass(frozen=True)
class PairedBounds:
    estimate: float
    lower: float
    upper: float
    wald_lower: float
    wald_upper: float
    confidence: float


@dataclass(frozen=True)
class GateResult:
    status: GateStatus
    bounds: PairedBounds
    margin: float
    harm_lower: float | None = None


@dataclass(frozen=True)
class SliceGateResult:
    status: GateStatus
    slices: Mapping[str, GateResult]


@dataclass(frozen=True)
class SampleSizeResult:
    n: int | None
    reason: Literal["not reachable at this point estimate", "no discordant pairs observed"] | None = None


@dataclass(frozen=True)
class PercentileBounds:
    lower: float
    upper: float
    harm_lower: float


@dataclass(frozen=True)
class BootstrapSensitivity:
    original_status: GateStatus
    bootstrap_status: GateStatus
    changed: bool
    bounds: Mapping[str, PercentileBounds]


def _validate_counts(n10: int, n01: int, n: int) -> None:
    if n <= 0 or n10 < 0 or n01 < 0 or n10 + n01 > n:
        raise ValueError("paired counts require n > 0 and 0 <= n10 + n01 <= n")


def _z(confidence: float) -> float:
    if not 0.5 < confidence < 1:
        raise ValueError("one-sided confidence must be in (0.5, 1)")
    return NormalDist().inv_cdf(confidence)


def restricted_mle(n10: int, n01: int, n: int, delta: float) -> float:
    """Restricted MLE of p01 under p10 - p01 = delta (Tango, 1998)."""
    _validate_counts(n10, n01, n)
    if not -1 <= delta <= 1:
        raise ValueError("delta must be in [-1, 1]")
    w = -n10 - n01 + (2 * n - n10 + n01) * delta
    root = math.sqrt(max(w * w + 8 * n * n01 * delta * (1 - delta), 0.0))
    # Rationalization avoids cancellation when delta > 0 and n01 is small.
    q = 2 * n01 * delta * (1 - delta) / (root + w) if w > 0 else (root - w) / (4 * n)
    return min((1 - delta) / 2, max(max(0.0, -delta), q))


def tango_score(n10: int, n01: int, n: int, delta: float) -> float:
    """Signed score for candidate minus incumbent under H0: difference = delta."""
    q = restricted_mle(n10, n01, n, delta)
    variance = n * (2 * q + delta * (1 - delta))
    difference = n10 - n01 - n * delta
    if variance <= 0:
        return math.copysign(math.inf, difference) if difference else 0.0
    return difference / math.sqrt(variance)


def tango_scores(n10: IntArray, n01: IntArray, n: int, delta: float) -> FloatArray:
    """Vectorized score-at-margin, equivalent to inverting the scalar upper bound."""
    if n <= 0 or n10.shape != n01.shape or np.any((n10 < 0) | (n01 < 0) | (n10 + n01 > n)):
        raise ValueError("invalid paired counts")
    if not -1 <= delta <= 1:
        raise ValueError("delta must be in [-1, 1]")
    a, b = n10.astype(np.float64), n01.astype(np.float64)
    w = -a - b + (2 * n - a + b) * delta
    root = np.sqrt(np.maximum(w * w + 8 * n * b * delta * (1 - delta), 0))
    q = (root - w) / (4 * n)
    np.divide(2 * b * delta * (1 - delta), root + w, out=q, where=w > 0)
    q = np.clip(q, max(0.0, -delta), (1 - delta) / 2)
    variance = n * (2 * q + delta * (1 - delta))
    difference = a - b - n * delta
    result = np.copysign(np.full_like(difference, np.inf), difference)
    result[difference == 0] = 0
    np.divide(difference, np.sqrt(np.maximum(variance, 0)), out=result, where=variance > 0)
    return result


def certifies_upper(n10: IntArray, n01: IntArray, n: int, margin: float, confidence: float = 0.95) -> BoolArray:
    """G1/G2 PASS test without inversion, for Monte Carlo and planning."""
    return tango_scores(n10, n01, n, margin) < -_z(confidence)


def _invert(n10: int, n01: int, n: int, target: float) -> float:
    low, high = -1.0, 1.0
    if tango_score(n10, n01, n, low) <= target:
        return low
    if tango_score(n10, n01, n, high) >= target:
        return high
    # Extra precision also makes the score residual < 1e-9 on certification-sized data.
    while high - low > 1e-14:
        mid = (low + high) / 2
        if tango_score(n10, n01, n, mid) > target:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def paired_bounds(n10: int, n01: int, n: int, confidence: float = 0.95) -> PairedBounds:
    """One-sided Tango and untruncated Wald bounds at the same confidence."""
    _validate_counts(n10, n01, n)
    z = _z(confidence)
    estimate = (n10 - n01) / n
    se = math.sqrt(max((n10 + n01) / n - estimate * estimate, 0.0) / n)
    return PairedBounds(
        estimate,
        _invert(n10, n01, n, z),
        _invert(n10, n01, n, -z),
        estimate - z * se,
        estimate + z * se,
        confidence,
    )


def _upper_status(lower: float, upper: float, margin: float) -> GateStatus:
    if upper < margin:
        return "PASS"
    return "FAIL" if lower >= margin else "UNRESOLVED"


def _lower_status(lower: float, upper: float, margin: float) -> GateStatus:
    if lower > margin:
        return "PASS"
    return "FAIL" if upper <= margin else "UNRESOLVED"


def gate_g1(n10: int, n01: int, n: int, margin: float, confidence: float = 0.95) -> GateResult:
    bounds = paired_bounds(n10, n01, n, confidence)
    return GateResult(_upper_status(bounds.lower, bounds.upper, margin), bounds, margin)


def _slice_status(statuses: Sequence[GateStatus]) -> GateStatus:
    if "FAIL" in statuses:
        return "FAIL"
    return "PASS" if all(status == "PASS" for status in statuses) else "UNRESOLVED"


def gate_g2(counts: Mapping[str, tuple[int, int, int]], margin: float, confidence: float = 0.95) -> SliceGateResult:
    """Per-slice PASS at confidence; harm is Bonferroni-adjusted over seven slices."""
    if len(counts) != 7:
        raise ValueError("G2 requires all seven slices")
    slices: dict[str, GateResult] = {}
    for name, (n10, n01, n) in counts.items():
        bounds = paired_bounds(n10, n01, n, confidence)
        harm_lower = _invert(n10, n01, n, _z(SLICE_HARM_CONFIDENCE))
        slices[name] = GateResult(_upper_status(harm_lower, bounds.upper, margin), bounds, margin, harm_lower)
    return SliceGateResult(_slice_status([result.status for result in slices.values()]), slices)


def gate_g3(n10: int, n01: int, n: int, confidence: float = 0.95) -> GateResult:
    bounds = paired_bounds(n10, n01, n, confidence)
    return GateResult(_lower_status(bounds.lower, bounds.upper, -0.03), bounds, -0.03)


def gate_g4(valid: int, total: int) -> GateStatus:
    if total <= 0 or not 0 <= valid <= total:
        raise ValueError("validity counts require 0 <= valid <= total and total > 0")
    return "PASS" if valid * 1000 >= total * 995 else "FAIL"


def sample_size_needed(
    n10: int, n01: int, n: int, margin: float, *, direction: Literal["upper", "lower"] = "upper"
) -> SampleSizeResult:
    """80%-power planning formula; lower direction uses a signed margin (G3: -0.03)."""
    _validate_counts(n10, n01, n)
    estimate = (n10 - n01) / n
    gap = margin - estimate if direction == "upper" else estimate - margin
    if gap <= 0:
        return SampleSizeResult(None, "not reachable at this point estimate")
    if n10 + n01 == 0:
        # p̂ = 0 makes the formula return 0, which would read as "already enough"; the gate is unresolved.
        return SampleSizeResult(None, "no discordant pairs observed")
    needed = (n10 + n01) / n * (_z(0.95) + _z(0.80)) ** 2 / gap**2
    return SampleSizeResult(math.ceil(needed))


def _counts(candidate: BoolArray, incumbent: BoolArray) -> tuple[int, int, int]:
    return int(np.count_nonzero(candidate & ~incumbent)), int(np.count_nonzero(incumbent & ~candidate)), candidate.size


def cluster_bootstrap(
    intents: Sequence[str],
    slices: Sequence[str],
    candidate: BoolArray,
    incumbent: BoolArray,
    slice_order: Sequence[str],
    *,
    gate: GateName,
    decision_index: int,
    margin: float | None = None,
    confidence: float = 0.95,
) -> BootstrapSensitivity:
    """Resample whole intents within each slice; percentile bounds never alter a verdict.

    Intent sizes need not be equal: each replicate divides its total paired difference by
    its resampled item count, rather than averaging per-intent rates.
    """
    _z(confidence)
    if gate not in ("G1", "G2", "G3"):
        raise ValueError("bootstrap supports Tango gates G1, G2 and G3")
    if (
        not (len(intents) == len(slices) == candidate.size == incumbent.size)
        or candidate.ndim != 1
        or incumbent.ndim != 1
    ):
        raise ValueError("paired item arrays must have equal one-dimensional lengths")
    if len(set(slice_order)) != len(slice_order) or set(slices) != set(slice_order):
        raise ValueError("slice_order must contain each observed slice exactly once")
    if gate == "G3":
        margin = -0.03
    elif margin is None:
        raise ValueError("wrong-auto gates require a margin")
    assert margin is not None
    labels = np.asarray(slices)
    intent_labels = np.asarray(intents)
    difference = candidate.astype(np.int64) - incumbent.astype(np.int64)
    rng = np.random.default_rng(np.random.SeedSequence([20261021, decision_index, int(gate[1:])]))
    totals = np.zeros(BOOTSTRAP_RESAMPLES, dtype=np.float64)
    sizes = np.zeros(BOOTSTRAP_RESAMPLES, dtype=np.float64)
    slice_draws: dict[str, FloatArray] = {}
    counts: dict[str, tuple[int, int, int]] = {}
    seen: set[str] = set()
    for name in slice_order:
        mask = labels == name
        unique, inverse = np.unique(intent_labels[mask], return_inverse=True)
        if seen.intersection(unique.tolist()):
            raise ValueError("an intent cannot belong to multiple slices")
        seen.update(unique.tolist())
        sums = np.bincount(inverse, weights=difference[mask])
        ns = np.bincount(inverse)
        draws = rng.integers(unique.size, size=(BOOTSTRAP_RESAMPLES, unique.size))
        draw_sums = sums[draws].sum(axis=1)
        draw_sizes = ns[draws].sum(axis=1)
        slice_draws[name] = draw_sums / draw_sizes
        totals += draw_sums
        sizes += draw_sizes
        counts[name] = _counts(candidate[mask], incumbent[mask])
    if gate == "G2":
        original = gate_g2(counts, margin, confidence).status
        draws_by_name = slice_draws
    else:
        pooled = _counts(candidate, incumbent)
        original = (gate_g1(*pooled, margin, confidence) if gate == "G1" else gate_g3(*pooled, confidence)).status
        draws_by_name = {"overall": totals / sizes}
    bounds: dict[str, PercentileBounds] = {}
    statuses: list[GateStatus] = []
    for name, values in draws_by_name.items():
        lower, upper, harm_lower = np.quantile(values, [1 - confidence, confidence, 1 - SLICE_HARM_CONFIDENCE])
        bounds[name] = PercentileBounds(float(lower), float(upper), float(harm_lower))
        if gate == "G3":
            statuses.append(_lower_status(float(lower), float(upper), margin))
        else:
            statuses.append(_upper_status(float(harm_lower if gate == "G2" else lower), float(upper), margin))
    bootstrap_status = _slice_status(statuses)
    return BootstrapSensitivity(original, bootstrap_status, bootstrap_status != original, bounds)
