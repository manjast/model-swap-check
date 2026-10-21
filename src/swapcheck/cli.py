"""`swapcheck` command line (spec §12)."""

from __future__ import annotations

import argparse
import asyncio
import os
from collections import Counter
from pathlib import Path

from swapcheck import data, prompt
from swapcheck.groups import OUT_OF_SCOPE, REPO_ROOT, load_groups


def cmd_data(_: argparse.Namespace) -> int:
    """Download and verify Banking77, then write the splits."""
    groups = load_groups()
    splits = data.load_splits(groups)
    data.write_splits(splits, groups)
    print(f"Banking77 @ {data.COMMIT[:12]}: SHA-256 verified; splits in {data.DATA_DIR / 'splits'}")
    for name in data.SPLITS:
        items = splits[name]
        oos = sum(groups.slice_of(it.intent) == OUT_OF_SCOPE for it in items)
        print(f"  {name:<9}{len(items):>6} items  {oos:>5} OOS  {data.item_list_hash(items)[:16]}")
    by_slice = Counter(groups.slice_of(it.intent) for it in splits["cert"])
    print("  cert slices: " + ", ".join(f"{s} {by_slice[s]}" for s in groups.slices))
    return 0


def cmd_prompt(args: argparse.Namespace) -> int:
    """Report the prompt's size and hash, and generate (or check) the Jev translation."""
    p = prompt.load_prompt()
    print(
        f"incumbent-v1: {len(p.catalog)} intents, prefix {prompt.prefix_tokens(p)} o200k tokens, "
        f"sha256 {p.sha256()[:16]}"
    )
    expected = prompt.render_jev_yaml(p)
    path = prompt.JEV_PROMPT
    current = path.read_text(encoding="utf-8") if path.exists() else None
    if current == expected:
        print(f"{path.name}: up to date")
        return 0
    if args.check:
        print(f"{path.name}: differs from the §4.1 translation; run `swapcheck prompt`")
        return 1
    path.write_text(expected, encoding="utf-8")
    print(f"{path.name}: written")
    return 0


def load_env(path: Path = REPO_ROOT / ".env") -> None:
    """Read `KEY=value` lines from the git-ignored `.env` into the environment (existing values win)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key, value)


def cmd_run(args: argparse.Namespace) -> int:
    """Run (or resume, or retry the API errors of) one configuration on one split."""
    import httpx

    from swapcheck import budget as budget_mod
    from swapcheck import cost, runner
    from swapcheck.configs import load_configurations
    from swapcheck.freeze import GUARDED_SPLITS, tag_commit
    from swapcheck.http import Sender, SystemClock
    from swapcheck.providers import get_adapter
    from swapcheck.ratelimit import RateLimiter, TokenEstimator, limit_for, load_limits
    from swapcheck.records import Usage, read_rows

    load_env()
    configs = load_configurations()
    cfg = configs[args.config]
    if cfg.pilot_only and args.split != "pilot":
        raise SystemExit(f"{cfg.id} is a pilot-only variant")
    runs_dir = REPO_ROOT / "runs"
    if args.split in GUARDED_SPLITS and not args.retry_errors:
        commit = tag_commit(REPO_ROOT)
        if commit is not None and cfg.provider in budget_mod.stopped_providers(runs_dir, configs, commit):
            raise SystemExit(
                f"{cfg.provider} had an in-run budget stop under this contract tag; no later run starts (spec §9.5)"
            )
    run_prompt = prompt.load_prompt(cfg.prompt_path)
    items = data.load_splits(load_groups())[args.split]
    adapter = get_adapter(cfg.provider)
    api_key = os.environ.get(adapter.api_key_env)
    if not api_key:
        raise SystemExit(f"{adapter.api_key_env} is not set (put it in .env)")
    prices = cost.load_prices()
    spent = cost.spent_usd(runs_dir, prices, configs).get(cfg.provider, 0.0)
    limit = budget_mod.load_budget().limit(cfg.provider)
    if args.split == "dev" and args.ceiling_usd is None:
        raise SystemExit("dev runs need --ceiling-usd from the pre-dev budget gate (spec §9.5)")
    ceiling = min(limit, args.ceiling_usd) if args.ceiling_usd is not None else limit
    reason = budget_mod.BUDGET_STOP if ceiling == limit else "spend ceiling"
    print(f"{cfg.id} on {args.split} ({len(items)} items): {cfg.provider} spent ${spent:.4f}, ceiling ${ceiling:.2f}")

    async def go() -> int:
        async with httpx.AsyncClient() as client:
            limiter = RateLimiter(limit_for(load_limits(), cfg), SystemClock())
            sender = Sender(client, adapter, api_key, limiter=limiter)
            budget = runner.RunBudget(spent, ceiling, reason=reason)
            estimate = TokenEstimator(cfg, run_prompt)

            def cost_fn(u: Usage) -> float:
                return cost.attempt_cost_usd(prices, cfg, u)

            def timeout_fn(text: str) -> Usage:
                return cost.timeout_usage(cfg, run_prompt, text)

            def reservation_fn(text: str) -> float:
                return cost.reservation_usd(prices, cfg, timeout_fn(text))

            if args.retry_errors:
                meta = await runner.retry_errors(
                    runs_dir / args.retry_errors,
                    cfg,
                    run_prompt,
                    items,
                    sender=sender,
                    repo_root=REPO_ROOT,
                    cost_fn=cost_fn,
                    timeout_usage_fn=timeout_fn,
                    reservation_fn=reservation_fn,
                    token_estimate_fn=estimate,
                    budget=budget,
                )
            else:
                meta = await runner.run(
                    cfg,
                    run_prompt,
                    args.split,
                    items,
                    sender=sender,
                    runs_dir=runs_dir,
                    repo_root=REPO_ROOT,
                    cost_fn=cost_fn,
                    timeout_usage_fn=timeout_fn,
                    reservation_fn=reservation_fn,
                    token_estimate_fn=estimate,
                    budget=budget,
                    run_id=args.run_id,
                )
        ok, why = runner.run_validity(meta, read_rows(runs_dir / meta.run_id))
        print(f"run {meta.run_id}: {meta.totals.by_status}, billed ${meta.totals.billed_usd:.4f}")
        print(f"valid for decide: {ok}" + ("" if ok else f" ({why})"))
        return 0 if meta.complete else 3

    return asyncio.run(go())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="swapcheck")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("data", help="download, verify and split Banking77").set_defaults(func=cmd_data)
    p_prompt = sub.add_parser("prompt", help="check the prompt and generate the Jev translation")
    p_prompt.add_argument("--check", action="store_true", help="fail instead of writing")
    p_prompt.set_defaults(func=cmd_prompt)
    p_run = sub.add_parser("run", help="run, resume or retry one configuration on one split")
    p_run.add_argument("config")
    p_run.add_argument("split", choices=["pilot", "dev", "cert", "aa"])
    p_run.add_argument("--run-id", help="resume this run (same configuration and split)")
    p_run.add_argument("--retry-errors", metavar="RUN_ID", help="the single API-error retry pass of a finished run")
    p_run.add_argument("--ceiling-usd", type=float, help="absolute provider spend at which this run stops")
    p_run.set_defaults(func=cmd_run)
    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
