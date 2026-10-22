"""Amendment 2, Jev at its top confidence (T-V5, spec §7.9)."""

from __future__ import annotations

import gzip
import re
import shutil
from collections import Counter
from fractions import Fraction
from pathlib import Path

import pytest
from test_golden import _items, build_golden, load_golden

from swapcheck.contract import Calibration, Contract, ContractConfiguration, JevPolicy
from swapcheck.data import Item
from swapcheck.decide import DecisionRefusal
from swapcheck.groups import OUT_OF_SCOPE, IntentGroups, load_groups
from swapcheck.jev_policy import fit_j2, write_jev_policy
from swapcheck.manifest import ManifestRun, load_manifest, save_manifest
from swapcheck.records import ItemRow, RunMeta, read_rows

V2 = "synthetic-golden-v2"


def _jev_row(item_id: str, intent: str, confidence: float, match: float | None) -> ItemRow:
    return ItemRow(
        item_id=item_id,
        status="ok",
        error_code=None,
        stop_reason="stop",
        raw_output="{}",
        intent=intent,
        confidence=confidence,
        probabilities={intent: confidence},
        match_probability=match,
        case_normalized=False,
        latency_ms=1.0,
        request_id=item_id,
        model_id="jev-1.13.0",
        attempts=[],
    )


def test_v5_tau_j2_ignores_the_noul_probability_below_top_confidence() -> None:
    groups = load_groups()
    dev = _items(groups, "dev", 10)  # 70 items, 10 per slice: equal weights, so 2% of 70 allows one wrong route
    oos = {it.item_id for it in dev if groups.slice_of(it.intent) == OUT_OF_SCOPE}
    in_scope = [it for it in dev if it.item_id not in oos]
    wrong_matches = {in_scope[0].item_id: 0.97, in_scope[1].item_id: 0.95, in_scope[2].item_id: 0.93}
    rows = []
    for i, it in enumerate(dev):
        if it.item_id in oos:
            rows.append(_jev_row(it.item_id, OUT_OF_SCOPE, 1.0, 0.2))
        elif it.item_id in wrong_matches:
            rows.append(_jev_row(it.item_id, "card_arrival", 1.0, wrong_matches[it.item_id]))
        elif it.item_id == in_scope[3].item_id:
            # Wrong at Choice confidence 0.98 with a high Noul probability: J2 must not route it, so it cannot
            # push tau_J2 up to 0.99.
            rows.append(_jev_row(it.item_id, "card_arrival", 0.98, 0.99))
        else:
            rows.append(_jev_row(it.item_id, it.intent, 1.0, 0.99 if i % 2 else 0.90))
    assert all(it.intent != "card_arrival" for it in in_scope[:4])
    counts = Counter(it.intent for it in dev)
    fitted = fit_j2(dev, rows, groups, counts, counts)
    # At 0.95 two wrong routes (2.86%) exceed 2%; at 0.97 one (1.43%) does not.
    assert fitted.tau == 0.97
    assert fitted.wrong == Fraction(1, 70)
    correct_at_099 = sum(1 for i, it in enumerate(dev) if it in in_scope[4:] and i % 2)
    assert fitted.automation == Fraction(correct_at_099 + 1, 70)


def _clone_run(
    runs: Path, source: str, run_id: str, config_id: str, hashes: ContractConfiguration, rows: list[ItemRow]
) -> RunMeta:
    meta = RunMeta.model_validate_json((runs / source / "run.json").read_text(encoding="utf-8"))
    meta = meta.model_copy(update={"run_id": run_id, "config_id": config_id, **hashes.model_dump()})
    (runs / run_id).mkdir()
    (runs / run_id / "run.json").write_text(meta.model_dump_json(), encoding="utf-8")
    payload = "".join(row.model_dump_json() + "\n" for row in rows).encode()
    (runs / run_id / "items.jsonl.gz").write_bytes(gzip.compress(payload, mtime=0))
    return meta


