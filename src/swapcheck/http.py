"""Sending one request with the retry policy of spec §9.2. Every HTTP attempt becomes an `Attempt`."""

from __future__ import annotations

import asyncio
import email.utils
import json
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

import httpx

from swapcheck.providers.base import HttpRequest, ProviderAdapter
from swapcheck.records import Attempt, Parsed, Usage

if TYPE_CHECKING:
    from swapcheck.ratelimit import RateLimiter

RETRYABLE_STATUSES = frozenset({408, 409, 429, 500, 502, 503, 504, 529})
# A 429 with one of these in its body is a spent quota or spend cap: retrying cannot fix it (spec §9.2).
QUOTA_ERROR_TYPES = frozenset({"insufficient_quota"})  # OpenAI `error.type`
QUOTA_ERROR_CODES = frozenset(
    {
        "insufficient_quota",
        "credit_balance_exhausted",
        "organization_spend_limit_exceeded",
        "project_spend_limit_exceeded",
        "organization_usage_limit_exceeded",
        "enforced_spend_limit_reached",  # Anthropic spend cap, in `error.details.error_code`
    }
)
ERROR_BODY_CHARS = 2_000


class Clock(Protocol):
    def monotonic(self) -> float: ...

    def now(self) -> datetime:
        """Current UTC wall-clock time (run timestamps, HTTP-date `retry-after`)."""
        ...

    async def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def now(self) -> datetime:
        return datetime.now(UTC)

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


@dataclass(frozen=True)
class RetryPolicy:
    """Spec §9.2: exponential backoff from 1 s, doubling, full jitter, at most 6 attempts, 60 s timeout."""

    max_attempts: int = 6
    base_s: float = 1.0
    factor: float = 2.0
    timeout_s: float = 60.0
    retryable: frozenset[int] = RETRYABLE_STATUSES


@dataclass(frozen=True)
class SendResult:
    attempts: list[Attempt]
    parsed: Parsed | None  # set when the final attempt was a 2xx with a JSON body
    error_code: str | None  # None on success; else `http_<status>`, `timeout`, `connection`, `quota`, `bad_body`,
    # or `budget` (an attempt the spend budget refused)
    error_body: str | None  # body of a final error response, capped at 2,000 chars

    @property
    def final(self) -> Attempt:
        """The last attempt; a result has none only when the budget refused its first attempt."""
        return self.attempts[-1]


def retry_after_s(headers: Mapping[str, str], now: datetime) -> float | None:
    """`retry-after-ms`, else `retry-after` in seconds or as an HTTP date; None when absent or unreadable."""
    ms = headers.get("retry-after-ms")
    if ms is not None:
        try:
            return max(float(ms) / 1000.0, 0.0)
        except ValueError:
            pass
    value = headers.get("retry-after")
    if value is None:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max((when - now).total_seconds(), 0.0)


def is_quota_error(body: Any) -> bool:
    """True when a 429 body reports an exhausted quota or spend limit (OpenAI and Anthropic shapes)."""
    if not isinstance(body, Mapping):
        return False
    error = body.get("error")
    if not isinstance(error, Mapping):
        return False
    if error.get("type") in QUOTA_ERROR_TYPES or error.get("code") in QUOTA_ERROR_CODES:
        return True
    details = error.get("details")
    return isinstance(details, Mapping) and details.get("error_code") in QUOTA_ERROR_CODES


class AttemptBudget(Protocol):
    """Spend admission per HTTP attempt (spec §9.5), retries included."""

    async def admit(self) -> bool:
        """Reserve the worst-case cost of one more attempt; False means it must not start."""
        ...

    def charge(self, attempt: Attempt) -> None:
        """Release that reservation and charge the completed attempt."""
        ...


