"""Offline fakes for runner tests: a provider adapter, a virtual clock, scripted transports, git repos."""

from __future__ import annotations

import asyncio
import json
import random
import subprocess
from collections.abc import Callable, Coroutine, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from swapcheck import runner
from swapcheck.configs import Configuration
from swapcheck.data import Item
from swapcheck.http import Sender
from swapcheck.prompt import Prompt
from swapcheck.providers.base import HttpRequest
from swapcheck.ratelimit import RateLimiter
from swapcheck.records import Parsed, RunMeta, Split, Usage
from swapcheck.runner import RunBudget

FAKE_URL = "https://fake.invalid/v1/respond"
START = datetime(2026, 10, 21, 12, 0, 0, tzinfo=UTC)
Handler = Callable[[httpx.Request], Coroutine[Any, Any, httpx.Response]]


class FakeClock:
    """Virtual time: `sleep` advances the clock at once and never yields, so no other task observes a
    half-finished wait."""

    def __init__(self) -> None:
        self.t = 1_000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.t

    def now(self) -> datetime:
        return START + timedelta(seconds=self.t - 1_000.0)

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


class UpperRandom(random.Random):
    """Jitter at its upper bound (the backoff cap), recording every requested range."""

    def __init__(self) -> None:
        super().__init__(0)
        self.ranges: list[tuple[float, float]] = []

    def uniform(self, a: float, b: float) -> float:
        self.ranges.append((a, b))
        return b


class FakeAdapter:
    """Requests carry the text; 2xx bodies are `ok_body(...)` dicts, parsed back without interpretation."""

    provider = "fake"
    api_key_env = "FAKE_API_KEY"

    def auth_headers(self, api_key: str) -> dict[str, str]:
        return {"authorization": f"Bearer {api_key}"}

    def cache_key(self, cfg: Configuration, item_digest: str) -> str | None:
        return f"k{int(item_digest, 16) % cfg.prompt_cache_keys}" if cfg.prompt_cache_keys else None

    def warmup_cache_keys(self, cfg: Configuration) -> list[str | None]:
        if cfg.prompt_cache_keys:
            return [f"k{i}" for i in range(cfg.prompt_cache_keys)]
        return [] if cfg.is_decision_interface else [None]

    def build_request(self, cfg: Configuration, prompt: Prompt, text: str, cache_key: str | None) -> HttpRequest:
        return HttpRequest(
            "POST",
            FAKE_URL,
            {"content-type": "application/json", "fake-version": "2026-10-01"},
            {"model": cfg.model, "text": text, "cache_key": cache_key},
        )

    def parse_response(self, cfg: Configuration, prompt: Prompt, body: Mapping[str, Any]) -> Parsed:
        usage = Usage(**body["usage"])
        raw = json.dumps(body) if cfg.is_decision_interface else body["output"]
        return Parsed(
            status=body.get("status", "ok"),
            raw_output=raw,
            intent=body["intent"],
            confidence=body["confidence"],
            probabilities=body.get("probabilities"),
            match_probability=body.get("match_probability"),
            case_normalized=body.get("case_normalized", False),
            model_id=body["model"],
            usage=usage,
        )

    def request_id(self, headers: Mapping[str, str]) -> str | None:
        return headers.get("x-request-id")

    def rate_limit_headers(self, headers: Mapping[str, str]) -> dict[str, str]:
        return {k: v for k, v in headers.items() if k.startswith("x-ratelimit-")}


