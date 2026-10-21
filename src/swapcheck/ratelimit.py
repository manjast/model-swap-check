"""Sliding-window rate limiting per provider (spec §9.4) and the per-request token estimate."""

from __future__ import annotations

import asyncio
from collections import deque
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from swapcheck.configs import Configuration
from swapcheck.groups import REPO_ROOT
from swapcheck.http import Clock
from swapcheck.prompt import Prompt

LIMITS_PATH = REPO_ROOT / "config" / "limits.yaml"
WINDOW_S = {"minute": 60.0, "second": 1.0}
_EXPIRY_MARGIN_S = 1e-6  # wait just past the window edge so float rounding cannot keep an entry alive


class Limit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    per: Literal["minute", "second"]
    requests: int
    tokens: int

    @property
    def window_s(self) -> float:
        return WINDOW_S[self.per]


class ProviderLimits(Limit):
    models: dict[str, Limit] = {}


def load_limits(path: Path = LIMITS_PATH) -> dict[str, ProviderLimits]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {provider: ProviderLimits(**fields) for provider, fields in raw.items()}


def limit_for(limits: dict[str, ProviderLimits], cfg: Configuration) -> Limit:
    """The model's own limit if listed, else the provider's."""
    provider = limits[cfg.provider]
    if cfg.model in provider.models:
        return provider.models[cfg.model]
    return Limit(per=provider.per, requests=provider.requests, tokens=provider.tokens)


class RateLimiter:
    """A request starts only if the requests and tokens started in the last window, plus its own, stay
    within the limit, so no window of the limit's length ever exceeds it. Waiters are served FIFO."""

    def __init__(self, limit: Limit, clock: Clock) -> None:
        self.limit = limit
        self._clock = clock
        self._starts: deque[tuple[float, int]] = deque()
        self._window_tokens = 0
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int) -> None:
        if tokens > self.limit.tokens:
            raise ValueError(f"a request of {tokens} tokens can never fit the limit of {self.limit.tokens}")
        async with self._lock:
            while True:
                now = self._clock.monotonic()
                self._expire(now)
                if len(self._starts) < self.limit.requests and self._window_tokens + tokens <= self.limit.tokens:
                    self._starts.append((now, tokens))
                    self._window_tokens += tokens
                    return
                await self._clock.sleep(self._wait_s(now, tokens))

    def _expire(self, now: float) -> None:
        while self._starts and now - self._starts[0][0] >= self.limit.window_s:
            _, k = self._starts.popleft()
            self._window_tokens -= k

    def _wait_s(self, now: float, tokens: int) -> float:
        """Time until enough of the oldest starts leave the window."""
        count, window_tokens = len(self._starts), self._window_tokens
        for started, k in self._starts:
            count -= 1
            window_tokens -= k
            if count < self.limit.requests and window_tokens + tokens <= self.limit.tokens:
                return started + self.limit.window_s - now + _EXPIRY_MARGIN_S
        raise AssertionError("unreachable: an empty window admits any request within the limit")


class TokenEstimator:
    """Per-request token estimate: o200k_base tokens of the developer message and the text, plus max
    output tokens for OpenAI, whose rate limiter counts them (spec §9.4)."""

    def __init__(self, cfg: Configuration, prompt: Prompt) -> None:
        import tiktoken

        self._encoding = tiktoken.get_encoding("o200k_base")
        self._fixed = len(self._encoding.encode(prompt.developer_message()))
        if cfg.provider == "openai":
            self._fixed += cfg.max_output_tokens or 0

    def __call__(self, text: str) -> int:
        return self._fixed + len(self._encoding.encode(text))
