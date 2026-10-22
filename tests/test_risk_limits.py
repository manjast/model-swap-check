"""Amendment 3, risk-limit sensitivity (T-V6, spec §7.10)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from test_jev_policy import V2, _fixture

from swapcheck.contract import Calibration, Contract, RiskLimits
from swapcheck.decide import DecisionRefusal
from swapcheck.groups import OUT_OF_SCOPE
from swapcheck.records import ItemRow, read_rows
from swapcheck.risk_limits import write_risk_limits

LIMITS = [0.01, 0.05]
TAUS = {"inc": (0.95, 0.0), "luna-none": (0.97, 0.6), "jev-noul": (0.9, 0.0)}


def _v3(base: Contract) -> Contract:
    run_contracts = {"inc": base.tag, "luna-none": base.tag, "jev-noul": V2}
    return Contract(
        tag="synthetic-golden-v3",
        configurations={cid: base.configurations[cid] for cid in run_contracts},
        item_lists={"cert": base.item_lists["cert"]},
        risk_limits=RiskLimits(
            limits=LIMITS,
            run_contracts=run_contracts,
            thresholds={cid: [Calibration(tau=t, dev_w=0.0, dev_a=0.5) for t in TAUS[cid]] for cid in run_contracts},
            incumbent_fixed=[Calibration(tau=0.0, dev_w=0.2, dev_a=0.9)],
            code_version="synthetic",
            records={},
        ),
    )


def _auto(row: ItemRow, tau: float, gated: bool) -> bool:
    """§3.3 by hand; with `gated`, the J2 signal of §7.9 (the Noul probability only at Choice confidence 1.00)."""
    if row.status != "ok" or row.intent == OUT_OF_SCOPE or row.confidence is None:
        return False
    if gated:
        assert row.match_probability is not None
        return row.match_probability >= 0.5 and (row.match_probability if row.confidence >= 1.0 else 0.0) >= tau
    return row.confidence >= tau


def _summary(text: str, cid: str) -> list[str]:
    match = re.search(rf"^\| `{re.escape(cid)}` \| ([^\n]*) \|$", text.split("## Summary")[1], re.MULTILINE)
    assert match is not None
    return match.group(1).split(" | ")


def test_v6_report_hand_counts_pairing_and_j2_signal(tmp_path: Path) -> None:
    runs, base, v2, items, groups, noul_rows, _ = _fixture(tmp_path / "fixture")
    text = write_risk_limits(runs, base, v2, _v3(base), items, groups, tmp_path / "out")
    assert (tmp_path / "out" / "A3-limits.md").read_text(encoding="utf-8") == text
    truth = {it.item_id: it.intent for it in items}
    oos = {it.item_id for it in items if groups.slice_of(it.intent) == OUT_OF_SCOPE}
    inc_rows = {r.item_id: r for r in read_rows(runs / "golden-inc-cert")}
    arms = {
        "luna-none": ({r.item_id: r for r in read_rows(runs / "golden-luna-none-cert")}, False),
        "jev-noul": ({r.item_id: r for r in noul_rows}, True),
    }
    for cid, (rows, gated) in arms.items():
        kept = [i for i in rows if rows[i].status != "api_error" and inc_rows[i].status != "api_error"]
        assert len(kept) == len(items) - (1 if cid == "luna-none" else 0)
        cells = []
        for k, tau in enumerate(TAUS[cid]):
            auto = [i for i in kept if _auto(rows[i], tau, gated)]
            wrong = [i for i in auto if i in oos or rows[i].intent != truth[i]]
            cells.append(f"{len(wrong) / len(kept) * 100:.2f}% / {len(auto) / len(kept) * 100:.2f}%")
            inc_auto = sum(_auto(inc_rows[i], TAUS["inc"][k], False) for i in kept)
            diff = (len(auto) - inc_auto) / len(kept) * 100
            section = text.split(f"## Limit {LIMITS[k] * 100:g}%")[1].split("##")[0]
            assert re.search(rf"^\| `{cid}` \|.* \| {diff:.2f} pp \[", section, re.MULTILINE), (cid, k)
        assert _summary(text, cid) == cells
    # Without the J2 gate more jev-noul answers would route at 0.9, so the hand counts above detect a missing gate.
    assert sum(_auto(r, 0.9, True) for r in noul_rows) < sum(_auto(r, 0.9, False) for r in noul_rows)


def test_v6_report_refuses_foreign_tag_changed_hash_and_missing_thresholds(tmp_path: Path) -> None:
    runs, base, v2, items, groups, _, _ = _fixture(tmp_path / "fixture")
    v3 = _v3(base)
    rl = v3.risk_limits
    assert rl is not None

    def refused(contract: Contract, message: str) -> None:
        with pytest.raises(DecisionRefusal, match=message):
            write_risk_limits(runs, base, v2, contract, items, groups, tmp_path / "out")
        assert not (tmp_path / "out").exists()

    changed = v3.configurations | {"jev-noul": base.configurations["jev-c51"]}
    refused(v3.model_copy(update={"configurations": changed}), "jev-noul: configuration hashes differ")
    foreign = rl.model_copy(update={"run_contracts": rl.run_contracts | {"luna-none": "contract-v9"}})
    refused(v3.model_copy(update={"risk_limits": foreign}), "luna-none: its run contract contract-v9 is neither")
    short = rl.model_copy(update={"thresholds": rl.thresholds | {"inc": rl.thresholds["inc"][:1]}})
    refused(v3.model_copy(update={"risk_limits": short}), "inc: thresholds do not match the 2 limits")
