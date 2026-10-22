"""T-R6, T-R11: budget gate, ceilings, pre-freeze projection, cert order and drop order (spec §8.1, §9.1, §9.5).

Projected run cost = split items x per-item p90 (dev 3,075; cert 9,758; aa 3,080). Limits are cap - 0.50:
OpenAI 14.50, Anthropic 9.50, TypeSafe 4.50.
"""

from __future__ import annotations

import pytest

from swapcheck import budget
from swapcheck.budget import NotRun, PlannedRun, ReasoningOutcome, Substitution, Vendor
from swapcheck.configs import load_configurations

CONFIGS = load_configurations()
BUDGET = budget.load_budget()

PILOT_P90 = {
    "inc": 0.0002,
    "luna-none": 0.0001,  # also prices the three D-X iterations
    "luna-low": 0.0003,
    "luna-medium": 0.0008,
    "luna-dec": 0.0003,
    "haiku55-off": 0.0001,
    "haiku55-low": 0.0004,
    "haiku55-medium": 0.0009,
    "jev-c51": 0.00007,
    "jev-noul": 0.00008,
}
# Mandatory cert reserve: OpenAI inc 1.9516 + luna-none 0.9758 + aa 0.616 = 3.5434; Anthropic 0.9758;
# TypeSafe jev-noul (the dearer design) 0.78064. `luna-dec` is not part of it (dropped before `aa`, §9.5).
OPENAI_RESERVE = 3.5434
# OpenAI dev: inc 0.615, luna-dec 0.9225, luna-none 0.3075, luna-low 0.9225, D-X 3 x 0.3075, luna-medium 2.46.
OPENAI_DEV = 6.15


def test_r6_budget_file_caps() -> None:
    assert BUDGET.limit("openai") == 14.5
    assert BUDGET.limit("anthropic") == 9.5
    assert BUDGET.limit("typesafe") == 4.5


def test_r6_pre_dev_gate_skips_medium_then_low() -> None:
    # OpenAI: 6.0 + dev 6.15 + reserve 3.5434 = 15.6934 > 14.5 -> skip luna-medium (-2.46) -> 13.2334 fits.
    # Anthropic: 7.5 + 0.3075 + 1.23 + 2.7675 + 0.9758 = 12.7808 -> skip medium -> 10.0133 -> skip low -> 8.7833.
    spent = {"openai": 6.0, "anthropic": 7.5, "typesafe": 0.1}
    gate = budget.pre_dev_gate(spent, PILOT_P90, CONFIGS, BUDGET)
    assert gate.skipped == ("luna-medium", "haiku55-medium", "haiku55-low")
    assert [r.run.name for r in gate.runs] == [
        "inc", "jev-c51", "jev-noul", "luna-dec", "luna-none", "haiku55-off", "luna-low",
        "luna-none-x-1", "luna-none-x-2", "luna-none-x-3",
    ]  # fmt: skip
    assert gate.cert_reserve_usd["openai"] == pytest.approx(OPENAI_RESERVE)
    assert gate.cert_reserve_usd["typesafe"] == pytest.approx(9758 * 0.00008)
    assert gate.projected_usd["openai"] == pytest.approx(6.0 + OPENAI_DEV - 2.46 + OPENAI_RESERVE)
    assert gate.projected_usd["anthropic"] == pytest.approx(8.7833)
    assert gate.fits == {"openai": True, "anthropic": True, "typesafe": True}


def test_r6_pre_dev_gate_keeps_everything_that_fits_and_flags_what_cannot() -> None:
    gate = budget.pre_dev_gate({"openai": 0.0, "anthropic": 0.0, "typesafe": 4.0}, PILOT_P90, CONFIGS, BUDGET)
    assert gate.skipped == ()
    assert len(gate.runs) == len(budget.DEV_PLAN)
    assert gate.fits["typesafe"] is False  # Jev dev runs are never skipped; the plan reports the overrun


def test_r6_dev_run_stops_at_its_ceiling_without_blocking_later_runs() -> None:
    gate = budget.pre_dev_gate({"openai": 6.0, "anthropic": 0.0, "typesafe": 0.0}, PILOT_P90, CONFIGS, BUDGET)
    openai = [r for r in gate.runs if r.provider == "openai"]
    by_name = {r.run.name: r for r in openai}
    # ceiling = 14.5 - reserve - later planned OpenAI dev runs (three D-X iterations after luna-low)
    assert by_name["luna-low"].ceiling_usd == pytest.approx(14.5 - OPENAI_RESERVE - 3 * 0.3075)
    assert by_name["luna-none-x-3"].ceiling_usd == pytest.approx(14.5 - OPENAI_RESERVE)

    spent = 6.0
    for run in openai:
        assert budget.can_start(spent, run.ceiling_usd), run.run.name
        if run.run.name == "luna-low":
            spent = run.ceiling_usd  # overruns its projection; the runner stops it at its ceiling
        else:
            spent += run.projected_usd
            assert spent <= run.ceiling_usd + 1e-9  # a run within its projection completes
    assert spent + OPENAI_RESERVE <= BUDGET.limit("openai") + 1e-9  # the mandatory cert reserve is intact


