"""T-R6 (spend guard): the reservation held for an attempt in flight is its worst-case cost (spec §9.5)."""

from __future__ import annotations

import pytest

from swapcheck.configs import load_configurations
from swapcheck.cost import attempt_cost_usd, load_prices, reservation_usd
from swapcheck.records import Usage

CONFIGS = load_configurations()
PRICES = load_prices()
INPUT = 3_000


def outcomes(output: int) -> list[Usage]:
    """Every way one attempt can bill `INPUT` input tokens and at most `output` output tokens."""
    return [
        Usage(uncached_input=INPUT, output=output),  # cache miss, nothing written; also the timeout charge
        Usage(cache_write=INPUT, output=output),  # cache miss that writes the whole input
        Usage(uncached_input=1_000, cache_write=INPUT - 1_000, output=output),
        Usage(cache_read=INPUT - 1_000, uncached_input=1_000, output=output),
    ]


@pytest.mark.parametrize("config_id", ["inc", "luna-none", "luna-medium", "haiku55-off", "jev-c51"])
def test_r6_reservation_is_the_dearest_outcome_of_one_attempt(config_id: str) -> None:
    cfg = CONFIGS[config_id]
    output = cfg.max_output_tokens if cfg.is_llm and cfg.max_output_tokens is not None else 0
    timeout_charge = Usage(uncached_input=INPUT, output=output)
    reserved = reservation_usd(PRICES, cfg, timeout_charge)
    costs = [attempt_cost_usd(PRICES, cfg, u) for u in outcomes(output)]
    assert all(c <= reserved + 1e-15 for c in costs)
    assert max(costs) == pytest.approx(reserved)


@pytest.mark.parametrize("config_id", ["luna-none", "haiku55-off"])
def test_r6_reservation_exceeds_the_timeout_charge_where_cache_writes_cost_more(config_id: str) -> None:
    cfg = CONFIGS[config_id]
    assert cfg.max_output_tokens is not None
    timeout_charge = Usage(uncached_input=INPUT, output=cfg.max_output_tokens)
    cache_writing = Usage(cache_write=INPUT, output=cfg.max_output_tokens)
    assert attempt_cost_usd(PRICES, cfg, cache_writing) > attempt_cost_usd(PRICES, cfg, timeout_charge)
    assert reservation_usd(PRICES, cfg, timeout_charge) == pytest.approx(attempt_cost_usd(PRICES, cfg, cache_writing))
