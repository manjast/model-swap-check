"""The parts of `contracts/contract-v1.yaml` (spec §7.7) that run verification reads.

M2/M4 extend this model with τ values, weights, margins, seeds and the budget plan; fields not
modelled here are ignored on load until then.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from swapcheck.groups import REPO_ROOT
from swapcheck.records import Split

CONTRACT_PATH = REPO_ROOT / "contracts" / "contract-v1.yaml"


class ContractConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    config_sha256: str
    prompt_sha256: str
    schema_sha256: str


class Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    tag: str  # the git tag the contract is frozen under, e.g. "contract-v1"
    configurations: dict[str, ContractConfiguration]
    item_lists: dict[Split, str]  # split -> item-list SHA-256 (spec §10)


def load_contract(path: Path = CONTRACT_PATH) -> Contract:
    return Contract.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