@dataclass
class Sender:
    """Sends requests for one provider: auth, rate limit per attempt, timeouts and retries."""

    client: httpx.AsyncClient
    adapter: ProviderAdapter
    api_key: str
    limiter: RateLimiter | None = None
    clock: Clock = field(default_factory=SystemClock)
    rng: random.Random = field(default_factory=random.Random)
    policy: RetryPolicy = field(default_factory=RetryPolicy)

    def backoff_s(self, attempt_number: int, retry_after: float | None) -> float:
        """Full jitter over the capped exponential; a longer `retry-after` wins."""
        cap = self.policy.base_s * self.policy.factor ** (attempt_number - 1)
        delay = self.rng.uniform(0.0, cap)
        return max(delay, retry_after) if retry_after is not None else delay

    async def send(
        self,
        request: HttpRequest,
        *,
        tokens: int,
        parse: Callable[[Mapping[str, Any]], Parsed],
        timeout_usage: Callable[[], Usage],
        budget: AttemptBudget | None = None,
    ) -> SendResult:
        """Send with retries. `tokens` is the rate-limit estimate charged per attempt; `timeout_usage`
        is the charge recorded for a timed-out attempt (spec §9.5). With a `budget`, every attempt must
        be admitted before it starts and is charged when it ends; a refused attempt ends the request
        with error code `budget`."""
        attempts: list[Attempt] = []

        def record(attempt: Attempt) -> None:
            attempts.append(attempt)
            if budget is not None:
                budget.charge(attempt)

        headers = {**request.headers, **self.adapter.auth_headers(self.api_key)}
        for number in range(1, self.policy.max_attempts + 1):
            if budget is not None and not await budget.admit():
                return SendResult(attempts, None, "budget", None)
            if self.limiter is not None:
                await self.limiter.acquire(tokens)
            http_request = self.client.build_request(
                request.method, request.url, headers=headers, json=request.body, timeout=self.policy.timeout_s
            )
            start = self.clock.monotonic()
            try:
                async with asyncio.timeout(self.policy.timeout_s):
                    response = await self.client.send(http_request)
            except (TimeoutError, httpx.TimeoutException):
                latency = (self.clock.monotonic() - start) * 1000.0
                record(
                    Attempt(
                        number=number,
                        http_status=None,
                        error="timeout",
                        usage=timeout_usage(),
                        usage_estimated=True,
                        latency_ms=latency,
                    )
                )
                if number < self.policy.max_attempts:
                    await self.clock.sleep(self.backoff_s(number, None))
                    continue
                return SendResult(attempts, None, "timeout", None)
            except httpx.TransportError:
                latency = (self.clock.monotonic() - start) * 1000.0
                record(Attempt(number=number, http_status=None, error="connection", latency_ms=latency))
                if number < self.policy.max_attempts:
                    await self.clock.sleep(self.backoff_s(number, None))
                    continue
                return SendResult(attempts, None, "connection", None)

            latency = (self.clock.monotonic() - start) * 1000.0
            status = response.status_code
            request_id = self.adapter.request_id(response.headers)
            body: Any
            try:
                body = response.json()
            except ValueError:
                body = None

            if 200 <= status < 300:
                if not isinstance(body, Mapping):
                    record(
                        Attempt(
                            number=number,
                            http_status=status,
                            error="bad_body",
                            latency_ms=latency,
                            request_id=request_id,
                        )
                    )
                    return SendResult(attempts, None, "bad_body", response.text[:ERROR_BODY_CHARS])
                parsed = parse(body)
                record(
                    Attempt(
                        number=number,
                        http_status=status,
                        usage=parsed.usage,
                        latency_ms=latency,
                        request_id=request_id,
                    )
                )
                return SendResult(attempts, parsed, None, None)

            wait = retry_after_s(response.headers, self.clock.now())
            quota = status == 429 and is_quota_error(body)
            error = "quota" if quota else f"http_{status}"
            record(
                Attempt(
                    number=number,
                    http_status=status,
                    error=error,
                    latency_ms=latency,
                    request_id=request_id,
                    retry_after_s=wait,
                )
            )
            if quota or status not in self.policy.retryable or number == self.policy.max_attempts:
                return SendResult(attempts, None, error, _error_text(body, response.text))
            await self.clock.sleep(self.backoff_s(number, wait))
        raise AssertionError("unreachable: the loop returns on its last attempt")


def _error_text(body: Any, text: str) -> str:
    raw = json.dumps(body, ensure_ascii=False) if body is not None else text
    return raw[:ERROR_BODY_CHARS]
