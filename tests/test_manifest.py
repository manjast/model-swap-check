"""T-R10: `runs/manifest.yaml` written by the runner, NOT RUN entries, and `verify_manifest` (spec §7.2, §9.5, §10)."""

from __future__ import annotations

import fcntl
import json
import shutil
from pathlib import Path

import httpx
import pytest
from fakes import clone_repo, git, items, make_repo, ok_body, ok_handler, run_sync

from swapcheck import manifest as manifest_mod
from swapcheck.configs import load_configurations
from swapcheck.contract import Contract, ContractConfiguration
from swapcheck.manifest import (
    MANIFEST,
    MANIFEST_LOCK,
    Manifest,
    ManifestError,
    ManifestRun,
    add_not_run,
    append_run,
    load_manifest,
    save_manifest,
    verify_manifest,
)
from swapcheck.prompt import Prompt
from swapcheck.records import RUN_JSON, RunMeta, read_meta

CONFIGS = load_configurations()


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return make_repo(tmp_path_factory.mktemp("template") / "repo")


@pytest.fixture
def repo(template: Path, tmp_path: Path) -> Path:
    return clone_repo(template, tmp_path / "repo")


def contract_for(*metas: RunMeta) -> Contract:
    return Contract(
        tag="contract-v1",
        configurations={
            m.config_id: ContractConfiguration(
                config_sha256=m.config_sha256, prompt_sha256=m.prompt_sha256, schema_sha256=m.schema_sha256
            )
            for m in metas
        },
        item_lists={m.split: m.item_list_sha256 for m in metas},
    )


@pytest.fixture
def certified(repo: Path, incumbent: Prompt) -> tuple[Path, Contract, str]:
    """One `cert` and one `aa` run under the tag, plus a `dev` run; returns runs dir, contract, tag commit."""
    cert = run_sync(CONFIGS["luna-none"], incumbent, "cert", items(3), ok_handler(), repo, run_id="luna-cert")
    aa = run_sync(CONFIGS["inc"], incumbent, "aa", items(2), ok_handler(), repo, run_id="inc-aa")
    run_sync(CONFIGS["haiku55-off"], incumbent, "dev", items(2), ok_handler(), repo, run_id="haiku-dev")
    return repo / "runs", contract_for(cert, aa), git(repo, "rev-parse", "contract-v1^{commit}").strip()


def test_r10_runner_records_cert_run_in_manifest_before_any_request(repo: Path, incumbent: Prompt) -> None:
    seen: list[Manifest] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if not seen:
            seen.append(load_manifest(repo / "runs"))
        return httpx.Response(200, json=ok_body())

    meta = run_sync(CONFIGS["luna-none"], incumbent, "cert", items(2), handler, repo, run_id="c")
    (entry,) = seen[0].runs
    assert (entry.run_id, entry.config_id, entry.split, entry.contract_tag) == ("c", "luna-none", "cert", "contract-v1")
    assert (entry.config_sha256, entry.prompt_sha256, entry.schema_sha256, entry.item_list_sha256) == (
        meta.config_sha256,
        meta.prompt_sha256,
        meta.schema_sha256,
        meta.item_list_sha256,
    )
    assert entry.contract_tag_commit == meta.contract_tag_commit


def test_r10_not_run_decisions_listed_with_reason(tmp_path: Path) -> None:
    add_not_run(tmp_path, "D-A2", "no dev gain", contract_tag="contract-v1")
    add_not_run(tmp_path, "D-B2", "budget", contract_tag="contract-v1")
    add_not_run(tmp_path, "D-A2", "no dev gain", contract_tag="contract-v1")  # idempotent
    with pytest.raises(ManifestError):
        add_not_run(tmp_path, "D-A2", "budget", contract_tag="contract-v1")
    manifest = load_manifest(tmp_path)
    assert [(n.decision_id, n.reason) for n in manifest.not_run] == [("D-A2", "no dev gain"), ("D-B2", "budget")]
    assert "no dev gain" in (tmp_path / MANIFEST).read_text()


def test_r10_consistent_manifest_has_no_problems(certified: tuple[Path, Contract, str]) -> None:
    runs_dir, contract, tag_commit = certified
    assert verify_manifest(load_manifest(runs_dir), contract, runs_dir, tag_commit=tag_commit) == []


@pytest.mark.parametrize("field", ["config_sha256", "prompt_sha256", "schema_sha256"])
def test_r10_configuration_hash_mismatch_is_refused(certified: tuple[Path, Contract, str], field: str) -> None:
    runs_dir, contract, _ = certified
    changed = contract.configurations["luna-none"].model_copy(update={field: "0" * 64})
    contract = contract.model_copy(update={"configurations": {**contract.configurations, "luna-none": changed}})
    problems = verify_manifest(load_manifest(runs_dir), contract, runs_dir)
    assert len(problems) == 1 and "luna-cert" in problems[0] and field in problems[0]


def test_r10_item_list_mismatch_is_refused(certified: tuple[Path, Contract, str]) -> None:
    runs_dir, contract, _ = certified
    contract = contract.model_copy(update={"item_lists": {**contract.item_lists, "aa": "0" * 64}})
    problems = verify_manifest(load_manifest(runs_dir), contract, runs_dir)
    assert len(problems) == 1 and "inc-aa" in problems[0] and "item_list_sha256" in problems[0]


def test_r10_configuration_missing_from_contract_is_refused(certified: tuple[Path, Contract, str]) -> None:
    runs_dir, contract, _ = certified
    contract = contract.model_copy(update={"configurations": {"inc": contract.configurations["inc"]}})
    problems = verify_manifest(load_manifest(runs_dir), contract, runs_dir)
    assert len(problems) == 1 and "not in the contract" in problems[0]


