"""T-V7: shared misroutes (docs/cert.md), on hand-built runs with hand-counted expectations."""

from __future__ import annotations

import numpy as np
import pytest

from swapcheck.agreement import shared_misroutes
from swapcheck.groups import OUT_OF_SCOPE
from swapcheck.outcomes import AnalysisRun
from swapcheck.records import Status

IDS = ("i0", "i1", "i2", "i3", "i4", "i5")
TRUTH = ("a", "a", "z", "a", "a", "a")
SLICES = ("s", "s", OUT_OF_SCOPE, "s", "s", "s")


def arm(intents: list[str], confidence: list[float], status: list[Status] | None = None) -> AnalysisRun:
    status = status or ["ok"] * len(IDS)
    return AnalysisRun(
        "cert",
        IDS,
        TRUTH,
        SLICES,
        tuple(status),
        tuple(intents),
        np.array(confidence),
        np.array([s == "ok" and i != OUT_OF_SCOPE for s, i in zip(status, intents, strict=True)]),
        np.array(
            [
                s == "ok" and i == t and sl != OUT_OF_SCOPE
                for s, i, t, sl in zip(status, intents, TRUTH, SLICES, strict=True)
            ]
        ),
    )


# i0 every arm right; i1 every arm the same wrong queue; i2 the same queue for an out-of-scope label; i3 the arms
# disagree; i4 every arm says out of scope (escalated, not a misroute); i5 an API error in X (dropped).
OOS = OUT_OF_SCOPE
REF = arm(["a", "b", "b", "b", OOS, "a"], [1.0, 1.0, 0.9, 1.0, 1.0, 1.0])
X = arm(["a", "b", "b", "c", OOS, "a"], [0.99, 0.5, 0.99, 0.99, 0.9, 0.9], ["ok", "ok", "ok", "ok", "ok", "api_error"])
Y = arm(["a", "b", "b", "b", OOS, "a"], [0.9, 0.95, 0.4, 0.9, 0.9, 0.9])


def test_shared_misroutes_hand_counts() -> None:
    r = shared_misroutes({"ref": REF, "x": X, "y": Y}, {"ref": [1.0], "x": [0.9], "y": [0.95, 0.0]}, "ref", 1.0)
    assert (r.n, r.dropped) == (5, 1)
    assert (r.shared, r.shared_out_of_scope) == (2, 1)  # i1 and i2
    assert r.reference_wrong == 2  # i1 and i3 at 1.00; i2 sits below it, i4 is escalated
    assert r.same_answer == {"x": 1, "y": 2}  # X answers c on i3
    shares = {cid: [(g.shared, g.correct) for g in gates] for cid, gates in r.gates.items()}
    assert shares == {"ref": [(0.5, 1.0)], "x": [(0.5, 1.0)], "y": [(0.5, 0.0), (1.0, 1.0)]}


def test_shared_misroutes_refuses_runs_that_disagree_on_truth() -> None:
    other = AnalysisRun("cert", IDS, ("b",) * 6, SLICES, Y.status, Y.intent, Y.confidence, Y.eligible, Y.correct)
    with pytest.raises(ValueError, match="truth"):
        shared_misroutes({"ref": REF, "other": other}, {"ref": [1.0], "other": [1.0]}, "ref", 1.0)
