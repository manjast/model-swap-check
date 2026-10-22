from __future__ import annotations

from fractions import Fraction

import numpy as np
import pytest

from swapcheck.calibrate import (
    VoidExperiment,
    fit_candidate,
    fit_incumbent,
    fit_resamples,
    thresholds,
)
from swapcheck.outcomes import AnalysisRun
from swapcheck.records import Split, Status


def _run(
    confidences: list[float],
    *,
    wrong: tuple[int, ...] = (),
    noul_rejected: tuple[int, ...] = (),
    statuses: tuple[Status, ...] | None = None,
    intents: tuple[str | None, ...] | None = None,
    split: Split = "dev",
) -> AnalysisRun:
    count = len(confidences)
    if statuses is None:
        statuses = tuple("ok" for _ in range(count))
    intents = intents if intents is not None else tuple("other" if i in wrong else "card" for i in range(count))
    return AnalysisRun(
        split=split,
        item_ids=tuple(str(i) for i in range(count)),
        truth=("card",) * count,
        slices=("in_scope",) * count,
        status=statuses,
        intent=intents,
        confidence=np.array(confidences, dtype=np.float64),
        eligible=np.array(
            [
                status == "ok" and intent is not None and intent != "out_of_scope" and i not in noul_rejected
                for i, (status, intent) in enumerate(zip(statuses, intents, strict=True))
            ],
            dtype=np.bool_,
        ),
        correct=np.array([intent == "card" for intent in intents], dtype=np.bool_),
    )


def test_c1_incumbent_selects_smallest_supported_threshold_inclusively() -> None:
    run = _run([0.1, 0.4, 0.7, 0.9], wrong=(0, 1))
    result = fit_incumbent(run, (Fraction(3, 100), Fraction(1, 100), Fraction(46, 100), Fraction(1, 2)))
    assert result.tau == 0.4
    assert result.wrong == Fraction(1, 100)
    assert result.automation == Fraction(97, 100)


def test_c1_incumbent_zero_when_risk_already_at_exact_limit() -> None:
    run = _run([0.2, 0.8], wrong=(0,))
    result = fit_incumbent(run, (Fraction(1, 50), Fraction(49, 50)))
    assert (result.tau, result.wrong, result.automation) == (0.0, Fraction(1, 50), Fraction(1))


def test_c1_exact_boundary_above_limit_is_not_rounded_into_acceptance() -> None:
    run = _run([0.2, 0.8], wrong=(0,))
    weight = Fraction(1, 50) + Fraction(1, 10**30)
    result = fit_incumbent(run, (weight, 1 - weight))
    assert (result.tau, result.wrong, result.automation) == (0.8, Fraction(0), 1 - weight)
    candidate = fit_candidate(run, (weight, 1 - weight), Fraction(1, 50))
    assert candidate.tau == 0.8


def test_c1_threshold_support_excludes_invalid_errors_and_oos_but_not_noul() -> None:
    run = _run(
        [0.1, 0.2, 0.3, 0.4, 0.4, 0.6],
        statuses=("invalid_output", "api_error", "ok", "ok", "ok", "ok"),
        intents=("card", "card", "out_of_scope", "card", "card", "card"),
        noul_rejected=(5,),
    )
    np.testing.assert_array_equal(thresholds(run), [0.0, 0.4, 0.6])


def test_c1_noul_escalation_is_applied_before_risk_and_automation() -> None:
    run = _run([0.2, 0.3, 0.8], wrong=(0,), noul_rejected=(1,))
    weights = (Fraction(1, 10), Fraction(1, 5), Fraction(7, 10))
    result = fit_candidate(run, weights, Fraction(0))
    assert (result.tau, result.wrong, result.automation) == (0.3, Fraction(0), Fraction(7, 10))
    rejected_wrong = _run([0.9, 0.8], wrong=(0,), noul_rejected=(0,))
    result = fit_incumbent(rejected_wrong, (Fraction(1, 2), Fraction(1, 2)))
    assert (result.tau, result.wrong, result.automation) == (0.0, Fraction(0), Fraction(1, 2))


