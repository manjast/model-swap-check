"""Exact development calibration and batched recalibrating bootstrap (spec §6)."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from swapcheck.groups import OUT_OF_SCOPE

if TYPE_CHECKING:
    from swapcheck.outcomes import AnalysisRun


class VoidExperiment(RuntimeError):
    """The incumbent cannot meet its registered risk limit on supported thresholds."""


@dataclass(frozen=True)
class Calibration:
    tau: float
    wrong: Fraction
    automation: Fraction


@dataclass(frozen=True)
class ResampledCalibration:
    tau: NDArray[np.float64]
    wrong: NDArray[np.float64]
    automation: NDArray[np.float64]
    wrong_mass: NDArray[np.int64]
    total_mass: NDArray[np.int64]


def _require_dev(run: AnalysisRun) -> None:
    if run.split != "dev":
        raise ValueError("Threshold calibration requires exclusively dev items")


def _support_mask(run: AnalysisRun) -> NDArray[np.bool_]:
    return np.fromiter(
        (
            status == "ok" and intent is not None and intent != OUT_OF_SCOPE
            for status, intent in zip(run.status, run.intent, strict=True)
        ),
        dtype=np.bool_,
        count=len(run),
    )


def thresholds(run: AnalysisRun) -> NDArray[np.float64]:
    """Sorted §6 support, including valid predictions escalated by the Noul gate."""
    _require_dev(run)
    return np.unique(np.concatenate((np.array([0.0]), run.confidence[_support_mask(run)])))


def _fit(run: AnalysisRun, weights: tuple[Fraction, ...], limit: Fraction, *, incumbent: bool) -> Calibration:
    _require_dev(run)
    if len(weights) != len(run):
        raise ValueError("Calibration weights must align with run items")
    # Group once: subtracting each lower confidence preserves exact rational boundaries.
    grouped: dict[float, tuple[Fraction, Fraction]] = {}
    wrong = Fraction(0)
    automation = Fraction(0)
    for index in np.flatnonzero(run.eligible):
        weight = weights[int(index)]
        error = Fraction(0) if run.correct[index] else weight
        confidence = float(run.confidence[index])
        old_wrong, old_auto = grouped.get(confidence, (Fraction(0), Fraction(0)))
        grouped[confidence] = (old_wrong + error, old_auto + weight)
        wrong += error
        automation += weight
    previous = 0.0
    for value in thresholds(run):
        tau = float(value)
        if tau > previous:
            removed_wrong, removed_auto = grouped.get(previous, (Fraction(0), Fraction(0)))
            wrong -= removed_wrong
            automation -= removed_auto
        if wrong <= limit:
            return Calibration(tau, wrong, automation)
        previous = tau
    if incumbent:
        raise VoidExperiment("Incumbent cannot reach weighted wrong-auto rate <= 2% on dev threshold support")
    return Calibration(1.01, Fraction(0), Fraction(0))


def fit_incumbent(run: AnalysisRun, weights: tuple[Fraction, ...]) -> Calibration:
    """Choose the smallest supported threshold meeting the exact 2% risk limit."""
    return _fit(run, weights, Fraction(1, 50), incumbent=True)


def fit_candidate(run: AnalysisRun, weights: tuple[Fraction, ...], incumbent_wrong: Fraction) -> Calibration:
    """Match the incumbent's exact weighted risk, escalating all if unreachable."""
    return _fit(run, weights, incumbent_wrong, incumbent=False)


