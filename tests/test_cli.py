"""T-R6 (CLI part): after an in-run budget stop no later `cert`/`aa` run of that provider starts (spec §9.5)."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
from fakes import clone_repo, git, items, make_repo, ok_handler, run_sync

from swapcheck import cli, data
from swapcheck.budget import BUDGET_STOP, stopped_providers
from swapcheck.configs import load_configurations
from swapcheck.prompt import Prompt
from swapcheck.records import Split
from swapcheck.runner import RunBudget

CONFIGS = load_configurations()


class PastTheStopCheck(Exception):
    """`cmd_run` went on to load the split: it would have started the run."""


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return make_repo(tmp_path_factory.mktemp("template") / "repo")


@pytest.fixture
def repo(template: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A tagged repository as `cmd_run`'s root; loading the split raises instead of reading data."""
    root = clone_repo(template, tmp_path / "repo")
    monkeypatch.setattr(cli, "REPO_ROOT", root)
    monkeypatch.setattr(cli, "load_env", lambda: None)

    def no_split(*args: object, **kwargs: object) -> None:
        raise PastTheStopCheck

    monkeypatch.setattr(data, "load_splits", no_split)
    return root


def stop_at_ceiling(repo: Path, incumbent: Prompt, split: Split, reason: str) -> None:
    """A `luna-none` (OpenAI) run under the tag that stops early with `reason`."""
    budget = RunBudget(spent_before_usd=0.0, ceiling_usd=0.01, reason=reason)
    meta = run_sync(CONFIGS["luna-none"], incumbent, split, items(30), ok_handler(), repo, run_id="stop", budget=budget)
    assert meta.complete is False and meta.incomplete_reason == reason


def run_args(config: str, split: str) -> argparse.Namespace:
    return argparse.Namespace(config=config, split=split, run_id=None, retry_errors=None, ceiling_usd=None)


def test_r6_cert_run_refused_after_a_provider_budget_stop(repo: Path, incumbent: Prompt) -> None:
    stop_at_ceiling(repo, incumbent, "cert", BUDGET_STOP)
    with pytest.raises(SystemExit, match="openai had an in-run budget stop"):
        cli.cmd_run(run_args("inc", "aa"))
    with pytest.raises(PastTheStopCheck):  # another provider is not affected
        cli.cmd_run(run_args("haiku55-off", "cert"))


def test_r6_dev_ceiling_stop_does_not_stop_the_provider(repo: Path, incumbent: Prompt) -> None:
    stop_at_ceiling(repo, incumbent, "dev", "spend ceiling")
    assert stopped_providers(repo / "runs", CONFIGS, git(repo, "rev-parse", "contract-v1^{commit}").strip()) == set()
    with pytest.raises(PastTheStopCheck):
        cli.cmd_run(run_args("inc", "cert"))


def test_r6_budget_stop_under_another_tag_commit_does_not_count(repo: Path, incumbent: Prompt) -> None:
    stop_at_ceiling(repo, incumbent, "cert", BUDGET_STOP)
    commit = git(repo, "rev-parse", "contract-v1^{commit}").strip()
    assert stopped_providers(repo / "runs", CONFIGS, commit) == {"openai"}
    assert stopped_providers(repo / "runs", CONFIGS, "f" * 40) == set()
