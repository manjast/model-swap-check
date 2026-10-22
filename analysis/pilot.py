"""Pilot report (docs/spec.md §14, docs/test-plan.md §5): the measured values behind docs/pilot.md.

Reads the latest pilot run of every configuration under runs/ and prints Markdown: validity (T-L1),
cache reads (T-L2, T-L3), cost model and the pre-dev gate (T-L4, T-L9), latency (T-L7), option-order
sensitivity (T-L8), the Decisions/Jev confidence function, timing headers and rate limits (§9.4).

Only structured fields of the run records are read: no message text and no ground truth.

Usage:
    python analysis/pilot.py [--runs-dir runs]
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np

from swapcheck import budget as budget_mod
from swapcheck import cost
from swapcheck.configs import Configuration, load_configurations
from swapcheck.records import Attempt, ItemRow, RunMeta, read_meta, read_rows

ORDER_PAIRS = (("jev-c51", "jev-c51-reversed"), ("jev-noul", "jev-noul-reversed"), ("luna-dec", "luna-dec-reversed"))
LIMIT_HEADERS = (
    "x-ratelimit-limit-requests",
    "x-ratelimit-limit-tokens",
    "anthropic-ratelimit-requests-limit",
    "anthropic-ratelimit-tokens-limit",
    "anthropic-ratelimit-input-tokens-limit",
    "anthropic-ratelimit-output-tokens-limit",
)

Run = tuple[RunMeta, list[ItemRow]]


def _q(values: Sequence[float], q: float) -> float:
    return float(np.quantile(np.asarray(values, dtype=float), q, method="higher"))


def latest_pilot_runs(runs_dir: Path) -> dict[str, Run]:
    """The most recently started complete pilot run per configuration (run IDs break ties)."""
    latest: dict[str, tuple[tuple[str, str], Path]] = {}
    for run_dir in (p for p in runs_dir.iterdir() if (p / "run.json").exists()):
        meta = read_meta(run_dir)
        key = (meta.started_at, meta.run_id)
        if meta.split == "pilot" and meta.complete and key > latest.get(meta.config_id, (("", ""), run_dir))[0]:
            latest[meta.config_id] = (key, run_dir)
    return {cid: (read_meta(d), read_rows(d)) for cid, (_, d) in sorted(latest.items())}


def final(row: ItemRow) -> Attempt:
    return row.attempts[-1]


def table(header: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    def cell(v: object) -> str:
        if v is None:
            return "-"
        if isinstance(v, float):
            return f"{v:.4g}"
        return str(v)

    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(cell(v) for v in r) + " |" for r in rows]
    return "\n".join(lines)


def validity(runs: dict[str, Run]) -> str:
    out = []
    for cid, (meta, rows) in runs.items():
        status = Counter(r.status for r in rows)
        codes = Counter(r.error_code for r in rows if r.status != "ok")
        out.append(
            (
                cid,
                len(rows),
                status["ok"],
                status["invalid_output"],
                status["api_error"],
                ", ".join(f"{k}: {v}" for k, v in sorted(codes.items(), key=str)) or None,
                ", ".join(meta.returned_model_ids),
                meta.totals.n_429,
                sum(len(r.attempts) > 1 for r in rows),
                meta.totals.billed_usd,
            )
        )
    head = ("config", "items", "ok", "invalid", "api_error", "error codes", "returned model", "429s", "retried", "$")
    return table(head, out)


def cache(runs: dict[str, Run]) -> str:
    out = []
    for cid, (meta, rows) in runs.items():
        calls = [final(r) for r in rows if final(r).http_status == 200]
        if not calls:
            continue
        reads = sum(a.usage.cache_read > 0 for a in calls)
        out.append(
            (
                cid,
                len(meta.warmups),
                f"{reads}/{len(calls)}",
                sum(a.usage.cache_read for a in calls),
                sum(a.usage.cache_write for a in calls)
                + sum(a.usage.cache_write for w in meta.warmups for a in w.attempts),
                sum(a.usage.uncached_input for a in calls),
                meta.totals.billed_usd,
            )
        )
    return table(
        ("config", "warm-ups", "calls with cache read", "read", "write (incl. warm-ups)", "uncached", "$"), out
    )


def cost_models(runs: dict[str, Run], configs: dict[str, Configuration], prices: cost.Prices) -> list[cost.CostModel]:
    return [cost.cost_model(configs[cid], rows, meta.warmups, prices) for cid, (meta, rows) in runs.items()]


def cost_table(models: Sequence[cost.CostModel]) -> str:
    out = []
    for m in models:
        tok = m.tokens

        def stat(cls: str, tok: dict[str, cost.ClassStats] = tok) -> str | None:
            return f"{tok[cls].mean:.0f} / {tok[cls].p90:.0f}" if cls in tok else None

        out.append(
            (
                m.config_id,
                stat("uncached_input"),
                stat("cache_read"),
                stat("cache_write"),
                stat("output"),
                stat("reasoning"),
                m.item_mean_usd * 1000,
                m.item_p90_usd * 1000,
                m.billed_per_1000,
                m.steady_per_1000,
                m.sparse_per_1000,
                m.prefix_tokens,
            )
        )
    head = (
        "config",
        "uncached mean/p90",
        "cache read",
        "cache write",
        "output",
        "reasoning",
        "$/1k mean",
        "$/1k p90",
        "$/1k billed",
        "$/1k steady",
        "$/1k sparse",
        "prefix",
    )
    return table(head, out)


def gate(
    models: Sequence[cost.CostModel], configs: dict[str, Configuration], prices: cost.Prices, runs_dir: Path
) -> str:
    p90 = {m.config_id: m.item_p90_usd for m in models}
    missing = sorted({r.config_id for r in budget_mod.DEV_PLAN} - {*p90, *budget_mod.PILOT_PROXY})
    if missing:
        return f"Not computed: no complete pilot run for {', '.join(missing)}."
    spent = cost.spent_usd(runs_dir, prices, configs)
    g = budget_mod.pre_dev_gate(spent, p90, configs, budget_mod.load_budget())
    lines = [
        table(
            ("provider", "spent", "dev + cert reserve projected", "cert reserve", "fits"),
            [(p, spent[p], g.projected_usd[p], g.cert_reserve_usd[p], g.fits[p]) for p in g.projected_usd],
        ),
        "",
        f"Skipped by the gate: {', '.join(g.skipped) or 'none'}.",
        "",
        table(
            ("dev run", "provider", "projected $", "ceiling $"),
            [(r.run.name, r.provider, r.projected_usd, r.ceiling_usd) for r in g.runs],
        ),
        "",
        planning(spent, g, p90, configs),
    ]
    return "\n".join(lines)


def planning(
    spent: dict[str, float], g: budget_mod.DevGate, p90: dict[str, float], configs: dict[str, Configuration]
) -> str:
    """§11 planning table at pilot p90: spent + gated dev plan + every cert run without a reasoning variant
    (mandatory, `luna-dec`, `luna-none-x` priced as `luna-none`), then the extra cert run for R = low / medium."""
    p90 = {**p90, "luna-none-x": p90["luna-none"]}
    cert = [
        *budget_mod.mandatory_cert_runs(p90),
        *(budget_mod.PlannedRun(c, c, "cert") for c in ("luna-dec", "luna-none-x")),
    ]
    rows = []
    for provider, prefix in (("openai", "luna"), ("anthropic", "haiku55"), ("typesafe", None)):
        dev = sum(r.projected_usd for r in g.runs if r.provider == provider)
        base = (
            spent[provider]
            + dev
            + sum(budget_mod.run_cost_usd(r, p90) for r in cert if configs[r.config_id].provider == provider)
        )
        extra = (
            [budget_mod.SPLIT_SIZES["cert"] * p90[f"{prefix}-{lvl}"] for lvl in ("low", "medium")]
            if prefix
            else [None, None]
        )
        rows.append((provider, spent[provider], dev, base, *extra))
    head = ("provider", "spent", "dev", "spent + dev + cert without R", "+ R = low", "+ R = medium")
    return table(head, rows)


def latency(runs: dict[str, Run]) -> str:
    out = []
    for cid, (_, rows) in runs.items():
        calls = [final(r) for r in rows if final(r).http_status == 200 and final(r).latency_ms is not None]
        lat: Callable[[list[Attempt]], list[float]] = lambda xs: [a.latency_ms for a in xs if a.latency_ms is not None]  # noqa: E731
        read = lat([a for a in calls if a.usage.cache_read > 0])
        unread = lat([a for a in calls if a.usage.cache_read == 0])
        allv = lat(calls)
        server = [float(a.headers["openai-processing-ms"]) for a in calls if "openai-processing-ms" in a.headers]
        out.append(
            (
                cid,
                _q(allv, 0.5),
                _q(allv, 0.95),
                f"{_q(read, 0.5):.0f} / {_q(read, 0.95):.0f} (n={len(read)})" if read else None,
                f"{_q(unread, 0.5):.0f} / {_q(unread, 0.95):.0f} (n={len(unread)})" if unread else None,
                f"{len(server)}/{len(calls)}",
                _q(server, 0.5) if server else None,
            )
        )
    head = (
        "config",
        "p50 ms",
        "p95 ms",
        "cache read p50/p95",
        "no cache read p50/p95",
        "openai-processing-ms",
        "its p50",
    )
    return table(head, out)


def order_sensitivity(runs: dict[str, Run]) -> str:
    out = []
    for normal, reversed_ in ORDER_PAIRS:
        if normal not in runs or reversed_ not in runs:
            continue
        a = {r.item_id: r.intent for r in runs[normal][1] if r.status == "ok"}
        b = {r.item_id: r.intent for r in runs[reversed_][1] if r.status == "ok"}
        both = sorted(a.keys() & b.keys())
        changed = sum(a[i] != b[i] for i in both)
        out.append((normal, len(both), changed, changed / len(both) if both else None))
    return table(("interface", "items ok in both", "choice changed", "share"), out)


def confidence_function(runs: dict[str, Run]) -> str:
    """Max |confidence - f(probabilities)| for the two candidate functions. They differ by (1 - p_max)/(n - 1),
    so only items with a low p_max tell them apart; those (p_max <= 0.9) are reported separately."""
    out = []
    for cid, (_, rows) in runs.items():
        pairs = [(r.confidence, r.probabilities) for r in rows if r.status == "ok" and r.probabilities]
        if not pairs:
            continue
        errors: list[tuple[float, float, float]] = []  # (p_max, rescaled error, p_max error)
        for conf, probs in pairs:
            assert conf is not None and probs is not None
            n, top = len(probs), max(probs.values())
            errors.append((top, abs(conf - (top - 1 / n) / (1 - 1 / n)), abs(conf - top)))
        low = [e for e in errors if e[0] <= 0.9]
        out.append(
            (
                cid,
                len(errors),
                max(e[1] for e in errors),
                max(e[2] for e in errors),
                len(low),
                max((e[1] for e in low), default=None),
                max((e[2] for e in low), default=None),
            )
        )
    head = ("config", "items", "max err rescaled", "max err p_max", "items p_max <= 0.9", "rescaled", "p_max")
    return table(head, out)


def rate_limits(runs: dict[str, Run], configs: dict[str, Configuration]) -> str:
    seen: dict[tuple[str, str], dict[str, str]] = {}
    for cid, (meta, rows) in runs.items():
        cfg = configs[cid]
        key = (cfg.provider, cfg.model + (f" ({cfg.api})" if cfg.api else ""))
        attempts = [a for r in rows for a in r.attempts] + [a for w in meta.warmups for a in w.attempts]
        for a in attempts:
            limits = {h: a.headers[h] for h in LIMIT_HEADERS if h in a.headers}
            if limits:
                seen.setdefault(key, {}).update(limits)
    return table(
        ("provider", "model", "limit headers"),
        [(p, m, ", ".join(f"{k}={v}" for k, v in lim.items())) for (p, m), lim in sorted(seen.items())],
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs-dir", type=Path, default=Path("runs"))
    args = ap.parse_args()
    configs = load_configurations()
    prices = cost.load_prices()
    runs = latest_pilot_runs(args.runs_dir)
    models = cost_models(runs, configs, prices)
    sections = [
        ("Validity (T-L1)", validity(runs)),
        ("Cache (T-L2, T-L3)", cache(runs)),
        ("Cost model per item, tokens mean / p90 (T-L4, T-L9)", cost_table(models)),
        ("Pre-dev gate (§9.5)", gate(models, configs, prices, args.runs_dir)),
        ("Latency, final attempt, ms (T-L7)", latency(runs)),
        ("Option-order sensitivity (T-L8)", order_sensitivity(runs)),
        ("Confidence as a function of the probabilities (§14)", confidence_function(runs)),
        ("Rate-limit headers (§9.4)", rate_limits(runs, configs)),
    ]
    print("\n\n".join(f"## {title}\n\n{body}" for title, body in sections))


if __name__ == "__main__":
    main()
