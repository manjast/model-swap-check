"""Frozen runner provenance and analysis plan (spec §7.7)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from swapcheck.groups import REPO_ROOT
from swapcheck.records import Split

CONTRACT_PATH = REPO_ROOT / "contracts" / "contract-v1.yaml"


class ContractConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    config_sha256: str
    prompt_sha256: str
    schema_sha256: str


class Calibration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tau: float
    dev_w: float
    dev_a: float


class BudgetPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    planned_cert_runs: list[str]
    drop_order: list[str]
    not_run: dict[str, Literal["no dev gain", "budget"]]


class SelectionRecords(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reasoning: dict[str, str | None]
    jev_design: str
    dx_iteration: int
    dx_prompt_sha256: str
    records: dict[str, object]


class OrderSensitivity(BaseModel):
    """Pilot items whose choice changed when the 50 intents were reversed (spec §14)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    changed: int
    items: int


class AnalysisContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    incumbent_tau: float
    configurations: dict[str, Calibration]
    dev_counts: dict[str, int]
    cert_counts: dict[str, int]
    delta_w: float
    delta_s: float
    power: dict[str, float]
    dev_discordance: dict[str, dict[str, float]] = Field(default_factory=dict)
    slices: list[str]
    seeds: dict[str, int]
    code_version: str
    budget: BudgetPlan
    selections: SelectionRecords
    order_sensitivity: dict[str, OrderSensitivity]  # decision-interface configuration ID -> pilot measurement


class Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    tag: str  # the git tag the contract is frozen under, e.g. "contract-v1"
    configurations: dict[str, ContractConfiguration]
    item_lists: dict[Split, str]  # split -> item-list SHA-256 (spec §10)
    analysis: AnalysisContract | None = None


def load_contract(path: Path = CONTRACT_PATH) -> Contract:
    return Contract.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