def test_c1_unreachable_incumbent_voids_and_candidate_escalates_all() -> None:
    run = _run([0.4, 1.0], wrong=(1,))
    weights = (Fraction(1, 2), Fraction(1, 2))
    with pytest.raises(VoidExperiment, match="Incumbent"):
        fit_incumbent(run, weights)
    result = fit_candidate(run, weights, Fraction(1, 50))
    assert (result.tau, result.wrong, result.automation) == (1.01, Fraction(0), Fraction(0))


def test_c1_candidate_matches_weighted_not_unweighted_incumbent_risk() -> None:
    weights = (Fraction(1, 100), Fraction(9, 100), Fraction(9, 10))
    incumbent = fit_incumbent(_run([0.1, 0.3, 0.9], wrong=(0,)), weights)
    candidate = fit_candidate(_run([0.2, 0.4, 0.8], wrong=(0, 1)), weights, incumbent.wrong)
    assert incumbent.wrong == Fraction(1, 100)
    assert (candidate.tau, candidate.wrong, candidate.automation) == (0.8, Fraction(0), Fraction(9, 10))
    # Exact equality is accepted, including a rational not representable as a float.
    equal = fit_candidate(_run([0.2, 0.4, 0.8], wrong=(0,)), weights, incumbent.wrong)
    assert equal.tau == 0.0
    assert equal.wrong == incumbent.wrong


@pytest.mark.parametrize("split", ["cert", "aa", "pilot", "examples"])
def test_c1_all_threshold_and_fitting_entrypoints_refuse_nondev(split: Split) -> None:
    run = _run([0.5], split=split)
    with pytest.raises(ValueError, match="dev"):
        thresholds(run)
    with pytest.raises(ValueError, match="dev"):
        fit_incumbent(run, (Fraction(1),))
    with pytest.raises(ValueError, match="dev"):
        fit_candidate(run, (Fraction(1),), Fraction(0))
    with pytest.raises(ValueError, match="dev"):
        fit_resamples(run, np.ones((1, 1), dtype=np.int64), np.zeros(1, dtype=np.int64), np.ones(1, dtype=np.int64))


def test_c1_resamples_exclude_absent_thresholds_and_preserve_original_item_weights() -> None:
    run = _run([0.2, 0.3, 0.8], wrong=(0,))
    weights = np.array([[1, 0, 9], [1, 1, 8], [0, 2, 8]], dtype=np.int64)
    result = fit_resamples(run, weights, np.zeros(3, dtype=np.int64), np.ones(3, dtype=np.int64))
    np.testing.assert_array_equal(result.tau, [0.8, 0.3, 0.0])
    np.testing.assert_allclose(result.wrong, [0.0, 0.0, 0.0])
    np.testing.assert_allclose(result.automation, [0.9, 0.9, 1.0])


def test_c1_resamples_keep_present_noul_threshold_support() -> None:
    run = _run([0.2, 0.3, 0.8], wrong=(0,), noul_rejected=(1,))
    result = fit_resamples(
        run, np.array([[1, 2, 7], [1, 0, 9]], dtype=np.int64), np.zeros(2, dtype=np.int64), np.ones(2, dtype=np.int64)
    )
    np.testing.assert_array_equal(result.tau, [0.3, 0.8])
    np.testing.assert_allclose(result.automation, [0.7, 0.9])


def test_c1_resamples_never_discard_unreachable_incumbent_samples() -> None:
    run = _run([1.0, 0.5], wrong=(0,))
    weights = np.array([[0, 2], [1, 1], [0, 2]], dtype=np.int64)
    result = fit_resamples(run, weights, np.ones(3, dtype=np.int64), np.full(3, 50, dtype=np.int64))
    np.testing.assert_array_equal(result.tau, [0.0, 1.01, 0.0])
    np.testing.assert_array_equal(result.wrong, [0.0, 0.0, 0.0])
    np.testing.assert_array_equal(result.automation, [1.0, 0.0, 1.0])
    np.testing.assert_array_equal(result.wrong_mass, [0, 0, 0])
    assert int(np.count_nonzero(result.tau == 1.01)) == 1
    candidate = fit_resamples(_run([0.2, 0.8], wrong=(0,)), weights, result.wrong_mass, result.total_mass)
    np.testing.assert_array_equal(candidate.tau, [0.0, 0.8, 0.0])
    np.testing.assert_array_equal(candidate.wrong_mass, [0, 0, 0])
    np.testing.assert_array_equal(candidate.automation, [1.0, 0.5, 1.0])


