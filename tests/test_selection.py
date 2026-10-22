"""T-X1/T-X2/T-X3: exact selections and recalibrating, paired gain evidence."""

from __future__ import annotations

from fractions import Fraction
from math import sqrt
from statistics import NormalDist
from time import perf_counter

import numpy as np
import pytest

from swapcheck.calibrate import Calibration
from swapcheck.outcomes import AnalysisRun
from swapcheck.records import Status
from swapcheck.selection import (
    IterationResult,
    gain_test,
    select_adaptation,
    select_jev,
    select_reasoning,
    sign_test,
)


def run(
    auto: np.ndarray[tuple[int], np.dtype[np.bool_]],
    *,
    wrong: np.ndarray[tuple[int], np.dtype[np.bool_]] | None = None,
    confidence: np.ndarray[tuple[int], np.dtype[np.float64]] | None = None,
    truth: tuple[str, ...] | None = None,
    api: tuple[int, ...] = (),
    complete: bool = True,
) -> AnalysisRun:
    n = len(auto)
    statuses: list[Status] = ["ok" if a else "invalid_output" for a in auto]
    eligible = auto.copy()
    for i in api:
        statuses[i] = "api_error"
        eligible[i] = False
    errors = np.zeros(n, dtype=np.bool_) if wrong is None else wrong
    return AnalysisRun(
        "dev",
        tuple(map(str, range(n))),
        ("a",) * n if truth is None else truth,
        ("cards",) * n,
        tuple(statuses),
        tuple("a" if a else None for a in auto),
        np.ones(n) if confidence is None else confidence,
        eligible,
        auto & ~errors,
        complete,
    )


def fixed_fixture(n10: int, n01: int, n: int = 3075) -> tuple[AnalysisRun, AnalysisRun, AnalysisRun]:
    x_auto, y_auto = np.zeros(n, dtype=np.bool_), np.zeros(n, dtype=np.bool_)
    x_auto[:n10] = True
    y_auto[n10 : n10 + n01] = True
    return run(np.ones(n, dtype=np.bool_)), run(x_auto), run(y_auto)


def normal_lower(n10: int, n01: int, n: int) -> float:
    difference = (n10 - n01) / n
    return difference - NormalDist().inv_cdf(0.9) * sqrt(((n10 + n01) / n - difference**2) / n)


@pytest.mark.parametrize(("n10", "n01", "qualifies"), [(62, 31, True), (500, 469, False)])
def test_t_x2_fixed_tau_bootstrap_agrees_with_normal(n10: int, n01: int, qualifies: bool) -> None:
    incumbent, x, y = fixed_fixture(n10, n01)
    begin = perf_counter()
    result = gain_test(incumbent, x, y, {"a": 3075}, {"a": 9758}, vendor="luna", comparison="low_vs_none")
    elapsed = perf_counter() - begin
    print(f"bootstrap n10={n10}, n01={n01}: {elapsed:.3f}s")
    assert result.qualifies is qualifies
    assert result.difference == Fraction(31, 3075)
    assert (result.n10, result.n01, result.n, result.dropped) == (n10, n01, 3075, 0)
    assert abs(result.bootstrap_lower - normal_lower(n10, n01, 3075)) < 0.001
    assert (result.incumbent.tau, result.x.tau, result.y.tau) == (0, 0, 0)
    assert result.seed == (20261021, 81, 0, 0)


def test_t_x2_recalibration_noise_widens_interval() -> None:
    n = 3075
    all_auto = np.ones(n, dtype=np.bool_)
    errors = np.arange(n) < 61
    inc_confidence = np.where(errors, 0.9, 1.0)
    x_confidence = np.where(np.arange(n) < 1061, 0.8, 1.0)
    incumbent = run(all_auto, wrong=errors, confidence=inc_confidence)
    x = run(all_auto, wrong=errors, confidence=x_confidence)
    y_auto = np.arange(n) >= 200
    y = run(y_auto)
    result = gain_test(incumbent, x, y, {"a": n}, {"a": n}, vendor="luna", comparison="medium_vs_none")
    # At the observed fit, all of X auto-routes, Y omits 200, so the fixed-tau
    # discordance is 200/3075. Resamples crossing 2% move X's tau past 0.8,
    # losing its 1,000 low-confidence correct items as well as the 61 errors.
    assert result.difference == Fraction(200, n)
    assert result.bootstrap_lower < normal_lower(200, 0, n) - 0.1
    assert not result.qualifies


def test_t_x2_exact_small_count_guard_despite_strong_weighted_bound() -> None:
    truth = ("rare",) * 2 + ("a",) * 20
    inc = run(np.ones(22, dtype=np.bool_), truth=truth)
    x = run(np.arange(22) < 2, truth=truth)
    y = run(np.zeros(22, dtype=np.bool_), truth=truth)
    result = gain_test(
        inc, x, y, {"rare": 2, "a": 20}, {"rare": 90, "a": 10}, vendor="haiku55", comparison="medium_vs_low"
    )
    repeat = gain_test(
        inc, x, y, {"rare": 2, "a": 20}, {"rare": 90, "a": 10}, vendor="haiku55", comparison="medium_vs_low"
    )
    assert repeat == result
    assert result.bootstrap_lower == pytest.approx(0.9)
    assert result.sign_p == Fraction(1, 4)
    assert not result.qualifies
    assert sign_test(0, 0) == 1
    assert sign_test(4, 0) == Fraction(1, 16)


