"""Prices, attempt cost, spend over run records, and the per-configuration cost model (spec §9.5, §10, §11).

Percentiles (per-item p90 and reasoning p95) use `numpy.quantile(..., method="higher")`: the smallest
observed value with at least the stated share of items at or below it, so a budget built on it never
uses an interpolated value below what was measured.
"""

from __future__ import annotations

import functools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict

from swapcheck.configs import Configuration
from swapcheck.groups import REPO_ROOT
from swapcheck.prompt import Prompt, prefix_tokens
from swapcheck.records import RUN_JSON, Attempt, ItemRow, Usage, Warmup, read_meta, read_rows

PRICES_PATH = REPO_ROOT / "config" / "prices.yaml"
PROVIDERS = ("openai", "anthropic", "typesafe")
TOKEN_CLASSES = ("uncached_input", "cache_read", "cache_write", "output", "reasoning")
_PER_TOKEN = 1e-6  # prices are per 1M tokens


class ModelPrice(BaseModel):
    """USD per 1M tokens for each billed class. Reasoning is part of `output` and not priced separately."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    uncached_input: float
    cache_read: float
    cache_write: float
    output: float
    source: str


class Prices(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    retrieved: str
    models: dict[str, ModelPrice]

    def for_model(self, model: str) -> ModelPrice:
        try:
            return self.models[model]
        except KeyError:
            raise KeyError(f"no price for model {model!r} in config/prices.yaml") from None


def load_prices(path: Path = PRICES_PATH) -> Prices:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Prices(retrieved=str(raw["retrieved"]), models=raw["models"])


def _usage_cost(
    price: ModelPrice, uncached_input: float, cache_read: float, cache_write: float, output: float
) -> float:
    return _PER_TOKEN * (
        uncached_input * price.uncached_input
        + cache_read * price.cache_read
        + cache_write * price.cache_write
        + output * price.output
    )


def attempt_cost_usd(prices: Prices, cfg: Configuration, usage: Usage) -> float:
    """Cost of one attempt's usage. `usage.reasoning` is a subset of `usage.output`, so it adds nothing."""
    price = prices.for_model(cfg.model)
    return _usage_cost(price, usage.uncached_input, usage.cache_read, usage.cache_write, usage.output)


@functools.cache
def _prefix_tokens(prompt: Prompt) -> int:
    return prefix_tokens(prompt)


@functools.cache
def _o200k_len(text: str) -> int:
    import tiktoken

    return len(tiktoken.get_encoding("o200k_base").encode(text))


def timeout_usage(cfg: Configuration, prompt: Prompt, text: str) -> Usage:
    """The charge for a timed-out attempt (spec §9.5): full uncached input plus max output tokens.

    Input is estimated with `o200k_base` as the developer message plus the customer text. For Jev the
    developer message stands in for the criteria it is translated from (§4.1), and only input is charged.
    """
    uncached = _prefix_tokens(prompt) + _o200k_len(text)
    if not cfg.is_llm:
        return Usage(uncached_input=uncached, output=0)
    if cfg.max_output_tokens is None:
        raise ValueError(f"configuration {cfg.id} has no max_output_tokens")
    return Usage(uncached_input=uncached, output=cfg.max_output_tokens)


def _attempts_cost(prices: Prices, cfg: Configuration, attempts: Sequence[Attempt]) -> float:
    return sum((attempt_cost_usd(prices, cfg, a.usage) for a in attempts), 0.0)


def run_cost_usd(prices: Prices, cfg: Configuration, rows: Sequence[ItemRow], warmups: Sequence[Warmup]) -> float:
    """Billed cost of one run: every attempt of every item and every warm-up."""
    return sum((_attempts_cost(prices, cfg, w.attempts) for w in warmups), 0.0) + sum(
        (_attempts_cost(prices, cfg, r.attempts) for r in rows), 0.0
    )


def spent_usd(runs_dir: Path, prices: Prices, configs: Mapping[str, Configuration]) -> dict[str, float]:
    """Spend per provider over every attempt and warm-up of every run under `runs_dir` (spec §9.5).

    In-progress runs count: `run.json` is written when a run starts, and `read_rows` reads the plain
    `items.jsonl` up to its last complete line. A run directory with item rows but no `run.json`
    cannot be attributed to a provider and raises instead of being undercounted.
    """
    spent = dict.fromkeys(PROVIDERS, 0.0)
    if not runs_dir.exists():
        return spent
    for run_dir in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        if not (run_dir / RUN_JSON).exists():
            if read_rows(run_dir):
                raise ValueError(f"{run_dir} has item rows but no {RUN_JSON}; its spend cannot be attributed")
            continue
        meta = read_meta(run_dir)
        try:
            cfg = configs[meta.config_id]
        except KeyError:
            raise KeyError(f"{run_dir}: unknown configuration {meta.config_id!r}") from None
        spent[cfg.provider] += run_cost_usd(prices, cfg, read_rows(run_dir), meta.warmups)
    return spent


