"""Banking77 download, verification and splits (spec §2)."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import tempfile
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from swapcheck.groups import REPO_ROOT, IntentGroups

COMMIT = "57ec275d8078af65b7731c2a98be812d844a6d6b"
SOURCES: dict[str, tuple[str, str]] = {
    "train": (
        f"https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/{COMMIT}/banking_data/train.csv",
        "b06e26ac675513959a63135f11b94ea7786ed02da65db93a5650d8838cbc664b",
    ),
    "test": (
        f"https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/{COMMIT}/banking_data/test.csv",
        "d12d6e3bc4c3103966ae786dc435913c0c563dfa328f5a3646d0e62cfeeb474d",
    ),
}
DATA_DIR = REPO_ROOT / "data"
N_EXAMPLES = 5
N_DEV = 40
SPLITS = ("examples", "dev", "cert", "pilot", "aa")


class DataIntegrityError(RuntimeError):
    """A downloaded file does not match its pinned SHA-256."""


@dataclass(frozen=True)
class Item:
    item_id: str
    text: str
    intent: str

    @property
    def digest(self) -> str:
        return text_digest("model-swap-check-v1", self.item_id, self.text)

    @property
    def pilot_digest(self) -> str:
        return text_digest("model-swap-check-pilot", self.item_id, self.text)


def text_digest(salt: str, item_id: str, text: str) -> str:
    return hashlib.sha256(f"{salt}:{item_id}:{text}".encode()).hexdigest()


def normalize(text: str) -> str:
    """Casefolded, whitespace-collapsed form used for text comparisons (spec §2.5)."""
    return " ".join(text.casefold().split())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(path: Path, expected: str) -> None:
    actual = sha256_file(path)
    if actual != expected:
        raise DataIntegrityError(
            f"{path}: SHA-256 {actual} does not match the pinned {expected} (spec §2.1). "
            "Delete the file and run `swapcheck data` again."
        )


def download(raw_dir: Path = DATA_DIR / "raw") -> dict[str, Path]:
    """Fetch both CSVs at the pinned commit unless a verified copy exists; verify either way."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name, (url, expected) in SOURCES.items():
        path = raw_dir / f"{name}.csv"
        if not path.exists():
            fd, tmp = tempfile.mkstemp(dir=raw_dir, suffix=".part")
            try:
                with urllib.request.urlopen(url, timeout=60) as response, os.fdopen(fd, "wb") as f:
                    shutil.copyfileobj(response, f)
                verify(Path(tmp), expected)
                os.replace(tmp, path)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
        verify(path, expected)
        paths[name] = path
    return paths


def read_rows(path: Path, prefix: str) -> list[Item]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        if header != ["text", "category"]:
            raise DataIntegrityError(f"{path}: unexpected header {header}")
        return [Item(f"{prefix}-{i}", text, intent) for i, (text, intent) in enumerate(reader)]


def make_splits(train: list[Item], test: list[Item], groups: IntentGroups) -> dict[str, list[Item]]:
    """The five splits of spec §2.3, each in ascending digest order."""
    in_scope = set(groups.in_scope)
    by_intent: dict[str, list[Item]] = defaultdict(list)
    for item in train:
        by_intent[item.intent].append(item)

    examples: list[Item] = []
    dev: list[Item] = []
    for intent, rows in by_intent.items():
        rows.sort(key=lambda it: it.digest)
        n_ex = N_EXAMPLES if intent in in_scope else 0
        examples += rows[:n_ex]
        dev += rows[n_ex : n_ex + N_DEV]
    taken = {it.item_id for it in examples} | {it.item_id for it in dev}
    cert = [it for it in train if it.item_id not in taken] + test

    pilot: list[Item] = []
    dev_by_intent: dict[str, list[Item]] = defaultdict(list)
    for item in dev:
        dev_by_intent[item.intent].append(item)
    for intent in groups.in_scope:
        pilot.append(min(dev_by_intent[intent], key=lambda it: it.pilot_digest))
    oos_dev = sorted((it for it in dev if it.intent not in in_scope), key=lambda it: it.pilot_digest)
    pilot += oos_dev[:50]

    splits = {"examples": examples, "dev": dev, "cert": cert, "pilot": pilot, "aa": list(test)}
    return {name: sorted(items, key=lambda it: it.digest) for name, items in splits.items()}


def item_list_hash(items: list[Item]) -> str:
    """SHA-256 of the newline-joined item IDs in split order; recorded in run.json (spec §10)."""
    return hashlib.sha256("\n".join(it.item_id for it in items).encode()).hexdigest()


def load_splits(groups: IntentGroups, raw_dir: Path = DATA_DIR / "raw") -> dict[str, list[Item]]:
    paths = download(raw_dir)
    return make_splits(read_rows(paths["train"], "train"), read_rows(paths["test"], "test"), groups)


def write_splits(splits: dict[str, list[Item]], groups: IntentGroups, out_dir: Path = DATA_DIR / "splits") -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, items in splits.items():
        with (out_dir / f"{name}.jsonl").open("w", encoding="utf-8") as f:
            for it in items:
                row = {
                    "item_id": it.item_id,
                    "intent": it.intent,
                    "slice": groups.slice_of(it.intent),
                    "text": it.text,
                }
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