def test_r6_run_not_affordable_does_not_start() -> None:
    assert not budget.can_start(5.0, 5.0)
    assert budget.can_start(4.99, 5.0)


OPENAI_MEDIUM_LOW_IN_E: dict[Vendor, ReasoningOutcome] = {
    "openai": ReasoningOutcome(selected="medium", low_qualifies=True),
    "anthropic": ReasoningOutcome(selected="medium", low_qualifies=False),
}
DEV_P90 = {
    "inc": 0.0002,
    "luna-none": 0.0001,
    "luna-none-x": 0.0001,
    "luna-low": 0.0003,
    "luna-medium": 0.0008,
    "luna-dec": 0.0003,
    "haiku55-off": 0.0001,
    "haiku55-medium": 0.0009,
    "jev-noul": 0.00008,
}
# OpenAI cert: inc 1.9516, luna-none 0.9758, aa 0.616, luna-dec 2.9274, luna-none-x 0.9758, luna-medium 7.8064,
# luna-low 2.9274 (plan with medium 15.253, with low 10.374). Anthropic cert: haiku55-off 0.9758,
# haiku55-medium 8.7822. TypeSafe: jev-noul 0.78064.


def test_r11_cert_order_and_no_dev_gain() -> None:
    plan = budget.cert_plan(OPENAI_MEDIUM_LOW_IN_E, "jev-noul")
    assert [(r.name, r.config_id, r.split) for r in plan.runs] == [
        ("inc", "inc", "cert"),
        ("luna-none", "luna-none", "cert"),
        ("aa", "inc", "aa"),
        ("luna-dec", "luna-dec", "cert"),
        ("luna-none-x", "luna-none-x", "cert"),
        ("luna-R", "luna-medium", "cert"),
        ("haiku55-off", "haiku55-off", "cert"),
        ("haiku55-R", "haiku55-medium", "cert"),
        ("jev-D", "jev-noul", "cert"),
    ]
    assert plan.not_run == ()

    none: dict[Vendor, ReasoningOutcome] = {
        "openai": ReasoningOutcome(selected=None, low_qualifies=False),
        "anthropic": ReasoningOutcome(selected="low", low_qualifies=True),
    }
    plan = budget.cert_plan(none, "jev-c51")
    names = [r.name for r in plan.runs]
    assert "luna-R" not in names
    assert ("haiku55-R", "haiku55-low") in [(r.name, r.config_id) for r in plan.runs]
    assert plan.not_run == (NotRun("D-A2", "no dev gain"),)


def test_r6_r11_projection_substitutes_low_before_dropping() -> None:
    # OpenAI: 1.0 + 15.253 = 16.253 > 14.5; luna-medium -> luna-low gives 11.374 and fits, so nothing
    # OpenAI is dropped.
    # Anthropic: 0.5 + 0.9758 + 8.7822 = 10.258 > 9.5, low not in E -> haiku55-R dropped -> 1.4758.
    spent = {"openai": 1.0, "anthropic": 0.5, "typesafe": 0.0}
    fp = budget.freeze_projection(spent, DEV_P90, OPENAI_MEDIUM_LOW_IN_E, "jev-noul", CONFIGS, BUDGET)
    assert fp.substitutions == (Substitution("luna-R", "luna-medium", "luna-low"),)
    assert ("luna-R", "luna-low") in [(r.name, r.config_id) for r in fp.runs]
    assert fp.dropped == ("haiku55-R",)
    assert fp.not_run == (NotRun("D-B2", "budget"),)
    assert fp.projected_usd["openai"] == pytest.approx(11.374)
    assert fp.projected_usd["anthropic"] == pytest.approx(1.4758)
    assert fp.warnings == ()


