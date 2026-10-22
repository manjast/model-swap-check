"""Offline byte-for-byte certification replay using committed synthetic Banking77 rows.

``build_golden(root)`` builds inputs only; expected records must be regenerated
explicitly with ``write_decisions(*load_golden(root), output_dir)`` after review.
No provider, dataset download, git tag or wall clock is involved.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

import yaml

from swapcheck.configs import load_configurations
from swapcheck.contract import Contract, load_contract
from swapcheck.data import Item, item_list_hash
from swapcheck.decide import DECISIONS, write_decisions
from swapcheck.groups import OUT_OF_SCOPE, IntentGroups, load_groups
from swapcheck.manifest import (
    Manifest,
    ManifestRun,
    NotRun,
    NotRunReason,
    load_manifest,
    save_manifest,
    verify_manifest,
)
from swapcheck.records import Attempt, ItemRow, RunMeta, RunTotals, Split, Status, Usage, read_rows

GOLDEN = Path(__file__).parent / "fixtures" / "golden"
COMMIT = "0123456789abcdef0123456789abcdef01234567"
NOT_RUN: dict[str, NotRunReason] = {"D-A2": "no dev gain", "D-B2": "budget", "D-X": "budget"}
CERT_CONFIGS = ("inc", "luna-none", "haiku55-off", "jev-noul", "luna-dec")


def load_golden(root: Path | None = None) -> tuple[Path, Contract, list[Item], IntentGroups]:
    """Load injectable decision arguments; pass a copied root for mutation tests."""
    root = GOLDEN if root is None else root
    items = [Item(**json.loads(line)) for line in (root / "cert.jsonl").read_text(encoding="utf-8").splitlines()]
    return root / "runs", load_contract(root / "contract.yaml"), items, load_groups(root / "groups.yaml")


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _items(groups: IntentGroups, split: str, per_slice: int) -> list[Item]:
    intents = [values[0] for values in groups.in_scope_groups.values()] + [groups.out_of_scope[0]]
    return [
        Item(f"synthetic-{split}-{s:02d}-{i:03d}", f"Please help with my banking request number {i}.", intent)
        for s, intent in enumerate(intents)
        for i in range(per_slice)
    ]


def _row(item: Item, i: int, config: str, groups: IntentGroups, model: str) -> ItemRow:
    prediction = OUT_OF_SCOPE if groups.slice_of(item.intent) == OUT_OF_SCOPE else item.intent
    confidence = 0.96
    # Distinct, stable arm behavior exercises discordance, escalation and invalid output.
    if config == "inc" and i % 19 == 0:
        confidence = 0.60
    if config == "luna-none" and i % 37 == 0:
        prediction = "activate_my_card" if item.intent != "activate_my_card" else "declined_transfer"
    if config == "haiku55-off" and i % 5 == 0:
        confidence = 0.55
    if config == "jev-noul" and i % 23 == 0:
        confidence = 0.65
    if config == "luna-dec" and i % 11 == 0:
        prediction = "activate_my_card"
    status: Status = "api_error" if config == "luna-none" and i == 13 else "ok"
    if config == "luna-dec" and i == 17:
        status = "invalid_output"
    valid = status == "ok"
    usage = Usage(uncached_input=150, cache_read=900 if i % 2 else 0, output=12, reasoning=None)
    latency = float(80 + i % 17 * 5 + (40 if config == "haiku55-off" else 0))
    interface = config in ("jev-noul", "luna-dec")
    probabilities = {prediction: confidence} if interface and valid else None
    return ItemRow(
        item_id=item.item_id,
        status=status,
        error_code=None if valid else ("http_500" if status == "api_error" else "invalid_json"),
        stop_reason="stop" if valid else None,
        raw_output=json.dumps({"intent": prediction, "confidence": confidence}) if valid else None,
        intent=prediction if valid else None,
        confidence=confidence if valid else None,
        probabilities=probabilities,
        match_probability=0.9 if config == "jev-noul" and valid else None,
        case_normalized=False,
        latency_ms=latency,
        request_id=f"fixture-{config}-{i:03d}",
        model_id=model,
        attempts=[
            Attempt(
                number=1,
                http_status=200 if status != "api_error" else 500,
                error="http_500" if status == "api_error" else None,
                usage=usage,
                latency_ms=latency,
                request_id=f"fixture-{config}-{i:03d}",
            )
        ],
    )


def build_golden(root: Path) -> None:
    """Build small, deterministic, manifest-verified inputs (never expected outputs)."""
    root.mkdir(parents=True, exist_ok=True)
    groups = load_groups()
    (root / "groups.yaml").write_text(
        yaml.safe_dump(
            {"in_scope_groups": groups.in_scope_groups, "out_of_scope": groups.out_of_scope}, sort_keys=False
        ),
        encoding="utf-8",
    )
    cert, dev = _items(groups, "cert", 30), _items(groups, "dev", 10)
    splits: dict[Split, list[Item]] = {"cert": cert, "dev": dev, "aa": cert}
    for split, items in splits.items():
        (root / f"{split}.jsonl").write_text(
            "".join(
                json.dumps({"item_id": it.item_id, "text": it.text, "intent": it.intent}, sort_keys=True) + "\n"
                for it in items
            ),
            encoding="utf-8",
        )
    configs = {key: cfg for key, cfg in load_configurations().items() if not cfg.pilot_only}
    hashes = {
        key: {
            "config_sha256": cfg.sha256(),
            "prompt_sha256": _digest(f"synthetic-prompt-{key}"),
            "schema_sha256": _digest(f"synthetic-schema-{key}"),
        }
        for key, cfg in configs.items()
    }
    contract = Contract.model_validate(
        {
            "tag": "synthetic-golden-v1",
            "configurations": hashes,
            "item_lists": {split: item_list_hash(items) for split, items in splits.items()},
            "analysis": {
                "incumbent_tau": 0.7,
                "configurations": {key: {"tau": 0.7, "dev_w": 0.0, "dev_a": 0.8} for key in configs},
                "dev_counts": dict(Counter(it.intent for it in dev)),
                "cert_counts": dict(Counter(it.intent for it in cert)),
                "delta_w": 0.01,
                "delta_s": 0.03,
                "power": dict.fromkeys(DECISIONS, 0.65),
                "slices": groups.slices,
                "dev_discordance": {decision: dict.fromkeys(groups.slices, 0.01) for decision in DECISIONS},
                "seeds": {"bootstrap": 20261021, "power": 20261021},
                "code_version": "synthetic-golden-v1",
                "budget": {
                    "planned_cert_runs": [*CERT_CONFIGS, "aa"],
                    "drop_order": ["D-X", "D-B2"],
                    "not_run": NOT_RUN,
                },
                "selections": {
                    "reasoning": {"luna": None, "haiku55": "haiku55-low"},
                    "jev_design": "jev-noul",
                    "dx_iteration": 0,
                    "dx_prompt_sha256": hashes["luna-none-x"]["prompt_sha256"],
                    "records": {
                        "fixture": "Synthetic data only; no real model claims.",
                        "discordance": "Assumed 1% planning floor per slice, not estimated from dev.",
                    },
                },
                # jev-noul sits exactly on the 5% boundary (no limitation); luna-dec is above it.
                "order_sensitivity": {
                    "jev-c51": {"changed": 6, "items": 100},
                    "jev-noul": {"changed": 5, "items": 100},
                    "luna-dec": {"changed": 14, "items": 100},
                },
            },
        }
    )
    (root / "contract.yaml").write_text(
        yaml.safe_dump(contract.model_dump(mode="json"), sort_keys=False), encoding="utf-8"
    )
    manifest = Manifest(
        not_run=[NotRun(contract_tag=contract.tag, decision_id=key, reason=reason) for key, reason in NOT_RUN.items()]
    )
    run_specs: list[tuple[str, Split]] = [*((cfg, "cert") for cfg in CERT_CONFIGS), ("inc", "aa")]
    for config, split in run_specs:
        run_id = f"golden-{config}-{split}"
        run_dir = root / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        rows = [_row(it, i, config, groups, configs[config].model) for i, it in enumerate(cert)]
        payload = "".join(row.model_dump_json() + "\n" for row in rows).encode()
        (run_dir / "items.jsonl.gz").write_bytes(gzip.compress(payload, mtime=0))
        usage = Usage(
            **{
                key: sum(getattr(row.attempts[0].usage, key) for row in rows)
                for key in ("uncached_input", "cache_read", "cache_write", "output")
            }
        )
        meta = RunMeta(
            run_id=run_id,
            config_id=config,
            config_sha256=hashes[config]["config_sha256"],
            prompt_sha256=hashes[config]["prompt_sha256"],
            schema_sha256=hashes[config]["schema_sha256"],
            split=split,
            item_list_sha256=contract.item_lists["cert"],
            requested_model=configs[config].model,
            returned_model_ids=[configs[config].model],
            versions={"python": "3.13", "swapcheck": "0.1.0"},
            git_commit=COMMIT,
            contract_tag_commit=COMMIT,
            warmups=[],
            started_at="2026-10-21T12:00:00+00:00",
            ended_at="2026-10-21T12:01:00+00:00",
            complete=True,
            incomplete_reason=None,
            retry_errors_passes=0,
            retry_errors_rewritten=0,
            totals=RunTotals(
                by_status=dict(Counter(row.status for row in rows)),
                tokens=usage,
                billed_usd=0.01,
                case_normalized=0,
                n_429=0,
            ),
        )
        _json(run_dir / "run.json", meta.model_dump(mode="json"))
        manifest.runs.append(
            ManifestRun(
                contract_tag=contract.tag,
                contract_tag_commit=COMMIT,
                run_id=run_id,
                config_id=config,
                split=split,
                item_list_sha256=meta.item_list_sha256,
                **hashes[config],
            )
        )
    save_manifest(root / "runs", manifest)


def test_golden_replays_committed_bytes(tmp_path: Path) -> None:
    runs, contract, items, groups = load_golden()
    assert len(items) == 210
    assert set(groups.slice_of(it.intent) for it in items) == set(groups.slices)
    assert verify_manifest(load_manifest(runs), contract, runs) == []
    result = write_decisions(runs, contract, items, groups, tmp_path)
    assert tuple(result) == DECISIONS
    assert {path.name for path in tmp_path.iterdir()} == {f"{decision}.md" for decision in DECISIONS}
    for decision in DECISIONS:
        assert (tmp_path / f"{decision}.md").read_bytes() == (GOLDEN / "expected" / f"{decision}.md").read_bytes()
    for decision in NOT_RUN:
        assert "**Verdict: NOT RUN**" in result[decision]


def test_golden_valid_changed_input_changes_record(tmp_path: Path) -> None:
    root = tmp_path / "fixture"
    shutil.copytree(GOLDEN, root)
    runs, contract, items, groups = load_golden(root)
    run_dir = runs / "golden-luna-none-cert"
    rows = read_rows(run_dir)
    assert rows[0].intent != items[0].intent
    rows[0] = rows[0].model_copy(
        update={
            "intent": items[0].intent,
            "confidence": 0.99,
            "raw_output": json.dumps({"intent": items[0].intent, "confidence": 0.99}),
        }
    )
    payload = "".join(row.model_dump_json() + "\n" for row in rows).encode()
    (run_dir / "items.jsonl.gz").write_bytes(gzip.compress(payload, mtime=0))
    assert verify_manifest(load_manifest(runs), contract, runs) == []
    write_decisions(runs, contract, items, groups, tmp_path / "changed")
    assert (tmp_path / "changed" / "D-A1.md").read_bytes() != (GOLDEN / "expected" / "D-A1.md").read_bytes()
    assert (tmp_path / "changed" / "D-B1.md").read_bytes() == (GOLDEN / "expected" / "D-B1.md").read_bytes()