def test_t_x2_three_arm_api_drops_renormalize_weights() -> None:
    n = 10
    all_auto = np.ones(n, dtype=np.bool_)
    inc = run(all_auto, api=(0,))
    x = run(all_auto, api=(1,))
    y = run(np.zeros(n, dtype=np.bool_), api=(2,))
    result = gain_test(inc, x, y, {"a": n}, {"a": 200}, vendor="luna", comparison="low_vs_none")
    assert (result.dropped, result.n, result.n10, result.n01) == (3, 7, 7, 0)
    assert result.weights == (Fraction(1, 7),) * 7
    assert result.difference == 1
    assert result.qualifies


def test_t_x2_selection_empty_skipped_incomplete_and_cheaper_level() -> None:
    n = 80
    inc = run(np.ones(n, dtype=np.bool_))
    none = run(np.zeros(n, dtype=np.bool_))
    low = run(np.arange(n) < 20)
    medium = run(np.arange(n) < 21)
    counts = {"a": n}
    empty = select_reasoning(
        inc,
        {"none": none, "low": None, "medium": run(np.ones(n, dtype=np.bool_), complete=False)},
        counts,
        counts,
        vendor="luna",
    )
    assert (empty.selected, empty.verdict, empty.reason, empty.qualified) == (None, "NOT RUN", "no dev gain", ())
    tie = select_reasoning(inc, {"none": none, "low": low, "medium": medium}, counts, counts, vendor="luna")
    assert tie.qualified == ("low", "medium")
    assert tie.selected == "low"
    assert not tie.comparisons["medium_vs_low"].qualifies
    medium_only = select_reasoning(inc, {"none": none, "medium": medium}, counts, counts, vendor="luna")
    assert medium_only.selected == "medium"
    medium_qualifies = select_reasoning(
        inc, {"none": none, "low": none, "medium": medium}, counts, counts, vendor="luna"
    )
    assert medium_qualifies.selected == "medium"
    assert medium_qualifies.qualified == ("medium",)
    no_gain = select_reasoning(inc, {"none": low, "low": low}, counts, counts, vendor="luna")
    assert (no_gain.verdict, no_gain.reason) == ("NOT RUN", "no dev gain")


def test_t_x2_medium_gains_and_budget_substitutes_qualified_low() -> None:
    n = 80
    inc = run(np.ones(n, dtype=np.bool_))
    levels = {"off": run(np.zeros(n, dtype=np.bool_)), "low": run(np.arange(n) < 20), "medium": run(np.arange(n) < 40)}
    counts = {"a": n}
    selected = select_reasoning(inc, levels, counts, counts, vendor="haiku55")
    assert selected.selected == "medium"
    substitute = select_reasoning(inc, levels, counts, counts, vendor="haiku55", medium_budget_dropped=True)
    assert substitute.selected == "low" and substitute.budget_substitution


def cal(automation: Fraction) -> Calibration:
    return Calibration(0.5, Fraction(1, 100), automation)


def test_t_x1_adaptation_exact_ties_limit_and_iteration_zero() -> None:
    # These two fractions round to the same binary float, but are not tied.
    near = Fraction(1, 2) + Fraction(1, 10**30)
    iterations = [
        IterationResult(0, 0, cal(Fraction(1, 2))),
        IterationResult(1, 2, cal(near)),
        IterationResult(2, 1, cal(near)),
        IterationResult(3, 3, cal(Fraction(1, 3))),
    ]
    result = select_adaptation(iterations)
    assert result.selected.iteration == 2
    assert result.adaptation_count == 3
    assert result.iterations == tuple(iterations)
    assert select_adaptation([iterations[0], IterationResult(1, 2, cal(Fraction(1, 2)))]).selected.iteration == 0
    with pytest.raises(ValueError):
        select_adaptation([*iterations, IterationResult(4, 1, cal(near))])


def test_t_x3_jev_exact_higher_and_c51_tie() -> None:
    half = cal(Fraction(1, 2))
    higher = cal(Fraction(1, 2) + Fraction(1, 10**30))
    assert select_jev(half, half).selected == "jev-c51"
    assert select_jev(half, higher).selected == "jev-noul"
    assert select_jev(higher, half).selected == "jev-c51"


def test_t_x2_unreachable_incumbent_resamples_are_counted_without_aborting() -> None:
    n = 50
    errors = np.arange(n) == 0
    incumbent = run(np.ones(n, dtype=np.bool_), wrong=errors)
    x = run(np.ones(n, dtype=np.bool_), wrong=errors, confidence=np.where(errors, 0.2, 1.0))
    y = run(np.zeros(n, dtype=np.bool_))
    result = gain_test(incumbent, x, y, {"a": n}, {"a": n}, vendor="luna", comparison="low_vs_none")
    # Full-dev W is exactly 1/50. With all incumbent confidences at one, its
    # bootstrap fit is unreachable iff the sole wrong item is drawn twice or more.
    rng = np.random.default_rng(np.random.SeedSequence([20261021, 81, 0, 0]))
    wrong_draws = rng.multinomial(n, np.full(n, 1 / n), 2000)[:, 0]
    assert result.incumbent_unreachable_resamples == int(np.count_nonzero(wrong_draws >= 2))
    assert 0 < result.incumbent_unreachable_resamples < 2000
    assert result.incumbent.tau == result.x.tau == 0
    assert result.incumbent.wrong == Fraction(1, 50)
    assert result.qualifies