def test_c1_resamples_zero_limit_equality_and_tied_confidences() -> None:
    run = _run([0.0, 0.4, 0.4, 0.9], wrong=(0, 1))
    result = fit_resamples(
        run, np.array([[1, 2, 3, 4]], dtype=np.int64), np.array([1], dtype=np.int64), np.array([5], dtype=np.int64)
    )
    np.testing.assert_array_equal(result.tau, [0.4])
    np.testing.assert_allclose(result.wrong, [0.2])
    np.testing.assert_allclose(result.automation, [0.9])


def test_c1_no_prediction_support_still_has_zero_threshold() -> None:
    run = _run([0.8, 0.9], statuses=("invalid_output", "ok"), intents=(None, "out_of_scope"))
    weights = (Fraction(1, 2), Fraction(1, 2))
    exact = fit_incumbent(run, weights)
    assert (exact.tau, exact.wrong, exact.automation) == (0.0, Fraction(0), Fraction(0))
    batched = fit_resamples(
        run,
        np.array([[1, 1], [2, 0]], dtype=np.int64),
        np.zeros(2, dtype=np.int64),
        np.ones(2, dtype=np.int64),
    )
    np.testing.assert_array_equal(batched.tau, [0.0, 0.0])
    np.testing.assert_array_equal(batched.wrong, [0.0, 0.0])
    np.testing.assert_array_equal(batched.automation, [0.0, 0.0])


def test_c1_batched_suffix_fits_match_independent_threshold_enumeration() -> None:
    run = _run(
        [0.0, 0.2, 0.2, 0.4, 0.6, 0.8, 1.0, 0.3],
        wrong=(0, 2, 4, 6),
        noul_rejected=(3,),
        statuses=("ok", "ok", "ok", "ok", "ok", "ok", "ok", "invalid_output"),
    )
    rng = np.random.default_rng(1783)
    # More than one internal chunk; repeated counts attach to original items.
    weights = rng.multinomial(20, np.full(8, 1 / 8), size=275).astype(np.int64)
    numerators = np.resize(np.array([0, 12, 31], dtype=np.int64), 275)
    denominators = np.full(275, 100, dtype=np.int64)
    result = fit_resamples(run, weights, numerators, denominators)
    for row, sample in enumerate(weights):
        support = sorted(
            {0.0}
            | {
                float(run.confidence[i])
                for i in range(len(run))
                if sample[i] > 0 and run.status[i] == "ok" and run.intent[i] != "out_of_scope"
            }
        )
        expected_tau = 1.01
        expected_wrong = Fraction(0)
        expected_auto = Fraction(0)
        total = sum(map(int, sample))
        limit = Fraction(int(numerators[row]), int(denominators[row]))
        for tau in support:
            auto = run.eligible & (run.confidence >= tau)
            error = Fraction(sum(int(sample[i]) for i in range(len(run)) if auto[i] and not run.correct[i]), total)
            if error <= limit:
                expected_tau = tau
                expected_wrong = error
                expected_auto = Fraction(sum(int(sample[i]) for i in range(len(run)) if auto[i]), total)
                break
        assert result.tau[row] == expected_tau
        assert result.wrong[row] == float(expected_wrong)
        assert result.automation[row] == float(expected_auto)


