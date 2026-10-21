"""`runs/manifest.yaml` (spec §9.5, §10): the single run per configuration and split under a contract
tag, and the decisions not run. Written by the runner, never by hand; `verify_manifest` is what
`decide` checks before using any run."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from swapcheck.contract import Contract
from swapcheck.freeze import GUARDED_SPLITS
from swapcheck.records import RUN_JSON, Split, read_meta

MANIFEST = "manifest.yaml"
NotRunReason = Literal["no dev gain", "budget"]


class ManifestError(RuntimeError):
    """The manifest refuses an entry (one run per configuration and split under a tag)."""


class ManifestRun(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_tag: str
    contract_tag_commit: str
    config_id: str
    split: Split
    run_id: str
    config_sha256: str
    prompt_sha256: str
    schema_sha256: str
    item_list_sha256: str


class NotRun(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_tag: str
    decision_id: str
    reason: NotRunReason


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runs: list[ManifestRun] = []
    not_run: list[NotRun] = []

    def run_for(self, contract_tag: str, config_id: str, split: str) -> ManifestRun | None:
        for entry in self.runs:
            if (entry.contract_tag, entry.config_id, entry.split) == (contract_tag, config_id, split):
                return entry
        return None


def load_manifest(runs_dir: Path) -> Manifest:
    path = runs_dir / MANIFEST
    if not path.exists():
        return Manifest()
    return Manifest.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def save_manifest(runs_dir: Path, manifest: Manifest) -> None:
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / MANIFEST
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.safe_dump(manifest.model_dump(mode="json"), sort_keys=False), encoding="utf-8")
    os.replace(tmp, path)


def append_run(runs_dir: Path, entry: ManifestRun) -> None:
    """Record a run at its start. A second run ID for the same tag, configuration and split is refused;
    recording the same run again (a restart before its first row) changes nothing."""
    manifest = load_manifest(runs_dir)
    existing = manifest.run_for(entry.contract_tag, entry.config_id, entry.split)
    if existing is not None:
        if existing.run_id != entry.run_id:
            raise ManifestError(
                f"{entry.config_id} on {entry.split} already has run {existing.run_id} under {entry.contract_tag}; "
                "only resume and retry-errors are allowed (spec §9.5)"
            )
        if existing != entry:
            raise ManifestError(f"run {entry.run_id} is already in the manifest with different hashes")
        return
    manifest.runs.append(entry)
    save_manifest(runs_dir, manifest)


def add_not_run(runs_dir: Path, decision_id: str, reason: NotRunReason, *, contract_tag: str) -> None:
    """List a decision as NOT RUN (spec §7.2) with its reason."""
    manifest = load_manifest(runs_dir)
    for entry in manifest.not_run:
        if (entry.contract_tag, entry.decision_id) == (contract_tag, decision_id):
            if entry.reason != reason:
                raise ManifestError(f"{decision_id} is already NOT RUN under {contract_tag} for {entry.reason!r}")
            return
    manifest.not_run.append(NotRun(contract_tag=contract_tag, decision_id=decision_id, reason=reason))
    save_manifest(runs_dir, manifest)


def verify_manifest(
    manifest: Manifest, contract: Contract, runs_dir: Path, *, tag_commit: str | None = None
) -> list[str]:
    """Problems that make `decide` refuse (spec §10); empty when the runs under the contract's tag are usable.

    Checks each entry under the tag against the contract and against its own `run.json`, requires the
    contract tag commit (equal to `tag_commit` when given), and requires every `cert`/`aa` run directory
    to be listed.
    """
    problems: list[str] = []
    for entry in manifest.runs:
        if entry.contract_tag != contract.tag:
            continue
        where = f"{entry.run_id} ({entry.config_id}, {entry.split})"
        expected = contract.configurations.get(entry.config_id)
        if expected is None:
            problems.append(f"{where}: configuration {entry.config_id} is not in the contract")
        else:
            for name in ("config_sha256", "prompt_sha256", "schema_sha256"):
                if getattr(entry, name) != getattr(expected, name):
                    problems.append(f"{where}: {name} differs from the contract")
        expected_items = contract.item_lists.get(entry.split)
        if expected_items is None:
            problems.append(f"{where}: split {entry.split} has no item-list hash in the contract")
        elif entry.item_list_sha256 != expected_items:
            problems.append(f"{where}: item_list_sha256 differs from the contract")
        if not entry.contract_tag_commit:
            problems.append(f"{where}: contract tag commit is missing")
        elif tag_commit is not None and entry.contract_tag_commit != tag_commit:
            problems.append(f"{where}: contract tag commit {entry.contract_tag_commit[:12]} is not {tag_commit[:12]}")
        run_json = runs_dir / entry.run_id / RUN_JSON
        if not run_json.exists():
            problems.append(f"{where}: run directory or run.json is missing")
            continue
        meta = read_meta(run_json.parent)
        recorded = {
            "config_id": meta.config_id,
            "split": meta.split,
            "config_sha256": meta.config_sha256,
            "prompt_sha256": meta.prompt_sha256,
            "schema_sha256": meta.schema_sha256,
            "item_list_sha256": meta.item_list_sha256,
            "contract_tag_commit": meta.contract_tag_commit,
        }
        for name, value in recorded.items():
            if value != getattr(entry, name):
                problems.append(f"{where}: run.json {name} differs from the manifest")

    listed = {entry.run_id for entry in manifest.runs}
    for run_json in sorted(runs_dir.glob(f"*/{RUN_JSON}")):
        meta = read_meta(run_json.parent)
        if meta.split in GUARDED_SPLITS and meta.run_id not in listed:
            problems.append(f"{meta.run_id} ({meta.config_id}, {meta.split}): run directory is not in the manifest")
    return problems
