"""T-R4 (limiter part): sliding windows per minute and per second; token estimate (spec §9.4)."""

from __future__ import annotations

import asyncio
import math

import pytest
from fakes import FakeClock, max_in_any_window

from swapcheck.configs import load_configurations
from swapcheck.prompt import Prompt
from swapcheck.ratelimit import Limit, RateLimiter, TokenEstimator, limit_for, load_limits


def acquire_all(limit: Limit, tokens: list[int]) -> list[tuple[float, int]]:
    clock = FakeClock()
    limiter = RateLimiter(limit, clock)
    starts: list[tuple[float, int]] = []

    async def one(k: int) -> None:
        await limiter.acquire(k)
        starts.append((clock.monotonic(), k))

    async def go() -> None:
        await asyncio.gather(*(one(k) for k in tokens))

    asyncio.run(go())
    return starts


@pytest.mark.parametrize(
    ("limit", "tokens", "per_window"),
    [
        (Limit(per="second", requests=5, tokens=20_000), [1_000] * 23, 5),  # TypeSafe: requests bind
        (Limit(per="second", requests=5, tokens=20_000), [6_000] * 23, 3),  # tokens bind
        (Limit(per="minute", requests=10, tokens=400_000), [2_000] * 23, 10),
        (Limit(per="minute", requests=400, tokens=10_000), [2_500] * 23, 4),
    ],
)
def test_r4_no_window_exceeds_the_limit(limit: Limit, tokens: list[int], per_window: int) -> None:
    starts = acquire_all(limit, tokens)
    assert len(starts) == len(tokens)
    worst_requests, worst_tokens = max_in_any_window(starts, limit.window_s)
    assert worst_requests <= limit.requests and worst_tokens <= limit.tokens
    # and the limiter is not slower than the limit requires: full windows back to back
    span = starts[-1][0] - starts[0][0]
    full_windows = math.ceil(len(tokens) / per_window) - 1
    assert full_windows * limit.window_s <= span < full_windows * limit.window_s + 0.01


def test_r4_mixed_token_sizes_respect_the_token_limit() -> None:
    limit = Limit(per="second", requests=100, tokens=10_000)
    starts = acquire_all(limit, [9_000, 500, 2_000, 7_000, 3_000, 10_000, 1, 9_999] * 3)
    _, worst_tokens = max_in_any_window(starts, 1.0)
    assert worst_tokens <= 10_000


def test_r4_request_larger_than_the_token_limit_is_refused() -> None:
    limiter = RateLimiter(Limit(per="second", requests=5, tokens=1_000), FakeClock())
    with pytest.raises(ValueError, match="never fit"):
        asyncio.run(limiter.acquire(1_001))


def test_r4_limits_file_has_explicit_units() -> None:
    limits = load_limits()
    configs = load_configurations()
    assert limit_for(limits, configs["inc"]).per == "minute"
    assert limit_for(limits, configs["haiku55-off"]).per == "minute"
    assert limit_for(limits, configs["jev-c51"]).per == "second"


def test_r4_token_estimate_counts_max_output_for_openai_only(incumbent: Prompt) -> None:
    configs = load_configurations()
    openai, anthropic = configs["luna-none"], configs["haiku55-off"]
    assert openai.max_output_tokens == anthropic.max_output_tokens == 200
    text = "I still have not received my new card"
    openai_estimate = TokenEstimator(openai, incumbent)(text)
    anthropic_estimate = TokenEstimator(anthropic, incumbent)(text)
    assert openai_estimate - anthropic_estimate == 200
    assert anthropic_estimate > TokenEstimator(anthropic, incumbent)("") > 1_100  # prefix + text
