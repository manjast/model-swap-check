"""T-O1, T-M1, T-M3: hand-computed routing, metric and paired-join oracles."""

from __future__ import annotations

from fractions import Fraction
from itertools import product

import pytest

from swapcheck.data import Item
from swapcheck.groups import IntentGroups
from swapcheck.outcomes import build_run, dev_weights, metrics, outcome, pair_runs, weighted_rates
from swapcheck.records import ItemRow, Status

GROUPS = IntentGroups({"cards": ["a"], "cash": ["b"], "empty": ["c"]}, ["oos"])


def row(item_id: str, intent: str = "a", confidence: float = 0.8, status: Status = "ok", match: float = 0.5) -> ItemRow:
    return ItemRow(
        item_id=item_id,
        status=status,
        error_code=None,
        stop_reason=None,
        raw_output=None,
        intent=intent,
        confidence=confidence,
        probabilities=None,
        match_probability=match,
        case_normalized=False,
        latency_ms=None,
        request_id=None,
        model_id=None,
        attempts=[],
    )


@pytest.mark.parametrize(
    ("status", "prediction", "confidence", "truth", "match"),
    list(
        product(
            ("ok", "invalid_output", "api_error"),
            ("a", "out_of_scope"),
            (0.4, 0.5, 0.6),
            ("a", "b", "oos"),
            (0.49, 0.5, 0.8),
        )
    ),
)
def test_t_o1_routing_table(status: Status, prediction: str, confidence: float, truth: str, match: float) -> None:
    recorded = row("i", prediction, confidence, status, match)
    for noul in (False, True):
        expected: str | None
        if status == "api_error":
            expected = None
        elif status != "ok" or prediction == "out_of_scope" or confidence < 0.5 or (noul and match < 0.5):
            expected = "escalated"
        elif truth == "a":
            expected = "correct_auto"
        else:
            expected = "wrong_auto"
        assert outcome(recorded, truth, 0.5, truth_in_scope=truth != "oos", noul=noul) == expected


def test_t_m1_twenty_items_and_exact_weights() -> None:
    # A: 3 right-auto, 2 wrong-auto, 1 right-below, 1 invalid, 1 API error.
    a = [row(str(i)) for i in range(3)] + [row(str(i), "b") for i in range(3, 5)]
    a += [row("5", confidence=0.2), row("6", status="invalid_output"), row("7", status="api_error")]
    # B: 2 right-auto, 1 wrong-auto, 1 OOS prediction, 1 invalid, 1 API error.
    b = [
        row("8", "b"),
        row("9", "b"),
        row("10"),
        row("11", "out_of_scope"),
        row("12", status="invalid_output"),
        row("13", status="api_error"),
    ]
    # OOS: 2 wrong-auto, 2 OOS predictions, 1 invalid, 1 API error.
    oos = [
        row("14"),
        row("15"),
        row("16", "out_of_scope"),
        row("17", "out_of_scope"),
        row("18", status="invalid_output"),
        row("19", status="api_error"),
    ]
    rows = a + b + oos
    items = [Item(r.item_id, "synthetic", "a" if i < 8 else "b" if i < 14 else "oos") for i, r in enumerate(rows)]
    run = build_run(items, rows, split="dev", groups=GROUPS)
    report = metrics(run, 0.5, slice_order=GROUPS.slices)
    all_metrics = report.overall
    assert (
        all_metrics.n,
        all_metrics.wrong,
        all_metrics.automation,
        all_metrics.valid,
        all_metrics.top1,
        all_metrics.oos_recall,
        all_metrics.api_error,
    ) == (20, Fraction(5, 20), Fraction(10, 20), Fraction(14, 17), Fraction(6, 14), Fraction(4, 6), Fraction(3, 20))
    expected = {
        "cards": (8, Fraction(2, 8), Fraction(5, 8), Fraction(6, 7), Fraction(4, 8), None, Fraction(1, 8)),
        "cash": (6, Fraction(1, 6), Fraction(3, 6), Fraction(4, 5), Fraction(2, 6), None, Fraction(1, 6)),
        "out_of_scope": (6, Fraction(2, 6), Fraction(2, 6), Fraction(4, 5), None, Fraction(4, 6), Fraction(1, 6)),
        "empty": (0, None, None, None, None, None, None),
    }
    for name, values in expected.items():
        m = report.by_slice[name]
        assert (m.n, m.wrong, m.automation, m.valid, m.top1, m.oos_recall, m.api_error) == values
    weights = dev_weights(run.truth, {"a": 8, "b": 6, "oos": 6}, {"a": 16, "b": 6, "oos": 18})
    assert weights == (Fraction(1, 20),) * 8 + (Fraction(1, 40),) * 6 + (Fraction(3, 40),) * 6
    rates = weighted_rates(run, 0.5, weights)
    assert (rates.wrong, rates.automation) == (Fraction(11, 40), Fraction(19, 40))


def test_t_m3_pair_and_triple_join_keep_invalid_and_align() -> None:
    items = [Item(str(i), "synthetic", "a") for i in range(5)]
    first = build_run(
        items,
        [row("0"), row("1", status="api_error"), row("2"), row("3", status="invalid_output"), row("4")],
        split="dev",
        groups=GROUPS,
    )
    second = build_run(
        items, [row("4"), row("3"), row("2", status="api_error"), row("1"), row("0")], split="dev", groups=GROUPS
    )
    paired = pair_runs(first, second)
    assert paired.dropped == 2
    assert paired.runs[0].item_ids == paired.runs[1].item_ids == ("0", "3", "4")
    assert paired.runs[0].auto_mask(0).tolist() == [True, False, True]
    third = build_run(items, [row("0", status="api_error"), row("3")], split="dev", groups=GROUPS)
    triple = pair_runs(first, second, third)
    assert triple.dropped == 4
    assert all(run.item_ids == ("3",) for run in triple.runs)


def test_oos_truth_is_wrong_even_if_prediction_matches_truth_literal() -> None:
    assert outcome(row("x", "oos"), "oos", 0, truth_in_scope=False) == "wrong_auto"


def test_pair_rejects_incompatible_truth_and_split() -> None:
    first = build_run([Item("0", "synthetic", "a")], [row("0")], split="dev", groups=GROUPS)
    other = build_run([Item("0", "synthetic", "b")], [row("0")], split="dev", groups=GROUPS)
    with pytest.raises(ValueError, match="truth"):
        pair_runs(first, other)
    cert = build_run([Item("0", "synthetic", "a")], [row("0")], split="cert", groups=GROUPS)
    with pytest.raises(ValueError, match="split"):
        pair_runs(first, cert)
