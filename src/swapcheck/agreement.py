"""Shared misroutes in the `cert` runs: descriptive and post hoc, no verdict (docs/cert.md). Text-free.

A shared misroute is an item that every configuration auto-routes, at threshold 0, to the same queue, which is not
the labelled one (an out-of-scope label has no queue). Those are the messages where the label, not one model,
stands alone. For each configuration at each threshold, the report compares the share of shared misroutes it
auto-routes with the share of its own correct answers it auto-routes: a gate that separates the two passes fewer
of the first.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from swapcheck.groups import OUT_OF_SCOPE
from swapcheck.outcomes import AnalysisRun


@dataclass(frozen=True)
class GateShares:
    tau: float
    shared: float  # share of shared misroutes auto-routed at tau
    correct: float  # share of the configuration's own correct answers auto-routed at tau


@dataclass(frozen=True)
class SharedMisroutes:
    n: int  # items with an answer from every configuration
    dropped: int  # items absent from a run or with an API error in any
    shared: int
    shared_out_of_scope: int  # of which the label is out of scope
    reference_wrong: int  # the reference configuration's wrong auto-routes at its top threshold
    same_answer: dict[str, int]  # per other configuration: the same queue on those items
    gates: dict[str, list[GateShares]]


def _align(runs: Mapping[str, AnalysisRun]) -> tuple[dict[str, AnalysisRun], int]:
    """Every run restricted to the items all of them answered, in the first run's order, and the dropped count."""
    indices = {cid: {item_id: i for i, item_id in enumerate(run.item_ids)} for cid, run in runs.items()}
    first = next(iter(runs.values()))
    union = set().union(*(set(index) for index in indices.values()))

    def answered(item_id: str) -> bool:
        return all(item_id in indices[c] and run.status[indices[c][item_id]] != "api_error" for c, run in runs.items())

    kept = [item_id for item_id in first.item_ids if answered(item_id)]
    aligned = {cid: run.take([indices[cid][item_id] for item_id in kept]) for cid, run in runs.items()}
    if len({run.truth for run in aligned.values()}) != 1:
        raise ValueError("aligned runs disagree on truth")
    return aligned, len(union) - len(kept)


def _share(auto: NDArray[np.bool_], of: NDArray[np.bool_]) -> float:
    """The share of the `of` items that `auto` routes (0 when there are none)."""
    return float(auto[of].mean()) if of.any() else 0.0


def shared_misroutes(
    runs: Mapping[str, AnalysisRun], taus: Mapping[str, Sequence[float]], reference: str, top: float
) -> SharedMisroutes:
    aligned, dropped = _align(runs)
    arms = list(aligned.values())
    first = arms[0]
    agree = np.array([len({run.intent[i] for run in arms}) == 1 for i in range(len(first))], dtype=np.bool_)
    shared = agree & np.logical_and.reduce([run.eligible for run in arms]) & ~first.correct
    ref = aligned[reference]
    ref_wrong = ref.auto_mask(top) & ~ref.correct
    same = {
        cid: sum(run.intent[i] == ref.intent[i] for i in np.flatnonzero(ref_wrong))
        for cid, run in aligned.items()
        if cid != reference
    }
    gates = {
        cid: [
            GateShares(tau, _share(run.auto_mask(tau), shared), _share(run.auto_mask(tau), run.correct))
            for tau in taus[cid]
        ]
        for cid, run in aligned.items()
    }
    return SharedMisroutes(
        n=len(first),
        dropped=dropped,
        shared=int(np.count_nonzero(shared)),
        shared_out_of_scope=sum(first.slices[i] == OUT_OF_SCOPE for i in np.flatnonzero(shared)),
        reference_wrong=int(np.count_nonzero(ref_wrong)),
        same_answer=same,
        gates=gates,
    )