def _fixture(root: Path) -> tuple[Path, Contract, Contract, list[Item], IntentGroups, list[ItemRow], list[ItemRow]]:
    """Golden runs plus a `jev-c51` cert run under the base contract and the `jev-noul` cert run moved to v2."""
    build_golden(root)
    runs, base, items, groups = load_golden(root)
    assert base.analysis is not None
    truth = {it.item_id: it.intent for it in items}
    noul_rows = []
    for i, row in enumerate(read_rows(runs / "golden-jev-noul-cert")):
        wrong = i % 10 == 0 and row.intent != OUT_OF_SCOPE
        noul_rows.append(
            row.model_copy(
                update={
                    "intent": "card_arrival" if wrong and truth[row.item_id] != "card_arrival" else row.intent,
                    "confidence": 1.0 if i % 2 == 0 else 0.98,
                    "match_probability": 0.95 if i % 3 == 0 else 0.80,
                }
            )
        )
    c51_rows = [
        row.model_copy(update={"confidence": 1.0 if i % 4 == 0 else 0.99, "match_probability": None})
        for i, row in enumerate(read_rows(runs / "golden-jev-noul-cert"))
    ]
    manifest = load_manifest(runs)
    noul_entry = next(e for e in manifest.runs if e.config_id == "jev-noul")
    manifest.runs.remove(noul_entry)
    noul_meta = _clone_run(
        runs, noul_entry.run_id, "golden-jev-noul-v2", "jev-noul", base.configurations["jev-noul"], noul_rows
    )
    c51_meta = _clone_run(
        runs, noul_entry.run_id, "golden-jev-c51-cert", "jev-c51", base.configurations["jev-c51"], c51_rows
    )
    for tag, meta in ((V2, noul_meta), (base.tag, c51_meta)):
        manifest.runs.append(
            ManifestRun(
                contract_tag=tag,
                contract_tag_commit=meta.contract_tag_commit or "",
                run_id=meta.run_id,
                config_id=meta.config_id,
                split="cert",
                item_list_sha256=meta.item_list_sha256,
                config_sha256=meta.config_sha256,
                prompt_sha256=meta.prompt_sha256,
                schema_sha256=meta.schema_sha256,
            )
        )
    save_manifest(runs, manifest)
    shutil.rmtree(runs / noul_entry.run_id)
    v2 = Contract(
        tag=V2,
        configurations={cid: base.configurations[cid] for cid in ("inc", "jev-c51", "jev-noul")},
        item_lists={"cert": base.item_lists["cert"]},
        jev_policy=JevPolicy(
            base_tag=base.tag,
            incumbent_tau=base.analysis.incumbent_tau,
            j1=Calibration(tau=1.0, dev_w=0.0229, dev_a=0.4238),
            j2=Calibration(tau=0.9, dev_w=0.0188, dev_a=0.4059),
            code_version="synthetic",
            records={},
        ),
    )
    return runs, base, v2, items, groups, noul_rows, c51_rows


def _overall(text: str, section: str) -> tuple[str, str]:
    part = text.split(f"## {section}")[1]
    match = re.search(r"\| candidate \| overall \| \d+ \| ([\d.]+) pp \[[^]]*\] \| ([\d.]+) pp \[", part)
    assert match is not None
    return match.group(1), match.group(2)


def test_v5_report_hand_counts_for_j1_and_j2(tmp_path: Path) -> None:
    runs, base, v2, items, groups, noul_rows, c51_rows = _fixture(tmp_path / "fixture")
    text = write_jev_policy(runs, base, v2, items, groups, tmp_path / "out")
    assert (tmp_path / "out" / "A2-jev.md").read_text(encoding="utf-8") == text
    truth = {it.item_id: it.intent for it in items}
    oos = {it.item_id for it in items if groups.slice_of(it.intent) == OUT_OF_SCOPE}
    n = len(items)

    def rates(auto: list[ItemRow]) -> tuple[str, str]:
        wrong = sum(1 for r in auto if r.item_id in oos or r.intent != truth[r.item_id])
        return f"{wrong / n * 100:.2f}", f"{len(auto) / n * 100:.2f}"

    j1 = [r for r in c51_rows if r.intent != OUT_OF_SCOPE and r.confidence == 1.0]
    j2 = [
        r for r in noul_rows if r.intent != OUT_OF_SCOPE and r.confidence == 1.0 and (r.match_probability or 0) >= 0.9
    ]
    assert 0 < len(j2) < len([r for r in noul_rows if r.intent != OUT_OF_SCOPE and (r.match_probability or 0) >= 0.9])
    assert _overall(text, "J1") == rates(j1)
    assert _overall(text, "J2") == rates(j2)
    assert "D-J stays as registered" in text


def test_v5_report_refuses_missing_run_and_changed_base_configuration(tmp_path: Path) -> None:
    runs, base, v2, items, groups, _, _ = _fixture(tmp_path / "fixture")
    changed = v2.configurations | {"jev-c51": base.configurations["jev-noul"]}
    with pytest.raises(DecisionRefusal, match="jev-c51: configuration hashes differ"):
        write_jev_policy(runs, base, v2.model_copy(update={"configurations": changed}), items, groups, tmp_path / "a")
    manifest = load_manifest(runs)
    manifest.runs = [e for e in manifest.runs if e.contract_tag != V2]
    save_manifest(runs, manifest)
    with pytest.raises(DecisionRefusal, match="jev-noul: required cert run under synthetic-golden-v2 missing"):
        write_jev_policy(runs, base, v2, items, groups, tmp_path / "b")
    assert not (tmp_path / "b").exists()