def test_r10_missing_or_wrong_contract_tag_commit_is_refused(certified: tuple[Path, Contract, str]) -> None:
    runs_dir, contract, tag_commit = certified
    manifest = load_manifest(runs_dir)
    assert any("is not" in p for p in verify_manifest(manifest, contract, runs_dir, tag_commit="f" * 40))

    first = manifest.runs[0].model_copy(update={"contract_tag_commit": ""})
    save_manifest(runs_dir, Manifest(runs=[first, *manifest.runs[1:]]))
    problems = verify_manifest(load_manifest(runs_dir), contract, runs_dir, tag_commit=tag_commit)
    assert any("contract tag commit is missing" in p for p in problems)

    meta_path = runs_dir / "inc-aa" / RUN_JSON
    meta = read_meta(meta_path.parent).model_copy(update={"contract_tag_commit": None})
    meta_path.write_text(meta.model_dump_json())
    problems = verify_manifest(load_manifest(runs_dir), contract, runs_dir, tag_commit=tag_commit)
    assert any("inc-aa" in p and "contract_tag_commit" in p for p in problems)


def test_r10_cert_run_directory_missing_from_manifest_is_refused(certified: tuple[Path, Contract, str]) -> None:
    runs_dir, contract, _ = certified
    shutil.copytree(runs_dir / "luna-cert", runs_dir / "luna-cert-again")
    meta = json.loads((runs_dir / "luna-cert-again" / RUN_JSON).read_text())
    (runs_dir / "luna-cert-again" / RUN_JSON).write_text(json.dumps({**meta, "run_id": "luna-cert-again"}))
    problems = verify_manifest(load_manifest(runs_dir), contract, runs_dir)
    assert problems == ["luna-cert-again (luna-none, cert): run directory is not in the manifest"]  # dev run is fine


def test_r10_copied_cert_run_directory_with_unedited_run_json_is_refused(
    certified: tuple[Path, Contract, str],
) -> None:
    runs_dir, contract, _ = certified
    shutil.copytree(runs_dir / "luna-cert", runs_dir / "luna-cert-copy")  # run.json still says luna-cert
    problems = verify_manifest(load_manifest(runs_dir), contract, runs_dir)
    assert problems == [
        "luna-cert-copy (luna-none, cert): run.json run_id luna-cert differs from the directory name",
        "luna-cert-copy (luna-none, cert): run directory is not in the manifest",
    ]


def test_r10_listed_directory_holding_another_run_id_is_refused(certified: tuple[Path, Contract, str]) -> None:
    runs_dir, contract, _ = certified
    meta_path = runs_dir / "inc-aa" / RUN_JSON
    meta_path.write_text(read_meta(meta_path.parent).model_copy(update={"run_id": "inc-aa-other"}).model_dump_json())
    problems = verify_manifest(load_manifest(runs_dir), contract, runs_dir)
    assert "inc-aa (inc, aa): run.json run_id differs from the manifest" in problems
    assert "inc-aa (inc, aa): run.json run_id inc-aa-other differs from the directory name" in problems


def test_r10_manifest_changes_hold_the_interprocess_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every load and save inside `append_run` and `add_not_run` happens while another open file
    description of the lock file cannot take it, as a second process could not."""
    held: list[bool] = []

    def probe() -> None:
        with (tmp_path / MANIFEST_LOCK).open("a") as other:
            try:
                fcntl.flock(other.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                held.append(True)
            else:
                fcntl.flock(other.fileno(), fcntl.LOCK_UN)
                held.append(False)

    real_load, real_save = manifest_mod.load_manifest, manifest_mod.save_manifest

    def load(runs_dir: Path) -> Manifest:
        probe()
        return real_load(runs_dir)

    def save(runs_dir: Path, manifest: Manifest) -> None:
        probe()
        real_save(runs_dir, manifest)

    monkeypatch.setattr(manifest_mod, "load_manifest", load)
    monkeypatch.setattr(manifest_mod, "save_manifest", save)
    entry = ManifestRun(
        contract_tag="contract-v1",
        contract_tag_commit="a" * 40,
        config_id="inc",
        split="cert",
        run_id="one",
        config_sha256="c",
        prompt_sha256="p",
        schema_sha256="s",
        item_list_sha256="i",
    )
    append_run(tmp_path, entry)
    add_not_run(tmp_path, "D-A2", "no dev gain", contract_tag="contract-v1")
    assert held == [True] * 4  # load and save of each change
    probe()
    assert held[-1] is False  # released afterwards
    assert [r.run_id for r in real_load(tmp_path).runs] == ["one"]


def test_r10_manifest_entry_without_run_directory_is_refused(certified: tuple[Path, Contract, str]) -> None:
    runs_dir, contract, _ = certified
    shutil.rmtree(runs_dir / "inc-aa")
    problems = verify_manifest(load_manifest(runs_dir), contract, runs_dir)
    assert len(problems) == 1 and "inc-aa" in problems[0] and "missing" in problems[0]


def test_r10_manifest_refuses_a_second_run_id(tmp_path: Path) -> None:
    entry = ManifestRun(
        contract_tag="contract-v1",
        contract_tag_commit="a" * 40,
        config_id="inc",
        split="cert",
        run_id="one",
        config_sha256="c",
        prompt_sha256="p",
        schema_sha256="s",
        item_list_sha256="i",
    )
    append_run(tmp_path, entry)
    append_run(tmp_path, entry)  # recording the same run again is a no-op
    with pytest.raises(ManifestError):
        append_run(tmp_path, entry.model_copy(update={"run_id": "two"}))
    append_run(tmp_path, entry.model_copy(update={"run_id": "two", "contract_tag": "contract-v2"}))
    assert [r.run_id for r in load_manifest(tmp_path).runs] == ["one", "two"]
