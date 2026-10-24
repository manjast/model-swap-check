from __future__ import annotations

from pathlib import Path

import pytest

from swapcheck.contract import Contract, FrozenContractError, load_contract, write_contract

HEADER = "# frozen\n"


def contract(tag: str) -> Contract:
    return Contract(tag=tag, configurations={}, item_lists={"cert": "a" * 64})


def test_write_contract_never_changes_an_existing_contract(tmp_path: Path) -> None:
    path = tmp_path / "contracts" / "contract-v1.yaml"
    write_contract(path, contract("contract-v1"), HEADER)
    frozen = path.read_bytes()
    assert load_contract(path) == contract("contract-v1")

    write_contract(path, contract("contract-v1"), HEADER)  # the same result again is allowed
    with pytest.raises(FrozenContractError, match="differs"):
        write_contract(path, contract("contract-v9"), HEADER)
    with pytest.raises(FrozenContractError, match="differs"):
        write_contract(path, contract("contract-v1"), "# another header\n")
    assert path.read_bytes() == frozen
