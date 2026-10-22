"""Development-only selections and contract evidence (spec §8.1-§8.3).

Seed indices are vendor luna=0, haiku55=1; comparisons low-vs-none/off=0,
medium-vs-none/off=1, medium-vs-low=2. Within-intent multinomial counts are
replacement samples of the original items. Unreachable incumbent bootstrap fits
take tau=1.01 and zero wrong mass; the full-dev incumbent must remain reachable.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from math import comb, lcm
from typing import Literal

import numpy as np

from swapcheck.calibrate import Calibration, fit_candidate, fit_incumbent, fit_resamples
from swapcheck.outcomes import AnalysisRun, dev_weights, pair_runs

Vendor = Literal["luna", "haiku55"]
Comparison = Literal["low_vs_none", "medium_vs_none", "medium_vs_low"]
Level = Literal["low", "medium"]
VENDOR_INDEX: dict[Vendor, int] = {"luna": 0, "haiku55": 1}
COMPARISON_INDEX: dict[Comparison, int] = {"low_vs_none": 0, "medium_vs_none": 1, "medium_vs_low": 2}
BOOTSTRAP_RESAMPLES = 2000


@dataclass(frozen=True)
class GainResult:
    qualifies: bool
    difference: Fraction
    bootstrap_lower: float
    sign_p: Fraction
    n10: int
    n01: int
    dropped: int
    n: int
    incumbent: Calibration
    x: Calibration
    y: Calibration
    weights: tuple[Fraction, ...]
    seed: tuple[int, int, int, int]
    incumbent_unreachable_resamples: int


def sign_test(n10: int, n01: int) -> Fraction:
    """Exact one-sided P[Binomial(n10+n01, 1/2) >= n10]."""
    if n10 < 0 or n01 < 0:
        raise ValueError("discordant counts must be nonnegative")
    n = n10 + n01
    return Fraction(sum(comb(n, k) for k in range(n10, n + 1)), 1 << n)


def gain_test(
    incumbent: AnalysisRun,
    x: AnalysisRun,
    y: AnalysisRun,
    dev_counts: Mapping[str, int],
    cert_counts: Mapping[str, int],
    *,
    vendor: Vendor,
    comparison: Comparison,
) -> GainResult:
    """Re-fit all three thresholds in 2,000 paired within-intent resamples.

    dev_counts describe the original dev population, not the retained subset.
    The cert/dev ratios are renormalized after the three-arm join. Incomplete
    arms are not eligible for a gain test (select_reasoning excludes them).
    """
    if not all(run.complete for run in (incumbent, x, y)):
        raise ValueError("gain test requires complete runs")
    paired = pair_runs(incumbent, x, y)
    inc, x, y = paired.runs
    weights = dev_weights(inc.truth, dev_counts, cert_counts)
    inc_fit = fit_incumbent(inc, weights)
    x_fit = fit_candidate(x, weights, inc_fit.wrong)
    y_fit = fit_candidate(y, weights, inc_fit.wrong)
    x_auto, y_auto = x.auto_mask(x_fit.tau), y.auto_mask(y_fit.tau)
    n10 = int(np.count_nonzero(x_auto & ~y_auto))
    n01 = int(np.count_nonzero(y_auto & ~x_auto))
    p = sign_test(n10, n01)
    seed = (20261021, 81, VENDOR_INDEX[vendor], COMPARISON_INDEX[comparison])
    rng = np.random.default_rng(np.random.SeedSequence(seed))
    scale = lcm(*(dev_counts[intent] for intent in set(inc.truth)))
    integer_weights = {intent: cert_counts[intent] * scale // dev_counts[intent] for intent in set(inc.truth)}
    if max(integer_weights.values()) * len(inc) >= 2**62:
        raise OverflowError("Integer dev weights exceed the safe int64 resampling range")
    sample_weights = np.empty((BOOTSTRAP_RESAMPLES, len(inc)), dtype=np.int64)
    for intent in dict.fromkeys(inc.truth):
        indices = np.array([i for i, truth in enumerate(inc.truth) if truth == intent], dtype=np.intp)
        counts = rng.multinomial(len(indices), np.full(len(indices), 1.0 / len(indices)), BOOTSTRAP_RESAMPLES)
        sample_weights[:, indices] = counts * integer_weights[intent]
    inc_samples = fit_resamples(
        inc,
        sample_weights,
        np.ones(BOOTSTRAP_RESAMPLES, dtype=np.int64),
        np.full(BOOTSTRAP_RESAMPLES, 50, dtype=np.int64),
    )
    x_samples = fit_resamples(x, sample_weights, inc_samples.wrong_mass, inc_samples.total_mass)
    y_samples = fit_resamples(y, sample_weights, inc_samples.wrong_mass, inc_samples.total_mass)
    lower = float(np.quantile(x_samples.automation - y_samples.automation, 0.1, method="lower"))
    return GainResult(
        lower > 0 and p < Fraction(1, 10),
        x_fit.automation - y_fit.automation,
        lower,
        p,
        n10,
        n01,
        paired.dropped,
        len(inc),
        inc_fit,
        x_fit,
        y_fit,
        weights,
        seed,
        int(np.count_nonzero(inc_samples.tau == 1.01)),
    )


@dataclass(frozen=True)
class ReasoningSelection:
    selected: Level | None
    verdict: Literal["SELECTED", "NOT RUN"]
    reason: Literal["no dev gain"] | None
    qualified: tuple[Level, ...]
    comparisons: dict[Comparison, GainResult]
    budget_substitution: bool = False


def select_reasoning(
    incumbent: AnalysisRun,
    levels: Mapping[str, AnalysisRun | None],
    dev_counts: Mapping[str, int],
    cert_counts: Mapping[str, int],
    *,
    vendor: Vendor,
    medium_budget_dropped: bool = False,
) -> ReasoningSelection:
    """Choose R by §8.1; missing/incomplete levels are excluded from E.

    levels uses keys none, low, medium for luna, and off, low, medium for haiku55.
    medium_budget_dropped applies the specified low-in-E budget substitution.
    """
    baseline = levels.get("none" if vendor == "luna" else "off")
    if baseline is None or not baseline.complete:
        raise ValueError("a complete no-reasoning run is required")
    comparisons: dict[Comparison, GainResult] = {}
    qualified: list[Level] = []
    level_comparisons: tuple[tuple[Level, Comparison], ...] = (("low", "low_vs_none"), ("medium", "medium_vs_none"))
    for level, comparison in level_comparisons:
        run = levels.get(level)
        if run is None or not run.complete:
            continue
        result = gain_test(incumbent, run, baseline, dev_counts, cert_counts, vendor=vendor, comparison=comparison)
        comparisons[comparison] = result
        if result.qualifies:
            qualified.append(level)
    if not qualified:
        return ReasoningSelection(None, "NOT RUN", "no dev gain", (), comparisons)
    selected: Level = "low"
    if "medium" in qualified:
        if "low" not in qualified:
            selected = "medium"
        else:
            medium, low = levels["medium"], levels["low"]
            assert medium is not None and low is not None
            comparison_result = gain_test(
                incumbent, medium, low, dev_counts, cert_counts, vendor=vendor, comparison="medium_vs_low"
            )
            comparisons["medium_vs_low"] = comparison_result
            if comparison_result.qualifies:
                selected = "medium"
    substituted = medium_budget_dropped and selected == "medium" and "low" in qualified
    if substituted:
        selected = "low"
    return ReasoningSelection(selected, "SELECTED", None, tuple(qualified), comparisons, substituted)


@dataclass(frozen=True)
class JevSelection:
    selected: Literal["jev-c51", "jev-noul"]
    c51: Calibration
    noul: Calibration


def select_jev(c51: Calibration, noul: Calibration) -> JevSelection:
    """Compare exact Fraction automation; a tie belongs to jev-c51."""
    return JevSelection("jev-noul" if noul.automation > c51.automation else "jev-c51", c51, noul)


@dataclass(frozen=True)
class IterationResult:
    iteration: int
    changed_lines: int
    calibration: Calibration


@dataclass(frozen=True)
class AdaptationSelection:
    selected: IterationResult
    iterations: tuple[IterationResult, ...]
    adaptation_count: int


def select_adaptation(iterations: Sequence[IterationResult]) -> AdaptationSelection:
    """Select exact highest A then fewer changed lines, including iteration 0.

    If both specified keys tie, retain input order; the spec does not distinguish
    such iterations. Iteration numbers are 0 (starting prompt), then 1 through 3.
    """
    numbers = [result.iteration for result in iterations]
    if not iterations or len(set(numbers)) != len(numbers) or any(i not in range(4) for i in numbers):
        raise ValueError("expected distinct iterations numbered 0 through 3")
    if any(result.changed_lines < 0 for result in iterations):
        raise ValueError("changed lines must be nonnegative")
    selected = min(iterations, key=lambda result: (-result.calibration.automation, result.changed_lines))
    return AdaptationSelection(selected, tuple(iterations), sum(i != 0 for i in numbers))
