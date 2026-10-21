"""T-D1 to T-D4: data download, splits, slices and intent groups (spec §2)."""

from __future__ import annotations

import importlib.util
import itertools
from collections import Counter
from pathlib import Path

import pytest

from swapcheck import data
from swapcheck.groups import OUT_OF_SCOPE, REPO_ROOT, IntentGroups

CERT_SLICES = {
    "cards": 1407,
    "card_payments": 1473,
    "cash": 966,
    "transfers": 1328,
    "top_ups": 844,
    "account_other": 1143,
    "out_of_scope": 2597,
}


def test_d1_corrupted_file_fails_with_clear_error(tmp_path: Path) -> None:
    (tmp_path / "train.csv").write_text("text,category\nhello,card_arrival\n", encoding="utf-8")
    with pytest.raises(data.DataIntegrityError, match=r"does not match the pinned b06e26ac"):
        data.download(tmp_path)


def test_d1_verified_files_have_the_pinned_hashes() -> None:
    for name, path in data.download().items():
        assert data.sha256_file(path) == data.SOURCES[name][1]


def test_d2_split_sizes_and_structure(splits: dict[str, list[data.Item]], groups: IntentGroups) -> None:
    ids = {name: [it.item_id for it in items] for name, items in splits.items()}
    sets = {name: set(v) for name, v in ids.items()}
    assert {name: len(v) for name, v in ids.items()} == {
        "examples": 250,
        "dev": 3075,
        "cert": 9758,
        "pilot": 100,
        "aa": 3080,
    }
    assert all(len(v) == len(sets[name]) for name, v in ids.items())
    assert not sets["examples"] & sets["dev"]
    assert not sets["examples"] & sets["cert"]
    assert not sets["dev"] & sets["cert"]
    assert len(sets["examples"] | sets["dev"] | sets["cert"]) == 10_003 + 3_080
    assert sets["aa"] <= sets["cert"]
    assert sets["aa"] == {f"test-{i}" for i in range(3080)}
    assert sets["pilot"] <= sets["dev"]

    dev_counts = Counter(it.intent for it in splits["dev"])
    assert sum(n for i, n in dev_counts.items() if i in groups.out_of_scope) == 1075
    assert dev_counts["contactless_not_working"] == 35
    assert {n for i, n in dev_counts.items() if i != "contactless_not_working"} == {40}

    in_scope = set(groups.in_scope)
    assert Counter(it.intent for it in splits["examples"]) == dict.fromkeys(in_scope, 5)
    pilot_in = Counter(it.intent for it in splits["pilot"] if it.intent in in_scope)
    assert pilot_in == dict.fromkeys(in_scope, 1)
    assert sum(it.intent not in in_scope for it in splits["pilot"]) == 50


def test_d2_selection_follows_digest_order(splits: dict[str, list[data.Item]]) -> None:
    """Within an intent, every examples digest precedes every dev digest, which precedes cert's."""
    first: dict[str, dict[str, list[str]]] = {}
    for name in ("examples", "dev", "cert"):
        for it in splits[name]:
            if it.item_id.startswith("train-"):
                first.setdefault(it.intent, {}).setdefault(name, []).append(it.digest)
    for parts in first.values():
        ordered = [parts[n] for n in ("examples", "dev", "cert") if n in parts]
        for lower, upper in itertools.pairwise(ordered):
            assert max(lower) < min(upper)


def test_d3_cert_slice_sizes(splits: dict[str, list[data.Item]], groups: IntentGroups) -> None:
    sizes = Counter(groups.slice_of(it.intent) for it in splits["cert"])
    assert dict(sizes) == CERT_SLICES
    spec = importlib.util.spec_from_file_location("power", REPO_ROOT / "analysis" / "power.py")
    assert spec and spec.loader
    power = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(power)
    assert power.CERT_SLICES == CERT_SLICES


def test_d4_intent_groups(groups: IntentGroups, all_rows: list[data.Item]) -> None:
    grouped = [i for intents in groups.in_scope_groups.values() for i in intents]
    assert len(grouped) == len(set(grouped)) == 50
    assert len(groups.out_of_scope) == len(set(groups.out_of_scope)) == 27
    assert not set(grouped) & set(groups.out_of_scope)
    assert set(grouped) | set(groups.out_of_scope) == {it.intent for it in all_rows}
    assert groups.slices[-1] == OUT_OF_SCOPE
