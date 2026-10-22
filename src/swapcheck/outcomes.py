"""Routing, exact dev weights, metrics and paired item joins (spec §3.3, §5, §7.4).

API errors have no routing outcome. Standalone run rates use all recorded items
as n (§5); paired analyses first remove API errors in any arm (§7.4).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from swapcheck.data import Item
from swapcheck.groups import OUT_OF_SCOPE, IntentGroups
from swapcheck.records import ItemRow, Split, Status

Outcome = Literal["correct_auto", "wrong_auto", "escalated"]


def routed_intent(row: ItemRow, tau: float, *, noul: bool = False) -> str | None:
    """Return the auto-routed intent, or None for escalation/API error."""
    if row.status != "ok" or row.intent == OUT_OF_SCOPE:
        return None
    if row.intent is None or row.confidence is None:
        raise ValueError("ok prediction requires intent and confidence")
    if noul:
        if row.match_probability is None:
            raise ValueError("jev-noul ok prediction requires match_probability")
        if row.match_probability < 0.5:
            return None
    return row.intent if row.confidence >= tau else None


def outcome(row: ItemRow, truth: str, tau: float, *, truth_in_scope: bool, noul: bool = False) -> Outcome | None:
    """API errors have no outcome; every auto-routed OOS truth is wrong."""
    if row.status == "api_error":
        return None
    prediction = routed_intent(row, tau, noul=noul)
    if prediction is None:
        return "escalated"
    return "correct_auto" if truth_in_scope and prediction == truth else "wrong_auto"


@dataclass(frozen=True)
class AnalysisRun:
    """Text-free, aligned arrays for repeated threshold evaluation.

    Construct with build_run so eligibility includes the Jev match rule. The split
    is explicit provenance and is checked by every calibration entry point.
    """

    split: Split
    item_ids: tuple[str, ...]
    truth: tuple[str, ...]
    slices: tuple[str, ...]
    status: tuple[Status, ...]
    intent: tuple[str | None, ...]
    confidence: NDArray[np.float64]
    eligible: NDArray[np.bool_]
    correct: NDArray[np.bool_]
    complete: bool = True

    def __len__(self) -> int:
        return len(self.item_ids)

    def auto_mask(self, tau: float) -> NDArray[np.bool_]:
        return self.eligible & (self.confidence >= tau)

    def take(self, indices: Sequence[int]) -> AnalysisRun:
        index = np.asarray(indices, dtype=np.intp)
        return AnalysisRun(
            self.split,
            tuple(self.item_ids[i] for i in indices),
            tuple(self.truth[i] for i in indices),
            tuple(self.slices[i] for i in indices),
            tuple(self.status[i] for i in indices),
            tuple(self.intent[i] for i in indices),
            self.confidence[index],
            self.eligible[index],
            self.correct[index],
            self.complete,
        )


def build_run(
    items: Sequence[Item],
    rows: Sequence[ItemRow],
    *,
    split: Split,
    groups: IntentGroups,
    noul: bool = False,
    complete: bool = True,
) -> AnalysisRun:
    """Join recorded rows to known truth, retaining row order and no message text.

    Missing rows are allowed for incomplete runs; unknown/duplicate IDs are not.
    Passing split='dev' asserts the caller obtained items from that split, rather
    than deriving provenance from an item ID (train IDs also occur in cert).
    """
    by_id = {item.item_id: item for item in items}
    if len(by_id) != len(items) or len({row.item_id for row in rows}) != len(rows):
        raise ValueError("duplicate item ID")
    selected = [by_id[row.item_id] for row in rows]
    slices = tuple(groups.slice_of(item.intent) for item in selected)
    eligible = np.array([routed_intent(row, 0, noul=noul) is not None for row in rows], dtype=np.bool_)
    return AnalysisRun(
        split,
        tuple(row.item_id for row in rows),
        tuple(item.intent for item in selected),
        slices,
        tuple(row.status for row in rows),
        tuple(row.intent for row in rows),
        np.array([row.confidence if row.confidence is not None else np.nan for row in rows]),
        eligible,
        np.array(
            [
                row.status == "ok" and row.intent == item.intent and s != OUT_OF_SCOPE
                for row, item, s in zip(rows, selected, slices, strict=True)
            ],
            dtype=np.bool_,
        ),
        complete,
    )


def dev_weights(
    truths: Sequence[str], dev_counts: Mapping[str, int], cert_counts: Mapping[str, int]
) -> tuple[Fraction, ...]:
    """Exact §5 item weights, renormalized over the supplied item set."""
    raw = tuple(Fraction(cert_counts[intent], dev_counts[intent]) for intent in truths)
    total = sum(raw, Fraction())
    if not raw or total <= 0:
        raise ValueError("weights require positive cert mass")
    return tuple(weight / total for weight in raw)


def normalize_weights(weights: Sequence[Fraction]) -> tuple[Fraction, ...]:
    total = sum(weights, Fraction())
    if not weights or any(w < 0 for w in weights) or total <= 0:
        raise ValueError("weights require nonnegative values and positive total")
    return tuple(w / total for w in weights)


@dataclass(frozen=True)
class WeightedRates:
    wrong: Fraction
    automation: Fraction


def weighted_rates(run: AnalysisRun, tau: float, weights: Sequence[Fraction]) -> WeightedRates:
    if len(weights) != len(run):
        raise ValueError("one weight required per item")
    normalized = normalize_weights(weights)
    auto = run.auto_mask(tau)
    return WeightedRates(
        sum((w for w, a, c in zip(normalized, auto, run.correct, strict=True) if a and not c), Fraction()),
        sum((w for w, a in zip(normalized, auto, strict=True) if a), Fraction()),
    )


@dataclass(frozen=True)
class Metrics:
    n: int
    wrong: Fraction | None
    automation: Fraction | None
    valid: Fraction | None
    top1: Fraction | None
    oos_recall: Fraction | None
    api_error: Fraction | None


@dataclass(frozen=True)
class MetricsReport:
    overall: Metrics
    by_slice: dict[str, Metrics]


def _rate(numerator: int, denominator: int) -> Fraction | None:
    return Fraction(numerator, denominator) if denominator else None


def _metrics(run: AnalysisRun, tau: float) -> Metrics:
    auto = run.auto_mask(tau)
    wrong = auto & ~run.correct
    counts = Counter(run.status)
    in_scope = np.array([s != OUT_OF_SCOPE for s in run.slices], dtype=np.bool_)
    oos = ~in_scope
    return Metrics(
        len(run),
        _rate(int(np.count_nonzero(wrong)), len(run)),
        _rate(int(np.count_nonzero(auto)), len(run)),
        _rate(counts["ok"], counts["ok"] + counts["invalid_output"]),
        _rate(int(np.count_nonzero(run.correct)), int(np.count_nonzero(in_scope))),
        _rate(int(np.count_nonzero(oos & ~wrong)), int(np.count_nonzero(oos))),
        _rate(counts["api_error"], len(run)),
    )


def metrics(run: AnalysisRun, tau: float, *, slice_order: Sequence[str] | None = None) -> MetricsReport:
    """Undefined ratios are None; optionally include empty slices in file order."""
    names = tuple(dict.fromkeys(run.slices)) if slice_order is None else tuple(slice_order)
    return MetricsReport(
        _metrics(run, tau),
        {name: _metrics(run.take([i for i, s in enumerate(run.slices) if s == name]), tau) for name in names},
    )


@dataclass(frozen=True)
class PairedRuns:
    runs: tuple[AnalysisRun, ...]
    dropped: int


def pair_runs(*runs: AnalysisRun) -> PairedRuns:
    """Align two or three arms in first-arm order; count union minus usable IDs.

    An absent item is dropped just like an API error. Truth, slice and split must
    agree, so accidental joins of different evaluations cannot silently proceed.
    """
    if len(runs) not in (2, 3):
        raise ValueError("pairing requires two or three runs")
    if len({run.split for run in runs}) != 1:
        raise ValueError("paired runs must have the same split")
    indices = [{item_id: i for i, item_id in enumerate(run.item_ids)} for run in runs]
    union = set().union(*(set(index) for index in indices))
    retained: list[str] = []
    for item_id in runs[0].item_ids:
        if any(item_id not in index for index in indices):
            continue
        positions = [index[item_id] for index in indices]
        if len({(run.truth[i], run.slices[i]) for run, i in zip(runs, positions, strict=True)}) != 1:
            raise ValueError("paired item truth/slice mismatch")
        if all(run.status[i] != "api_error" for run, i in zip(runs, positions, strict=True)):
            retained.append(item_id)
    return PairedRuns(
        tuple(run.take([index[item_id] for item_id in retained]) for run, index in zip(runs, indices, strict=True)),
        len(union) - len(retained),
    )
