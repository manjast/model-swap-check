"""Budget planning and spend guards (spec §8.1, §9.1, §9.5).

Pure functions over explicit inputs: spend per provider (`swapcheck.cost.spent_usd`), per-item p90 cost
per configuration (`swapcheck.cost.CostModel.item_p90_usd`, from the pilot before `dev` and from `dev`
before the freeze), and the item counts of each split. A planned run is projected as items x p90.

Every limit here is `cap - reserve_margin_usd` (the in-run stop level of §9.5), for the pre-`dev` gate
and the pre-freeze projection alike, so a plan that fits is never cut short by the in-run stop.
Ceilings are absolute provider spend levels: a run stops once spend before it plus its own spend
reaches its ceiling.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from swapcheck.configs import Configuration
from swapcheck.groups import REPO_ROOT
from swapcheck.records import Split

BUDGET_PATH = REPO_ROOT / "config" / "budget.yaml"
SPLIT_SIZES: dict[str, int] = {"dev": 3075, "cert": 9758, "aa": 3080}
Level = Literal["low", "medium"]
Vendor = Literal["openai", "anthropic"]
NotRunReason = Literal["no dev gain", "budget"]


class BudgetConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    caps_usd: dict[str, float]
    reserve_margin_usd: float

    def limit(self, provider: str) -> float:
        """The highest spend a provider may reach: cap - reserve margin (spec §9.5)."""
        return self.caps_usd[provider] - self.reserve_margin_usd


def load_budget(path: Path = BUDGET_PATH) -> BudgetConfig:
    return BudgetConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class PlannedRun:
    """One planned run. `name` is the plan label (`aa`, `luna-R`, `luna-none-x-2`); `config_id` what it runs."""

    name: str
    config_id: str
    split: Split


def run_cost_usd(run: PlannedRun, p90: Mapping[str, float]) -> float:
    return SPLIT_SIZES[run.split] * p90[run.config_id]


def can_start(spent: float, ceiling: float) -> bool:
    """A run starts only while its provider's spend is below the run's ceiling."""
    return spent < ceiling


def _provider(run: PlannedRun, configs: Mapping[str, Configuration]) -> str:
    return configs[run.config_id].provider


# ---------------------------------------------------------------------------------------------------
# Pre-dev gate (after the pilot)

DX_ITERATIONS = 3  # spec §8.3; iteration 0 is luna-none itself
DEV_PLAN: tuple[PlannedRun, ...] = (
    PlannedRun("inc", "inc", "dev"),
    PlannedRun("jev-c51", "jev-c51", "dev"),
    PlannedRun("jev-noul", "jev-noul", "dev"),
    PlannedRun("luna-none", "luna-none", "dev"),
    PlannedRun("haiku55-off", "haiku55-off", "dev"),
    PlannedRun("luna-low", "luna-low", "dev"),
    PlannedRun("haiku55-low", "haiku55-low", "dev"),
    *(PlannedRun(f"luna-none-x-{i}", "luna-none-x", "dev") for i in range(1, DX_ITERATIONS + 1)),
    PlannedRun("luna-medium", "luna-medium", "dev"),
    PlannedRun("haiku55-medium", "haiku55-medium", "dev"),
)
# Skipped by the gate, in this order, until the provider fits (spec §9.5).
DEV_SKIP_ORDER: tuple[str, ...] = ("luna-medium", "haiku55-medium", "luna-low", "haiku55-low")
# No pilot run exists for luna-none-x; before `dev` its iterations are priced as luna-none (same model
# and settings, a prompt of the same kind).
PILOT_PROXY: dict[str, str] = {"luna-none-x": "luna-none"}


def mandatory_cert_runs(p90: Mapping[str, float]) -> tuple[PlannedRun, ...]:
    """The `cert` runs every plan keeps (spec §9.5). `jev-D` is priced as the dearer of the two designs."""
    jev = max(("jev-c51", "jev-noul"), key=lambda c: p90[c])
    return (
        PlannedRun("inc", "inc", "cert"),
        PlannedRun("luna-none", "luna-none", "cert"),
        PlannedRun("aa", "inc", "aa"),
        PlannedRun("haiku55-off", "haiku55-off", "cert"),
        PlannedRun("jev-D", jev, "cert"),
    )


@dataclass(frozen=True)
class DevRun:
    run: PlannedRun
    provider: str
    projected_usd: float
    ceiling_usd: float  # absolute provider spend at which this run stops as incomplete


@dataclass(frozen=True)
class DevGate:
    runs: tuple[DevRun, ...]  # §9.1 order
    skipped: tuple[str, ...]  # dev run names skipped by the gate; their levels are not in E (§8.1)
    cert_reserve_usd: dict[str, float]
    projected_usd: dict[str, float]  # spent + planned dev runs + mandatory cert reserve
    fits: dict[str, bool]  # False: even the plan without reasoning levels exceeds cap - margin


def pre_dev_gate(
    spent: Mapping[str, float],
    pilot_p90: Mapping[str, float],
    configs: Mapping[str, Configuration],
    budget: BudgetConfig,
    dev_plan: Sequence[PlannedRun] = DEV_PLAN,
) -> DevGate:
    """Spec §9.5 pre-`dev` gate: skip `*-medium`, then `*-low`, until spent + dev + cert reserve fits."""
    p90 = dict(pilot_p90)
    for cid, proxy in PILOT_PROXY.items():
        if cid not in p90 and proxy in p90:
            p90[cid] = p90[proxy]
    providers = list(budget.caps_usd)
    reserve = dict.fromkeys(providers, 0.0)
    for run in mandatory_cert_runs(p90):
        reserve[_provider(run, configs)] += run_cost_usd(run, p90)

    def projected(plan: Sequence[PlannedRun], provider: str) -> float:
        dev = sum(run_cost_usd(r, p90) for r in plan if _provider(r, configs) == provider)
        return spent.get(provider, 0.0) + dev + reserve[provider]

    plan = list(dev_plan)
    skipped: list[str] = []
    for name in DEV_SKIP_ORDER:
        candidate = next((r for r in plan if r.name == name), None)
        if candidate is None:
            continue
        provider = _provider(candidate, configs)
        if projected(plan, provider) > budget.limit(provider):
            plan.remove(candidate)
            skipped.append(name)

    runs: list[DevRun] = []
    for i, run in enumerate(plan):
        provider = _provider(run, configs)
        later = sum(run_cost_usd(r, p90) for r in plan[i + 1 :] if _provider(r, configs) == provider)
        ceiling = budget.limit(provider) - reserve[provider] - later
        runs.append(DevRun(run, provider, run_cost_usd(run, p90), ceiling))
    totals = {p: projected(plan, p) for p in providers}
    return DevGate(
        runs=tuple(runs),
        skipped=tuple(skipped),
        cert_reserve_usd=reserve,
        projected_usd=totals,
        fits={p: totals[p] <= budget.limit(p) for p in providers},
    )


# ---------------------------------------------------------------------------------------------------
# Cert plan (spec §9.1) and the pre-freeze projection (M4)

RUN_DECISION: dict[str, str] = {
    "luna-none": "D-A1",
    "luna-R": "D-A2",
    "haiku55-off": "D-B1",
    "haiku55-R": "D-B2",
    "jev-D": "D-J",
    "luna-none-x": "D-X",
}
CERT_DROP_ORDER: tuple[str, ...] = ("luna-R", "haiku55-R", "luna-none-x", "aa")
_VENDOR_PREFIX: dict[str, str] = {"openai": "luna", "anthropic": "haiku55"}
NOISE_FLOOR_WARNING = "aa not run: noise floor not measured"


@dataclass(frozen=True)
class ReasoningOutcome:
    """The §8.1 outcome for one vendor: the selected level R (None: E empty) and whether `low` in E."""

    selected: Level | None
    low_qualifies: bool


@dataclass(frozen=True)
class NotRun:
    decision: str
    reason: NotRunReason


@dataclass(frozen=True)
class CertPlan:
    runs: tuple[PlannedRun, ...]  # §9.1 order
    not_run: tuple[NotRun, ...]


def cert_plan(outcomes: Mapping[Vendor, ReasoningOutcome], jev_design: str) -> CertPlan:
    """Spec §9.1 `cert` order; `luna-R` / `haiku55-R` only where §8.1 certified a level."""
    runs: list[PlannedRun] = []
    not_run: list[NotRun] = []

    def reasoning_run(vendor: Vendor) -> None:
        name = f"{_VENDOR_PREFIX[vendor]}-R"
        level = outcomes[vendor].selected
        if level is None:
            not_run.append(NotRun(RUN_DECISION[name], "no dev gain"))
        else:
            runs.append(PlannedRun(name, f"{_VENDOR_PREFIX[vendor]}-{level}", "cert"))

    runs += [
        PlannedRun("inc", "inc", "cert"),
        PlannedRun("luna-none", "luna-none", "cert"),
        PlannedRun("aa", "inc", "aa"),
        PlannedRun("luna-none-x", "luna-none-x", "cert"),
    ]
    reasoning_run("openai")
    runs.append(PlannedRun("haiku55-off", "haiku55-off", "cert"))
    reasoning_run("anthropic")
    runs.append(PlannedRun("jev-D", jev_design, "cert"))
    return CertPlan(tuple(runs), tuple(not_run))


@dataclass(frozen=True)
class Substitution:
    run: str
    from_config: str
    to_config: str


@dataclass(frozen=True)
class FreezePlan:
    runs: tuple[PlannedRun, ...]  # the final `cert` plan written into the contract, §9.1 order
    substitutions: tuple[Substitution, ...]
    dropped: tuple[str, ...]  # run names dropped for budget, in drop order
    not_run: tuple[NotRun, ...]  # `no dev gain` from §8.1, then `budget`
    m5_blocked: tuple[str, ...]  # providers whose projection exceeds the limit even after every drop
    projected_usd: dict[str, float]  # spent + the final plan, per provider
    warnings: tuple[str, ...]


def freeze_projection(
    spent: Mapping[str, float],
    dev_p90: Mapping[str, float],
    outcomes: Mapping[Vendor, ReasoningOutcome],
    jev_design: str,
    configs: Mapping[str, Configuration],
    budget: BudgetConfig,
) -> FreezePlan:
    """Spec §9.5 projection before the freeze, per provider: substitute `medium` -> `low` when `low` in E,
    then drop `luna-R`, `haiku55-R`, `luna-none-x`, `aa` until spent + plan ≤ cap - margin.

    `dev_p90` is per-item p90 cost from each configuration's `dev` run (`luna-none-x`: the selected
    iteration). If a provider still does not fit, none of its runs start; without `inc` no decision
    can be made (every decision needs it), so every decision is then NOT RUN (`budget`).
    """
    base = cert_plan(outcomes, jev_design)
    runs = list(base.runs)
    substitutions: list[Substitution] = []
    dropped: list[str] = []
    blocked: list[str] = []

    def projected(provider: str) -> float:
        own = sum(run_cost_usd(r, dev_p90) for r in runs if _provider(r, configs) == provider)
        return spent.get(provider, 0.0) + own

    for provider in budget.caps_usd:
        limit = budget.limit(provider)
        if projected(provider) <= limit:
            continue
        for vendor, outcome in outcomes.items():
            name = f"{_VENDOR_PREFIX[vendor]}-R"
            idx = next((i for i, r in enumerate(runs) if r.name == name), None)
            if idx is None or _provider(runs[idx], configs) != provider:
                continue
            if outcome.selected == "medium" and outcome.low_qualifies:
                low = f"{_VENDOR_PREFIX[vendor]}-low"
                substitutions.append(Substitution(name, runs[idx].config_id, low))
                runs[idx] = replace(runs[idx], config_id=low)
        for name in CERT_DROP_ORDER:
            if projected(provider) <= limit:
                break
            run = next((r for r in runs if r.name == name and _provider(r, configs) == provider), None)
            if run is not None:
                runs.remove(run)
                dropped.append(name)
        if projected(provider) > limit:
            blocked.append(provider)
            dropped += [r.name for r in runs if _provider(r, configs) == provider]
            runs = [r for r in runs if _provider(r, configs) != provider]

    warnings: list[str] = []
    not_run = list(base.not_run)
    if not any(r.name == "inc" for r in runs):
        warnings.append("inc not affordable in cert: no decision can be made")
        dropped += [r.name for r in runs]
        runs = []
    planned = {r.name for r in runs}
    for run in base.runs:
        if run.name not in planned and run.name in RUN_DECISION:
            not_run.append(NotRun(RUN_DECISION[run.name], "budget"))
    for provider in blocked:
        warnings.append(f"{provider}: projection exceeds cap - margin after every drop; M5 does not start")
    if "aa" not in planned:
        warnings.append(NOISE_FLOOR_WARNING)
    return FreezePlan(
        runs=tuple(runs),
        substitutions=tuple(substitutions),
        dropped=tuple(dropped),
        not_run=tuple(not_run),
        m5_blocked=tuple(blocked),
        projected_usd={p: projected(p) for p in budget.caps_usd},
        warnings=tuple(warnings),
    )


# ---------------------------------------------------------------------------------------------------
# Cert execution (spec §9.5 in-run stop)


def cert_ceiling(provider: str, budget: BudgetConfig) -> float:
    """Every `cert` run of a provider stops at cap - margin."""
    return budget.limit(provider)


def next_cert_run(
    plan: Sequence[PlannedRun],
    configs: Mapping[str, Configuration],
    budget: BudgetConfig,
    spent: Mapping[str, float],
    finished: Collection[str],
    stopped: Collection[str],
) -> PlannedRun | None:
    """The next `cert` run to start, in plan order.

    `finished` are run names already run (complete or stopped); `stopped` are providers with an in-run
    stop. After a stop, or once a provider's spend reaches its ceiling, no later run of it starts.
    """
    for run in plan:
        if run.name in finished:
            continue
        provider = _provider(run, configs)
        if provider in stopped or not can_start(spent.get(provider, 0.0), cert_ceiling(provider, budget)):
            continue
        return run
    return None
