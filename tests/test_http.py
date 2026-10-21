"""T-R3: retry policy with a fake transport (spec §9.2, §10)."""

from __future__ import annotations

import asyncio
import email.utils
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fakes import FAKE_URL, FakeClock, UpperRandom, make_sender, ok_body, timeout_usage

from swapcheck.http import AttemptBudget, Sender, SendResult
from swapcheck.providers.base import HttpRequest
from swapcheck.records import Attempt, Parsed, Usage

CFG_USAGE = Usage(uncached_input=100, cache_read=1000, output=10)


def scripted(responses: list[Any], clock: FakeClock, latency_s: float = 0.0) -> tuple[Sender, UpperRandom]:
    """A sender whose transport plays `responses` in order: an `httpx.Response` or an exception to raise."""
    queue = list(responses)

    async def handler(request: httpx.Request) -> httpx.Response:
        clock.t += latency_s
        step = queue.pop(0)
        if isinstance(step, Exception):
            raise step
        assert isinstance(step, httpx.Response)
        return step

    rng = UpperRandom()
    return make_sender(handler, clock, rng), rng


def send(sender: Sender, budget: AttemptBudget | None = None) -> SendResult:
    def parse(body: Any) -> Parsed:
        return Parsed(
            status="ok",
            raw_output=body["output"],
            intent=body["intent"],
            confidence=body["confidence"],
            model_id=body["model"],
            usage=Usage(**body["usage"]),
        )

    async def go() -> SendResult:
        async with sender.client:
            request = HttpRequest("POST", FAKE_URL, {}, {"text": "hi"})
            return await sender.send(
                request, tokens=10, parse=parse, timeout_usage=lambda: timeout_usage("hi"), budget=budget
            )

    return asyncio.run(go())


def ok() -> httpx.Response:
    return httpx.Response(200, json=ok_body(), headers={"x-request-id": "req-ok"})


@pytest.mark.parametrize("status", [408, 409, 429, 500, 502, 503, 504, 529])
def test_r3_retryable_status_is_retried(status: int) -> None:
    clock = FakeClock()
    sender, _ = scripted([httpx.Response(status, json={"error": {"type": "x"}}), ok()], clock)
    result = send(sender)
    assert result.error_code is None and result.parsed is not None
    assert [(a.http_status, a.error) for a in result.attempts] == [(status, f"http_{status}"), (200, None)]
    assert clock.sleeps == [1.0]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_r3_non_retryable_status_fails_at_once(status: int) -> None:
    clock = FakeClock()
    sender, _ = scripted([httpx.Response(status, json={"error": {"message": "bad"}}), ok()], clock)
    result = send(sender)
    assert result.parsed is None
    assert result.error_code == f"http_{status}"
    assert len(result.attempts) == 1 and clock.sleeps == []
    assert result.error_body is not None and "bad" in result.error_body


def test_r3_six_attempts_with_exponential_full_jitter() -> None:
    clock = FakeClock()
    sender, rng = scripted([httpx.Response(503) for _ in range(7)], clock)
    result = send(sender)
    assert result.error_code == "http_503"
    assert [a.number for a in result.attempts] == [1, 2, 3, 4, 5, 6]
    assert rng.ranges == [(0.0, 1.0), (0.0, 2.0), (0.0, 4.0), (0.0, 8.0), (0.0, 16.0)]  # full jitter over the cap
    assert clock.sleeps == [1.0, 2.0, 4.0, 8.0, 16.0]


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"retry-after": "7"}, 7.0),
        ({"retry-after-ms": "2500", "retry-after": "1"}, 2.5),  # milliseconds win over seconds
        ({"retry-after": "0.2"}, 1.0),  # shorter than the backoff: the backoff wins
        ({}, 1.0),
    ],
)
def test_r3_retry_after_honoured_when_longer(headers: dict[str, str], expected: float) -> None:
    clock = FakeClock()
    sender, _ = scripted([httpx.Response(429, headers=headers), ok()], clock)
    result = send(sender)
    assert clock.sleeps == [expected]
    assert result.parsed is not None