def fit_resamples(
    run: AnalysisRun,
    weights: NDArray[np.int64],
    limit_numerators: NDArray[np.int64],
    limit_denominators: NDArray[np.int64],
) -> ResampledCalibration:
    """Fit integer original-item masses against exact rational risk limits.

    Zero-weight items do not contribute threshold support. An unreachable resample
    takes tau=1.01 with zero wrong and automation mass, including incumbent fits.
    Products and cumulative masses are checked before int64 arithmetic can overflow.
    """
    _require_dev(run)
    if weights.ndim != 2 or weights.shape[1] != len(run):
        raise ValueError("Resample weights must have shape (resamples, run items)")
    count = weights.shape[0]
    if limit_numerators.shape != (count,) or limit_denominators.shape != (count,):
        raise ValueError("Resample limits must have one numerator and denominator per resample")
    if weights.dtype != np.int64 or limit_numerators.dtype != np.int64 or limit_denominators.dtype != np.int64:
        raise ValueError("Resample masses and rational limits must use int64 arrays")
    if np.any(weights < 0):
        raise ValueError("Resample item masses must be nonnegative")
    if np.any(limit_denominators <= 0):
        raise ValueError("Resample limit denominators must be positive")
    bound = 1 << 62
    max_item_mass = int(np.max(weights, initial=0))
    if max_item_mass * len(run) >= bound:
        raise OverflowError("Resample item masses exceed safe int64 cumulative-sum bounds")
    total_mass = np.sum(weights, axis=1, dtype=np.int64)
    if np.any(total_mass <= 0):
        raise ValueError("Every resample must have positive total mass")
    max_total_mass = int(np.max(total_mass, initial=0))
    max_denominator = int(np.max(limit_denominators, initial=0))
    max_numerator = max(
        abs(int(np.min(limit_numerators, initial=0))),
        abs(int(np.max(limit_numerators, initial=0))),
    )
    if max_denominator * max_total_mass >= bound or max_numerator * max_total_mass >= bound:
        raise OverflowError("Resample rational limits exceed safe int64 cross-product bounds")
    taus = np.full(count, 1.01, dtype=np.float64)
    wrong = np.zeros(count, dtype=np.float64)
    automation = np.zeros(count, dtype=np.float64)
    fitted_wrong_mass = np.zeros(count, dtype=np.int64)
    indices = np.flatnonzero(_support_mask(run))
    indices = indices[np.argsort(run.confidence[indices], kind="stable")]
    confidences = run.confidence[indices]
    if not indices.size:
        # There is still the universal threshold zero, with no automated predictions.
        zero_ok = limit_numerators >= 0
        taus[zero_ok] = 0.0
        return ResampledCalibration(taus, wrong, automation, fitted_wrong_mass, total_mass)
    starts = np.flatnonzero(np.concatenate((np.array([True]), confidences[1:] != confidences[:-1])))
    values = confidences[starts]
    eligible = run.eligible[indices]
    errors = eligible & ~run.correct[indices]
    # Bound working memory while retaining vectorized suffix sums over all confidences.
    for begin in range(0, count, 128):
        end = min(begin + 128, count)
        ordered = weights[begin:end, indices]
        present = np.add.reduceat(ordered, starts, axis=1, dtype=np.int64) > 0
        wrong_mass = np.add.reduceat(ordered * errors, starts, axis=1, dtype=np.int64)
        auto_mass = np.add.reduceat(ordered * eligible, starts, axis=1, dtype=np.int64)
        wrong_suffix = np.cumsum(wrong_mass[:, ::-1], axis=1, dtype=np.int64)[:, ::-1]
        auto_suffix = np.cumsum(auto_mass[:, ::-1], axis=1, dtype=np.int64)[:, ::-1]
        denominators = limit_denominators[begin:end]
        allowed_mass = limit_numerators[begin:end] * total_mass[begin:end]
        zero_ok = denominators * wrong_suffix[:, 0] <= allowed_mass
        qualifies = present & (denominators[:, None] * wrong_suffix <= allowed_mass[:, None])
        found = np.any(qualifies, axis=1)
        first = np.argmax(qualifies, axis=1)
        selected = np.flatnonzero(found & ~zero_ok)
        rows = selected + begin
        columns = first[selected]
        taus[rows] = values[columns]
        fitted_wrong_mass[rows] = wrong_suffix[selected, columns]
        wrong[rows] = fitted_wrong_mass[rows] / total_mass[rows]
        automation[rows] = auto_suffix[selected, columns] / total_mass[rows]
        zero_rows = np.flatnonzero(zero_ok) + begin
        taus[zero_rows] = 0.0
        fitted_wrong_mass[zero_rows] = wrong_suffix[zero_ok, 0]
        wrong[zero_rows] = fitted_wrong_mass[zero_rows] / total_mass[zero_rows]
        automation[zero_rows] = auto_suffix[zero_ok, 0] / total_mass[zero_rows]
    return ResampledCalibration(taus, wrong, automation, fitted_wrong_mass, total_mass)