# ---------------------------------------------------------------------------------------------------
# Cost model (spec §11)


@dataclass(frozen=True)
class ClassStats:
    """Tokens of one class per item, summed over the item's attempts."""

    mean: float
    p90: float


@dataclass(frozen=True)
class CostModel:
    config_id: str
    n_items: int
    tokens: dict[str, ClassStats]  # keys: TOKEN_CLASSES; `reasoning` only over items that report it
    item_mean_usd: float  # per item, all attempts
    item_p90_usd: float  # per item, all attempts; drives the budget guard (§9.5)
    billed_per_1000: float  # every attempt incl. warm-ups and retries, divided by items
    steady_per_1000: float | None  # shared prefix read from cache on every call; None without a success
    sparse_per_1000: float | None  # nothing cached; None without a successful attempt
    prefix_tokens: int  # largest cached prefix (cache read + cache write) seen in one call, provider tokenizer
    reasoning_mean: float | None  # reasoning/thinking tokens per message; None if never reported
    reasoning_p95: float | None


def _quantile(values: Sequence[float], q: float) -> float:
    return float(np.quantile(np.asarray(values, dtype=float), q, method="higher"))


def _final_success(row: ItemRow) -> Attempt | None:
    """The attempt whose response was used: the last one, if it returned HTTP 2xx."""
    last = row.attempts[-1] if row.attempts else None
    if last is None or last.http_status is None or not 200 <= last.http_status < 300:
        return None
    return last


def _input_tokens(u: Usage) -> int:
    return u.uncached_input + u.cache_read + u.cache_write


def cost_model(cfg: Configuration, rows: Sequence[ItemRow], warmups: Sequence[Warmup], prices: Prices) -> CostModel:
    """Token statistics and cost per 1,000 messages for one run of `cfg` (spec §11).

    - billed: all attempts, warm-ups and retries (timed-out attempts carry their §9.5 charge), per item;
    - steady: one call per message with the shared prefix priced as cache read and the rest of the input
      uncached, at the mean input and output of the successful calls;
    - sparse: the same calls with every input token uncached.
    The prefix is the largest cache read + cache write seen in one call, in the provider's own tokens.
    """
    if not rows:
        raise ValueError(f"no item rows for {cfg.id}")
    price = prices.for_model(cfg.model)
    per_item: dict[str, list[float]] = {c: [] for c in TOKEN_CLASSES}
    item_costs: list[float] = []
    for row in rows:
        for cls in ("uncached_input", "cache_read", "cache_write", "output"):
            per_item[cls].append(float(sum(getattr(a.usage, cls) for a in row.attempts)))
        reported = [a.usage.reasoning for a in row.attempts if a.usage.reasoning is not None]
        if reported:
            per_item["reasoning"].append(float(sum(reported)))
        item_costs.append(_attempts_cost(prices, cfg, row.attempts))

    tokens = {cls: ClassStats(mean=float(np.mean(v)), p90=_quantile(v, 0.9)) for cls, v in per_item.items() if v}
    reasoning = per_item["reasoning"]
    n = len(rows)
    billed = run_cost_usd(prices, cfg, rows, warmups)

    successes = [a for a in map(_final_success, rows) if a is not None]
    calls = successes + [a for w in warmups for a in w.attempts]
    prefix = max((a.usage.cache_read + a.usage.cache_write for a in calls), default=0)
    steady: float | None = None
    sparse: float | None = None
    if successes:
        mean_input = float(np.mean([_input_tokens(a.usage) for a in successes]))
        mean_output = float(np.mean([a.usage.output for a in successes]))
        cached = min(float(prefix), mean_input)
        steady = 1000 * _usage_cost(price, mean_input - cached, cached, 0.0, mean_output)
        sparse = 1000 * _usage_cost(price, mean_input, 0.0, 0.0, mean_output)

    return CostModel(
        config_id=cfg.id,
        n_items=n,
        tokens=tokens,
        item_mean_usd=float(np.mean(item_costs)),
        item_p90_usd=_quantile(item_costs, 0.9),
        billed_per_1000=1000 * billed / n,
        steady_per_1000=steady,
        sparse_per_1000=sparse,
        prefix_tokens=prefix,
        reasoning_mean=float(np.mean(reasoning)) if reasoning else None,
        reasoning_p95=_quantile(reasoning, 0.95) if reasoning else None,
    )


def run_cost_model(run_dir: Path, prices: Prices, configs: Mapping[str, Configuration]) -> CostModel:
    meta = read_meta(run_dir)
    return cost_model(configs[meta.config_id], read_rows(run_dir), meta.warmups, prices)