def test_r6_r11_projection_drop_order_and_noise_floor_warning() -> None:
    # OpenAI 11.0: after substitution 21.374 -> drop luna-R 18.4466 -> drop luna-none-x 17.4708
    # -> drop luna-dec 14.5434 -> drop aa 13.9274.
    # Anthropic (separate cap): 0.9758 + 8.7822 = 9.758 > 9.5, low not in E -> haiku55-R dropped.
    spent = {"openai": 11.0, "anthropic": 0.0, "typesafe": 0.0}
    outcomes = OPENAI_MEDIUM_LOW_IN_E
    fp = budget.freeze_projection(spent, DEV_P90, outcomes, "jev-noul", CONFIGS, BUDGET)
    assert fp.dropped == ("luna-R", "luna-none-x", "luna-dec", "aa", "haiku55-R")
    assert [r.name for r in fp.runs] == ["inc", "luna-none", "haiku55-off", "jev-D"]
    assert fp.not_run == (
        NotRun("D-O", "budget"),
        NotRun("D-X", "budget"),
        NotRun("D-A2", "budget"),
        NotRun("D-B2", "budget"),
    )
    assert fp.warnings == (budget.NOISE_FLOOR_WARNING,)
    assert fp.m5_blocked == ()

    # Just enough to keep aa: 10.9 + 3.5434 = 14.4434 fits after dropping luna-dec.
    fp = budget.freeze_projection({**spent, "openai": 10.9}, DEV_P90, outcomes, "jev-noul", CONFIGS, BUDGET)
    assert fp.dropped == ("luna-R", "luna-none-x", "luna-dec", "haiku55-R")
    assert budget.NOISE_FLOOR_WARNING not in fp.warnings

    # luna-dec is dropped after luna-none-x: 7.5 + 7.4466 = 14.9466 -> drop luna-none-x 13.9708 fits.
    fp = budget.freeze_projection({**spent, "openai": 7.5}, DEV_P90, outcomes, "jev-noul", CONFIGS, BUDGET)
    assert fp.dropped == ("luna-R", "luna-none-x", "haiku55-R")
    assert "luna-dec" in [r.name for r in fp.runs]


def test_r11_provider_that_never_fits_does_not_start_m5() -> None:
    # TypeSafe: 4.0 + 0.78064 > 4.5 with nothing droppable -> no Jev cert run, D-J NOT RUN (budget).
    spent = {"openai": 0.0, "anthropic": 0.0, "typesafe": 4.0}
    fp = budget.freeze_projection(spent, DEV_P90, OPENAI_MEDIUM_LOW_IN_E, "jev-noul", CONFIGS, BUDGET)
    assert fp.m5_blocked == ("typesafe",)
    assert "jev-D" not in [r.name for r in fp.runs]
    assert NotRun("D-J", "budget") in fp.not_run
    assert "inc" in [r.name for r in fp.runs]

    # OpenAI: 12.0 + inc + luna-none = 14.9274 > 14.5 even after every drop. Without inc no decision can be made.
    fp = budget.freeze_projection(
        {**spent, "openai": 12.0}, DEV_P90, OPENAI_MEDIUM_LOW_IN_E, "jev-noul", CONFIGS, BUDGET
    )
    assert "openai" in fp.m5_blocked
    assert fp.runs == ()
    assert {n.decision for n in fp.not_run} == {"D-A1", "D-A2", "D-X", "D-O", "D-B1", "D-B2", "D-J"}
    assert all(n.reason == "budget" for n in fp.not_run)


def test_r6_r11_cert_ceiling_and_no_start_after_in_run_stop() -> None:
    plan = budget.cert_plan(OPENAI_MEDIUM_LOW_IN_E, "jev-noul").runs
    assert budget.cert_ceiling("openai", BUDGET) == 14.5
    assert budget.cert_ceiling("typesafe", BUDGET) == 4.5
    spent = {"openai": 3.0, "anthropic": 0.0, "typesafe": 0.0}

    def nxt(finished: set[str], stopped: set[str], spent: dict[str, float] = spent) -> PlannedRun | None:
        return budget.next_cert_run(plan, CONFIGS, BUDGET, spent, finished, stopped)

    assert (r := nxt(set(), set())) is not None and r.name == "inc"
    assert (r := nxt({"inc", "luna-none"}, set())) is not None and r.name == "aa"
    assert (r := nxt({"inc", "luna-none", "aa"}, set())) is not None and r.name == "luna-dec"
    # luna-none stopped at cap - 0.50: aa, luna-dec, luna-none-x and luna-R never start; Anthropic goes on.
    assert (r := nxt({"inc", "luna-none"}, {"openai"})) is not None and r.name == "haiku55-off"
    # spend already at the ceiling: no OpenAI run starts even without a recorded stop
    assert (r := nxt(set(), set(), {**spent, "openai": 14.5})) is not None and r.name == "haiku55-off"
    assert nxt({r.name for r in plan}, set()) is None
