"""T-R7: freeze guard and one-run rule for `cert`/`aa` runs (spec §9.5), in temporary git repositories."""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest
from fakes import (
    FakeClock,
    clone_repo,
    git,
    items,
    make_repo,
    ok_body,
    ok_handler,
    request_text,
    retry_sync,
    run_sync,
)

from swapcheck.configs import load_configurations
from swapcheck.freeze import FreezeError, check_freeze
from swapcheck.manifest import MANIFEST, ManifestError
from swapcheck.prompt import Prompt
from swapcheck.records import read_meta, read_rows

CONFIGS = load_configurations()


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return make_repo(tmp_path_factory.mktemp("template") / "repo")


@pytest.fixture
def repo(template: Path, tmp_path: Path) -> Path:
    return clone_repo(template, tmp_path / "repo")


def tag_sha(repo: Path) -> str:
    return git(repo, "rev-parse", "contract-v1^{commit}").strip()


class Recorder:
    def __init__(self, fail: set[str] | None = None) -> None:
        self.fail = fail or set()
        self.requested: list[str] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        text = request_text(request)
        self.requested.append(text)
        if text in self.fail:
            return httpx.Response(400, json={"error": {"message": "bad"}})
        return httpx.Response(200, json=ok_body())


def test_r7_refuses_without_the_tag(tmp_path: Path, incumbent: Prompt) -> None:
    repo = make_repo(tmp_path / "repo", tag=None)
    with pytest.raises(FreezeError, match="does not exist"):
        check_freeze(repo)
    recorder = Recorder()
    with pytest.raises(FreezeError):
        run_sync(CONFIGS["inc"], incumbent, "cert", items(3), recorder, repo, run_id="c")
    assert recorder.requested == []
    assert not (repo / "runs").exists()


@pytest.mark.parametrize(
    "path",
    [
        "src/swapcheck/core.py",
        "prompts/incumbent-v1.md",
        "config/limits.yaml",
        "contracts/contract-v1.yaml",
        "analysis/power.py",
    ],
)
def test_r7_refuses_a_modified_frozen_file(repo: Path, path: str) -> None:
    (repo / path).write_text("changed\n")
    with pytest.raises(FreezeError, match=re.escape(path)):
        check_freeze(repo)


def test_r7_refuses_committed_staged_untracked_and_deleted_changes(repo: Path) -> None:
    (repo / "config" / "extra.yaml").write_text("new: 1\n")  # untracked
    with pytest.raises(FreezeError, match=re.escape("config/extra.yaml")):
        check_freeze(repo)
    (repo / "config" / "extra.yaml").unlink()

    (repo / "analysis" / "power.py").unlink()
    with pytest.raises(FreezeError, match=re.escape("analysis/power.py")):
        check_freeze(repo)
    git(repo, "checkout", "--", "analysis/power.py")

    (repo / "prompts" / "incumbent-v1.md").write_text("edited\n")
    git(repo, "add", "prompts/incumbent-v1.md")  # staged
    with pytest.raises(FreezeError, match=re.escape("prompts/incumbent-v1.md")):
        check_freeze(repo)
    git(repo, "commit", "--quiet", "-m", "edit after the freeze")  # committed after the tag
    with pytest.raises(FreezeError, match=re.escape("prompts/incumbent-v1.md")):
        check_freeze(repo)


def test_r7_allows_changes_outside_frozen_paths(repo: Path) -> None:
    (repo / "runs" / "earlier-run").mkdir(parents=True)
    (repo / "runs" / "earlier-run" / "run.json").write_text("{}\n")
    git(repo, "add", "runs")
    git(repo, "commit", "--quiet", "-m", "records")  # HEAD moves past the tag
    (repo / "runs" / "partial").mkdir()
    (repo / "runs" / "partial" / "items.jsonl").write_text('{"item_id": "te')
    (repo / "README.md").write_text("edited\n")
    assert check_freeze(repo) == tag_sha(repo)


def test_r7_cert_run_one_run_rule_resume_and_retry(repo: Path, incumbent: Prompt) -> None:
    cfg, its = CONFIGS["luna-none"], items(6)
    (repo / "runs" / "earlier-run").mkdir(parents=True)
    (repo / "runs" / "earlier-run" / "notes.txt").write_text("an earlier run directory\n")

    class Killed(Exception):
        pass

    async def dies_at_item_3(request: httpx.Request) -> httpx.Response:
        if request_text(request) == its[3].text:
            raise Killed
        return httpx.Response(200, json=ok_body())

    with pytest.raises(BaseExceptionGroup):
        run_sync(cfg, incumbent, "cert", its, dies_at_item_3, repo, run_id="c1", concurrency=1)
    resumed = Recorder(fail={its[5].text})
    meta = run_sync(cfg, incumbent, "cert", its, resumed, repo, run_id="c1")  # resume is allowed
    assert meta.complete and meta.contract_tag_commit == tag_sha(repo)
    assert len(read_rows(repo / "runs" / "c1")) == 6

    second = Recorder()
    with pytest.raises(ManifestError, match="already has run c1"):
        run_sync(cfg, incumbent, "cert", its, second, repo, run_id="c2", clock=FakeClock())
    assert second.requested == [] and not (repo / "runs" / "c2").exists()

    retried = retry_sync(repo / "runs" / "c1", cfg, incumbent, its, Recorder(), repo)  # retry-errors is allowed
    assert retried.retry_errors_rewritten == 1

    run_sync(cfg, incumbent, "aa", its[:2], ok_handler(), repo, run_id="a1")  # another split: its own run
    assert read_meta(repo / "runs" / "a1").contract_tag_commit == tag_sha(repo)
    assert (repo / "runs" / MANIFEST).exists()


def test_r7_dev_runs_need_no_tag(tmp_path: Path, incumbent: Prompt) -> None:
    repo = make_repo(tmp_path / "repo", tag=None)
    (repo / "src" / "swapcheck" / "core.py").write_text("X = 2\n")
    meta = run_sync(CONFIGS["luna-none"], incumbent, "dev", items(2), ok_handler(), repo, run_id="d")
    assert meta.complete and meta.contract_tag_commit is None
    assert not (repo / "runs" / MANIFEST).exists()