def ok_body(
    *,
    intent: str = "card_arrival",
    output: str | None = None,
    usage: Mapping[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "output": output if output is not None else json.dumps({"intent": intent, "confidence": 0.9}),
        "intent": intent,
        "confidence": 0.9,
        "model": "fake-model-2026",
        "usage": dict(usage) if usage is not None else {"uncached_input": 100, "cache_read": 1000, "output": 10},
        **extra,
    }


def request_text(request: httpx.Request) -> str:
    text: str = json.loads(request.content)["text"]
    return text


def ok_handler(clock: FakeClock | None = None, latency_s: float = 0.0) -> Handler:
    async def handler(request: httpx.Request) -> httpx.Response:
        if clock is not None:
            clock.t += latency_s
        return httpx.Response(200, json=ok_body(), headers={"x-request-id": "req-1"})

    return handler


def make_sender(handler: Handler, clock: FakeClock, rng: random.Random | None = None) -> Sender:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return Sender(client=client, adapter=FakeAdapter(), api_key="sk-test", clock=clock, rng=rng or random.Random(0))


def items(n: int, prefix: str = "test") -> list[Item]:
    return [Item(f"{prefix}-{i}", f"customer message {i}", "card_arrival") for i in range(n)]


def cost(usage: Usage) -> float:
    """$1 per million tokens of every class; enough to tell attempts apart."""
    return (usage.uncached_input + usage.cache_read + usage.cache_write + usage.output) / 1e6


def timeout_usage(text: str) -> Usage:
    return Usage(uncached_input=2_000, output=200)


def reservation(text: str) -> float:
    """Worst case of one attempt: with one price for every class, the timeout charge."""
    return cost(timeout_usage(text))


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=test", "-c", "user.email=test@example.invalid", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


FROZEN_FILES = {
    "src/swapcheck/core.py": "X = 1\n",
    "prompts/incumbent-v1.md": "prompt\n",
    "config/limits.yaml": "openai: {}\n",
    "contracts/contract-v1.yaml": "tag: contract-v1\n",
    "analysis/power.py": "Y = 2\n",
    "README.md": "readme\n",
}


def make_repo(root: Path, *, tag: str | None = "contract-v1") -> Path:
    """A git repository with one file under every frozen path, committed and (optionally) tagged."""
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "--quiet")
    for name, content in FROZEN_FILES.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    git(root, "add", ".")
    git(root, "commit", "--quiet", "-m", "freeze")
    if tag is not None:
        git(root, "tag", "-a", tag, "-m", tag)
    return root


def clone_repo(template: Path, dest: Path) -> Path:
    """A clone of a `make_repo` template (tags included); cheaper than creating a repository per test."""
    git(template, "clone", "--quiet", "--no-hardlinks", str(template), str(dest))
    return dest


def max_in_any_window(starts: list[tuple[float, int]], window_s: float) -> tuple[int, int]:
    """Largest request count and token sum over every window [s, s + window) that begins at a start."""
    worst_requests = worst_tokens = 0
    for s, _ in starts:
        inside = [k for t, k in starts if s <= t < s + window_s]
        worst_requests = max(worst_requests, len(inside))
        worst_tokens = max(worst_tokens, sum(inside))
    return worst_requests, worst_tokens


UNLIMITED = RunBudget(spent_before_usd=0.0, ceiling_usd=1_000.0)


def run_sync(
    cfg: Configuration,
    prompt: Prompt,
    split: Split,
    its: list[Item],
    handler: Handler,
    repo: Path,
    *,
    clock: FakeClock | None = None,
    budget: RunBudget = UNLIMITED,
    run_id: str | None = None,
    limiter: RateLimiter | None = None,
    concurrency: int = 16,
    tokens: int = 100,
    reservation_fn: Callable[[str], float] = reservation,
) -> RunMeta:
    """`runner.run` against a fake transport, with `runs/` under `repo`."""

    async def go() -> RunMeta:
        sender = make_sender(handler, clock or FakeClock())
        sender.limiter = limiter
        async with sender.client:
            return await runner.run(
                cfg,
                prompt,
                split,
                its,
                sender=sender,
                runs_dir=repo / "runs",
                repo_root=repo,
                cost_fn=cost,
                timeout_usage_fn=timeout_usage,
                reservation_fn=reservation_fn,
                token_estimate_fn=lambda text: tokens,
                budget=budget,
                run_id=run_id,
                concurrency=concurrency,
            )

    return asyncio.run(go())


def retry_sync(
    run_dir: Path,
    cfg: Configuration,
    prompt: Prompt,
    its: list[Item],
    handler: Handler,
    repo: Path,
    *,
    budget: RunBudget = UNLIMITED,
    concurrency: int = 16,
) -> RunMeta:
    async def go() -> RunMeta:
        sender = make_sender(handler, FakeClock())
        async with sender.client:
            return await runner.retry_errors(
                run_dir,
                cfg,
                prompt,
                its,
                sender=sender,
                repo_root=repo,
                cost_fn=cost,
                timeout_usage_fn=timeout_usage,
                reservation_fn=reservation,
                token_estimate_fn=lambda text: 100,
                budget=budget,
                concurrency=concurrency,
            )

    return asyncio.run(go())
