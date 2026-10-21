from __future__ import annotations

import pytest

from swapcheck import data
from swapcheck.groups import IntentGroups, load_groups
from swapcheck.prompt import Prompt, load_prompt


@pytest.fixture(scope="session")
def groups() -> IntentGroups:
    return load_groups()


@pytest.fixture(scope="session")
def splits(groups: IntentGroups) -> dict[str, list[data.Item]]:
    """The real splits; downloads and verifies Banking77 on first use (cached under data/raw)."""
    return data.load_splits(groups)


@pytest.fixture(scope="session")
def all_rows() -> list[data.Item]:
    paths = data.download()
    return data.read_rows(paths["train"], "train") + data.read_rows(paths["test"], "test")


@pytest.fixture(scope="session")
def incumbent() -> Prompt:
    return load_prompt()