def test_c1_resampled_incumbent_recalibrates_at_registered_limit() -> None:
    run = _run([0.1, 0.4, 0.7, 0.9], wrong=(0, 1))
    weights = np.array([[3, 1, 46, 50], [0, 2, 48, 50]], dtype=np.int64)
    result = fit_resamples(run, weights, np.ones(2, dtype=np.int64), np.full(2, 50, dtype=np.int64))
    np.testing.assert_array_equal(result.tau, [0.4, 0.0])
    np.testing.assert_allclose(result.wrong, [0.01, 0.02])
    np.testing.assert_allclose(result.automation, [0.97, 1.0])


def test_c1_resampled_rational_boundary_matches_exact_candidate() -> None:
    run = _run([0.2, 0.4, 0.8], wrong=(0, 1))
    exact = fit_candidate(run, (Fraction(1, 10), Fraction(1, 5), Fraction(7, 10)), Fraction(3, 10))
    batched = fit_resamples(
        run, np.array([[1, 2, 7]], dtype=np.int64), np.array([3], dtype=np.int64), np.array([10], dtype=np.int64)
    )
    assert exact.tau == batched.tau[0] == 0
    assert batched.wrong[0] == float(exact.wrong) == 0.3
    assert batched.automation[0] == float(exact.automation) == 1
    assert (int(batched.wrong_mass[0]), int(batched.total_mass[0])) == (3, 10)


def test_c1_random_integer_batches_match_exact_fraction_fits_at_boundaries() -> None:
    run = _run([0.0, 0.2, 0.2, 0.4, 0.6, 0.8, 1.0, 0.3], wrong=(0, 2, 4, 6), noul_rejected=(3,))
    rng = np.random.default_rng(17382)
    masses = rng.integers(0, 101, size=(300, len(run)), dtype=np.int64)
    # Limits are wrong rates at actual thresholds, hence include inclusive ties.
    cutoffs = rng.choice([0.0, 0.2, 0.4, 0.8, 1.0], size=300)
    numerators = np.array(
        [
            sum(int(w) for w, a, c in zip(mass, run.auto_mask(float(tau)), run.correct, strict=True) if a and not c)
            for mass, tau in zip(masses, cutoffs, strict=True)
        ],
        dtype=np.int64,
    )
    denominators = masses.sum(axis=1)
    batched = fit_resamples(run, masses, numerators, denominators)
    for i, mass in enumerate(masses):
        present = [int(j) for j in np.flatnonzero(mass)]
        selected = run.take(present)
        weights = tuple(Fraction(int(mass[j]), int(denominators[i])) for j in present)
        exact = fit_candidate(selected, weights, Fraction(int(numerators[i]), int(denominators[i])))
        assert batched.tau[i] == exact.tau
        assert batched.wrong[i] == float(exact.wrong)
        assert batched.automation[i] == float(exact.automation)
        try:
            exact_inc = fit_incumbent(selected, weights)
        except VoidExperiment:
            fallback = fit_resamples(
                selected, mass[present][None, :], np.ones(1, dtype=np.int64), np.full(1, 50, dtype=np.int64)
            )
            assert fallback.tau[0] == 1.01
            assert fallback.wrong[0] == fallback.automation[0] == fallback.wrong_mass[0] == 0
        else:
            resampled_inc = fit_resamples(
                selected,
                mass[present][None, :],
                np.ones(1, dtype=np.int64),
                np.full(1, 50, dtype=np.int64),
            )
            assert resampled_inc.tau[0] == exact_inc.tau
            assert resampled_inc.wrong[0] == float(exact_inc.wrong)
            assert resampled_inc.automation[0] == float(exact_inc.automation)


def test_c1_resampling_rejects_integer_overflow_before_arithmetic() -> None:
    run = _run([0.2, 0.8], wrong=(0,))
    with pytest.raises(OverflowError):
        fit_resamples(
            run, np.array([[2**61, 2**61]], dtype=np.int64), np.ones(1, dtype=np.int64), np.full(1, 50, dtype=np.int64)
        )
    with pytest.raises(OverflowError):
        fit_resamples(
            run, np.array([[1, 1]], dtype=np.int64), np.ones(1, dtype=np.int64), np.full(1, 2**62, dtype=np.int64)
        )