def test_r3_retry_after_http_date() -> None:
    clock = FakeClock()
    date = email.utils.format_datetime(clock.now() + timedelta(seconds=30), usegmt=True)
    sender, _ = scripted([httpx.Response(503, headers={"retry-after": date}), ok()], clock)
    result = send(sender)
    assert clock.sleeps == [30.0]
    assert result.attempts[0].retry_after_s == 30.0


@pytest.mark.parametrize(
    "body",
    [
        {"error": {"type": "insufficient_quota", "code": "insufficient_quota", "message": "quota"}},
        {"error": {"type": "rate_limit_error", "code": "organization_spend_limit_exceeded"}},
        {"error": {"type": "rate_limit_error", "code": "credit_balance_exhausted"}},
        {
            "type": "error",
            "error": {"type": "rate_limit_error", "details": {"error_code": "enforced_spend_limit_reached"}},
        },
    ],
)
def test_r3_quota_429_is_not_retried(body: dict[str, Any]) -> None:
    clock = FakeClock()
    sender, _ = scripted([httpx.Response(429, json=body), ok()], clock)
    result = send(sender)
    assert result.error_code == "quota"
    assert len(result.attempts) == 1 and clock.sleeps == []


def test_r3_rate_limit_429_is_retried() -> None:
    clock = FakeClock()
    body = {"error": {"type": "requests", "code": "rate_limit_exceeded"}}
    sender, _ = scripted([httpx.Response(429, json=body), ok()], clock)
    assert send(sender).parsed is not None


def test_r3_every_attempt_keeps_usage_latency_and_request_id() -> None:
    clock = FakeClock()
    sender, _ = scripted(
        [
            httpx.ReadTimeout("slow"),
            httpx.ConnectError("refused"),
            httpx.Response(500, headers={"x-request-id": "req-500"}),
            ok(),
        ],
        clock,
        latency_s=0.25,
    )
    result = send(sender)
    timeout, connection, server, final = result.attempts
    assert (timeout.error, timeout.usage, timeout.usage_estimated) == ("timeout", timeout_usage("hi"), True)
    assert (connection.error, connection.usage, connection.usage_estimated) == ("connection", Usage(), False)
    assert (server.error, server.request_id, server.usage) == ("http_500", "req-500", Usage())
    assert (final.error, final.request_id, final.usage) == (None, "req-ok", CFG_USAGE)
    assert [a.latency_ms for a in result.attempts] == [250.0, 250.0, 250.0, 250.0]


def test_r3_timeouts_exhaust_into_timeout_error() -> None:
    clock = FakeClock()
    sender, _ = scripted([httpx.ReadTimeout("slow") for _ in range(6)], clock)
    result = send(sender)
    assert result.error_code == "timeout"
    assert all(a.usage_estimated and a.usage == timeout_usage("hi") for a in result.attempts)
    assert len(result.attempts) == 6


class Allowance:
    """Admits `allowed` attempts, logging every admission and charge in order."""

    def __init__(self, allowed: int) -> None:
        self.allowed = allowed
        self.log: list[str] = []

    async def admit(self) -> bool:
        admitted = self.allowed > 0
        self.allowed -= 1
        self.log.append("admit" if admitted else "refuse")
        return admitted

    def charge(self, attempt: Attempt) -> None:
        self.log.append(f"charge {attempt.number} {attempt.error}")


def test_r3_every_attempt_is_admitted_before_it_starts_and_charged_when_it_ends() -> None:
    clock = FakeClock()
    sender, _ = scripted([httpx.ReadTimeout("slow") for _ in range(6)], clock)
    allowance = Allowance(2)
    result = send(sender, allowance)
    assert result.error_code == "budget" and result.parsed is None
    assert [a.error for a in result.attempts] == ["timeout", "timeout"]
    assert allowance.log == ["admit", "charge 1 timeout", "admit", "charge 2 timeout", "refuse"]


def test_r3_a_successful_attempt_is_charged_once() -> None:
    allowance = Allowance(6)
    sender, _ = scripted([httpx.Response(503), ok()], FakeClock())
    assert send(sender, allowance).parsed is not None
    assert allowance.log == ["admit", "charge 1 http_503", "admit", "charge 2 None"]
