"""T-S1-T-S4, T-S6 and bootstrap T-S7: paired inference (spec §7)."""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path
from statistics import NormalDist
from types import ModuleType

import numpy as np
import pytest
from numpy.typing import NDArray

from swapcheck import stats

SLICES = {
    "cards": 1407,
    "card_payments": 1473,
    "cash": 966,
    "transfers": 1328,
    "top_ups": 844,
    "account_other": 1143,
    "out_of_scope": 2597,
}
SIMULATIONS = 16_000
Z95 = NormalDist().inv_cdf(0.95)


def _power_module() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "analysis" / "power.py"
    spec = importlib.util.spec_from_file_location("standalone_power", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("n10,n01,n", [(350, 150, 10000), (100, 100, 5000), (30, 40, 9758)])
def test_t_s1_restricted_likelihood_and_inversion(n10: int, n01: int, n: int) -> None:
    estimate = (n10 - n01) / n
    assert stats.tango_score(n10, n01, n, estimate) == 0
    for delta in (-0.04, -0.005, 0.0, 0.02, 0.08):
        q = stats.restricted_mle(n10, n01, n, delta)
        # Differentiate the multinomial log likelihood in its nuisance probability p01.
        derivative = n10 / (q + delta) + n01 / q - 2 * (n - n10 - n01) / (1 - 2 * q - delta)
        assert abs(derivative) < 1e-9
    bounds = stats.paired_bounds(n10, n01, n)
    assert stats.tango_score(n10, n01, n, bounds.upper) == pytest.approx(-Z95, abs=1e-9)
    assert stats.tango_score(n10, n01, n, bounds.lower) == pytest.approx(Z95, abs=1e-9)
    assert abs(bounds.upper - bounds.wald_upper) < 0.0005
    assert abs(bounds.lower - bounds.wald_lower) < 0.0005


@pytest.mark.parametrize("n10,n01", [(0, 0), (50, 0), (0, 50), (25, 25), (100, 0), (0, 100)])
def test_t_s2_finite_boundary_cases(n10: int, n01: int) -> None:
    bounds = stats.paired_bounds(n10, n01, 100)
    assert all(math.isfinite(value) for value in (bounds.lower, bounds.upper, bounds.wald_lower, bounds.wald_upper))
    assert -1 <= bounds.lower <= bounds.estimate <= bounds.upper <= 1
    assert stats.gate_g1(n10, n01, 100, 0.02).status in ("PASS", "FAIL", "UNRESOLVED")
    assert stats.gate_g3(n10, n01, 100).status in ("PASS", "FAIL", "UNRESOLVED")
    slices = {name: (n10, n01, 100) for name in SLICES}
    assert stats.gate_g2(slices, 0.02).status in ("PASS", "FAIL", "UNRESOLVED")


def test_t_s2_zero_discordance_closed_form() -> None:
    # With no discordance, the score is -sqrt(n*delta/(1-delta)) for positive delta.
    bounds = stats.paired_bounds(0, 0, 100)
    endpoint = Z95**2 / (100 + Z95**2)
    assert bounds.upper == pytest.approx(endpoint, abs=1e-12)
    assert bounds.lower == pytest.approx(-endpoint, abs=1e-12)
    assert bounds.wald_lower == bounds.wald_upper == 0
    assert stats.gate_g1(0, 0, 100, 0.01).status == "UNRESOLVED"
    assert stats.gate_g1(0, 0, 100, 0.03).status == "PASS"


@pytest.mark.parametrize("confidence", [0.95, stats.SLICE_HARM_CONFIDENCE])
@pytest.mark.parametrize("margin", [-0.03, 0.005, 0.02])
def test_score_at_margin_is_equivalent_to_gate(confidence: float, margin: float) -> None:
    # Exercise actual gate inversion, including nuisance-MLE boundary cases.
    cells = np.array([(0, 0), (1, 0), (0, 1), (90, 0), (0, 90), (25, 25), (100, 0), (0, 100)])
    actual = stats.certifies_upper(cells[:, 0], cells[:, 1], 100, margin, confidence)
    expected = [stats.gate_g1(int(a), int(b), 100, margin, confidence).status == "PASS" for a, b in cells]
    np.testing.assert_array_equal(actual, expected)
    for (a, b), score in zip(cells, stats.tango_scores(cells[:, 0], cells[:, 1], 100, margin), strict=True):
        assert score == pytest.approx(stats.tango_score(int(a), int(b), 100, margin), abs=1e-12)


@pytest.mark.parametrize("p_disc", [0.03, 0.08])
@pytest.mark.parametrize("n,margin", [(sum(SLICES.values()), 0.005), *[(n, 0.02) for n in SLICES.values()]])
def test_t_s3_false_release_at_margin(p_disc: float, n: int, margin: float) -> None:
    rng = np.random.default_rng(np.random.SeedSequence([20261021, n, round(p_disc * 100)]))
    draws = rng.multinomial(n, [(p_disc + margin) / 2, (p_disc - margin) / 2, 1 - p_disc], size=SIMULATIONS)
    certified = stats.certifies_upper(draws[:, 0], draws[:, 1], n, margin)
    limit = 0.05 + 2 * math.sqrt(0.05 * 0.95 / SIMULATIONS)
    assert float(certified.mean()) <= limit


@pytest.mark.parametrize("p_disc", [0.03, 0.08])
def test_t_s4_power_matches_standalone_without_calibration(p_disc: float) -> None:
    rng = np.random.default_rng(5729)
    totals = np.zeros((SIMULATIONS, 2), dtype=np.int64)
    joint = np.ones(SIMULATIONS, dtype=np.bool_)
    observed: dict[str, float] = {}
    for name, n in SLICES.items():
        draws = rng.multinomial(n, [p_disc / 2, p_disc / 2, 1 - p_disc], size=SIMULATIONS)
        totals += draws[:, :2]
        passed = stats.certifies_upper(draws[:, 0], draws[:, 1], n, 0.02)
        observed[name] = float(passed.mean())
        joint &= passed
    overall = stats.certifies_upper(totals[:, 0], totals[:, 1], sum(SLICES.values()), 0.005)
    observed["overall"] = float(overall.mean())
    observed["joint"] = float((overall & joint).mean())
    power = _power_module().simulate(
        dict.fromkeys(SLICES, p_disc), 0.005, 0.02, dev_n=None, sims=SIMULATIONS, seed=8239
    )
    for name, rate in observed.items():
        assert rate == pytest.approx(power[name], abs=0.015)


def test_gate_directions_and_slice_harm_correction() -> None:
    assert stats.gate_g1(10, 30, 1000, 0.02).status == "PASS"
    assert stats.gate_g1(70, 10, 1000, 0.02).status == "FAIL"
    assert stats.gate_g1(30, 10, 1000, 0.02).status == "UNRESOLVED"
    assert stats.gate_g3(30, 10, 1000).status == "PASS"
    assert stats.gate_g3(10, 70, 1000).status == "FAIL"
    assert stats.gate_g3(10, 40, 1000).status == "UNRESOLVED"
    # This slice fails at 95%, but not at the 7-slice corrected harm level.
    assert stats.gate_g1(43, 10, 1000, 0.02).status == "FAIL"
    counts = dict.fromkeys(SLICES, (0, 0, 1000))
    counts["cash"] = (43, 10, 1000)
    result = stats.gate_g2(counts, 0.02)
    assert result.status == result.slices["cash"].status == "UNRESOLVED"
    assert result.slices["cards"].status == "PASS"
    counts["cash"] = (70, 10, 1000)
    assert stats.gate_g2(counts, 0.02).status == "FAIL"
    assert stats.gate_g4(995, 1000) == "PASS"
    assert stats.gate_g4(994, 1000) == "FAIL"


def test_explicit_confidence_changes_gate() -> None:
    # No discordance: U95 = .002698, U99.286 = .005968 for n=1000.
    assert stats.gate_g1(0, 0, 1000, 0.005).status == "PASS"
    assert stats.gate_g1(0, 0, 1000, 0.005, stats.SLICE_HARM_CONFIDENCE).status == "UNRESOLVED"
    assert stats.gate_g3(0, 0, 100).status == "PASS"
    assert stats.gate_g3(0, 0, 100, stats.SLICE_HARM_CONFIDENCE).status == "UNRESOLVED"


@pytest.mark.parametrize("direction,margin", [("upper", 0.02), ("lower", -0.03)])
def test_t_s6_sample_size_closed_form(direction: str, margin: float) -> None:
    # p_disc=.08, d=.01, and target gaps .01 (W) or .04 (A).
    factor = (NormalDist().inv_cdf(0.95) + NormalDist().inv_cdf(0.8)) ** 2
    if direction == "upper":
        actual = stats.sample_size_needed(45, 35, 1000, margin)
        expected = math.ceil(0.08 * factor / 0.01**2)
    else:
        actual = stats.sample_size_needed(45, 35, 1000, margin, direction="lower")
        expected = math.ceil(0.08 * factor / 0.04**2)
    assert actual.n == expected
    assert actual.reason is None
    assert stats.sample_size_needed(0, 0, 100, 0.01) == stats.SampleSizeResult(None, "no discordant pairs observed")


def test_t_s6_unreachable_in_both_directions() -> None:
    for n10, n01 in [(30, 10), (40, 10)]:
        result = stats.sample_size_needed(n10, n01, 1000, 0.02)
        assert result.n is None
        assert result.reason == "not reachable at this point estimate"
    for n10, n01 in [(10, 40), (10, 50)]:
        assert stats.sample_size_needed(n10, n01, 1000, -0.03, direction="lower").n is None


def _heterogeneous_items() -> tuple[list[str], list[str], NDArray[np.bool_]]:
    intents, slices = [], []
    for name in SLICES:
        for i in range(10):
            intents.extend([f"{name}-{i}"] * 100)
            slices.extend([name] * 100)
    concentrated = np.tile(np.repeat(np.arange(10) == 0, 100), 7)
    return intents, slices, concentrated


@pytest.mark.parametrize("gate", ["G1", "G2"])
def test_t_s7_cluster_bootstrap_changes_heterogeneous_wrong_auto_gate(gate: stats.GateName) -> None:
    intents, slices, candidate = _heterogeneous_items()
    incumbent = np.zeros(candidate.size, dtype=np.bool_)
    result = stats.cluster_bootstrap(
        intents, slices, candidate, incumbent, list(SLICES), gate=gate, decision_index=2, margin=0.15
    )
    assert result.original_status == "PASS"
    assert result.bootstrap_status == "UNRESOLVED"
    assert result.changed
    assert any(bounds.upper > 0.15 for bounds in result.bounds.values())
    assert result == stats.cluster_bootstrap(
        intents, slices, candidate, incumbent, list(SLICES), gate=gate, decision_index=2, margin=0.15
    )


def test_t_s7_cluster_bootstrap_changes_automation_gate() -> None:
    intents, slices, concentrated = _heterogeneous_items()
    # Exactly 20/100 losses in one intent per slice: d=-.02; clustering widens L below -.03.
    incumbent = concentrated & (np.arange(concentrated.size) % 100 < 20)
    candidate = np.zeros(incumbent.size, dtype=np.bool_)
    result = stats.cluster_bootstrap(intents, slices, candidate, incumbent, list(SLICES), gate="G3", decision_index=3)
    assert result.original_status == "PASS"
    assert result.bootstrap_status == "UNRESOLVED"
    assert result.changed
    assert result.bounds["overall"].lower < -0.03


def test_bootstrap_uses_item_weighted_cluster_ratios() -> None:
    # Two unequal-sized intents: one +1 on one item, the other 0 on three items.
    # Resampling two clusters gives differences 0, 1/4, 1 with probabilities 1/4, 1/2, 1/4.
    result = stats.cluster_bootstrap(
        ["a", "b", "b", "b"],
        ["only"] * 4,
        np.array([True, False, False, False]),
        np.zeros(4, dtype=np.bool_),
        ["only"],
        gate="G1",
        decision_index=1,
        margin=0.8,
        confidence=0.6,
    )
    # Both the 40th and 60th percentiles are 1/4, not the unweighted intent mean 1/2.
    assert result.bounds["overall"].lower == 0.25
    assert result.bounds["overall"].upper == 0.25
    assert result.bounds["overall"].harm_lower == 0


@pytest.mark.parametrize("n10,n01,n", [(-1, 0, 10), (0, -1, 10), (5, 6, 10), (0, 0, 0)])
def test_rejects_invalid_counts(n10: int, n01: int, n: int) -> None:
    with pytest.raises(ValueError, match="paired counts"):
        stats.paired_bounds(n10, n01, n)
