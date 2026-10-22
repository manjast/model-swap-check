"""`swapcheck` command line (spec §12)."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from swapcheck import data, prompt
from swapcheck.freeze import CONTRACT_TAG
from swapcheck.groups import OUT_OF_SCOPE, REPO_ROOT, load_groups

# Request-ID headers of the three providers, plus the content type; nothing account-identifying.
CAPTURED_HEADERS = frozenset({"x-request-id", "request-id", "x-typesafe-request-id", "content-type"})


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
    """Report the prompt's size and hash, and generate (or check) the Jev and Decisions translations."""
    p = prompt.load_prompt()
    print(
        f"incumbent-v1: {len(p.catalog)} intents, prefix {prompt.prefix_tokens(p)} o200k tokens, "
        f"sha256 {p.sha256()[:16]}"
    )
    translations = (
        (prompt.JEV_PROMPT, prompt.render_jev_yaml(p), "§4.1"),
        (prompt.DECISIONS_PROMPT, prompt.render_decisions_yaml(p), "§4.2"),
    )
    status = 0
    for path, expected, section in translations:
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == expected:
            print(f"{path.name}: up to date")
        elif args.check:
            print(f"{path.name}: differs from the {section} translation; run `swapcheck prompt`")
            status = 1
        else:
            path.write_text(expected, encoding="utf-8")
            print(f"{path.name}: written")
    return status


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
        commit = tag_commit(REPO_ROOT, args.contract_tag)
        if commit is not None and cfg.provider in budget_mod.stopped_providers(runs_dir, configs, commit):
            raise SystemExit(
                f"{cfg.provider} had an in-run budget stop under this contract tag; no later run starts (spec §9.5)"
            )
    run_prompt = prompt.load_prompt(cfg.prompt_path)
    items = data.load_splits(load_groups())[args.split]
    adapter = get_adapter(cfg)
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

    captured = 0

    def capture(status: int, headers: httpx.Headers, body: Mapping[str, Any]) -> None:
        """Save a 2xx response in the T-R2 fixture format; only request-ID, rate-limit and timing headers.
        A failed save is reported and skipped: the paid response must still be parsed and recorded."""
        nonlocal captured
        captured += 1
        kept = adapter.rate_limit_headers(headers) | {k: v for k, v in headers.items() if k in CAPTURED_HEADERS}
        doc = {"config_id": cfg.id, "http_status": status, "headers": kept, "body": body}
        path = args.capture_dir / f"{cfg.id}-{captured:03d}.json"
        try:
            path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"capture skipped: {path}: {exc}", file=sys.stderr)

    if args.capture_dir is not None:
        args.capture_dir.mkdir(parents=True, exist_ok=True)

    async def go() -> int:
        async with httpx.AsyncClient() as client:
            limiter = RateLimiter(limit_for(load_limits(), cfg), SystemClock())
            sender = Sender(
                client, adapter, api_key, limiter=limiter, capture=capture if args.capture_dir is not None else None
            )
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
                    contract_tag=args.contract_tag,
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
                    contract_tag=args.contract_tag,
                )
        ok, why = runner.run_validity(meta, read_rows(runs_dir / meta.run_id))
        print(f"run {meta.run_id}: {meta.totals.by_status}, billed ${meta.totals.billed_usd:.4f}")
        print(f"valid for decide: {ok}" + ("" if ok else f" ({why})"))
        return 0 if meta.complete else 3

    return asyncio.run(go())


def cmd_decide(args: argparse.Namespace) -> int:
    """Replay frozen certification evidence into decision records."""
    from swapcheck.contract import load_contract
    from swapcheck.decide import DecisionRefusal, write_decisions

    contract = load_contract(args.contract)
    groups = load_groups()
    items = data.load_splits(groups)
    try:
        write_decisions(args.runs_dir, contract, items["cert"], groups, args.output_dir)
    except DecisionRefusal as exc:
        print(str(exc))
        return 2
    return 0


def cmd_jev_policy(args: argparse.Namespace) -> int:
    """Replay the amendment 2 Jev report (spec §7.9)."""
    from swapcheck.contract import load_contract
    from swapcheck.decide import DecisionRefusal
    from swapcheck.jev_policy import write_jev_policy

    groups = load_groups()
    items = data.load_splits(groups)["cert"]
    try:
        write_jev_policy(
            args.runs_dir,
            load_contract(args.base_contract),
            load_contract(args.contract),
            items,
            groups,
            args.output_dir,
        )
    except DecisionRefusal as exc:
        print(str(exc))
        return 2
    return 0


def cmd_risk_limits(args: argparse.Namespace) -> int:
    """Replay the amendment 3 risk-limit report (spec §7.10)."""
    from swapcheck.contract import load_contract
    from swapcheck.decide import DecisionRefusal
    from swapcheck.risk_limits import write_risk_limits

    groups = load_groups()
    items = data.load_splits(groups)["cert"]
    try:
        write_risk_limits(
            args.runs_dir,
            load_contract(args.base_contract),
            load_contract(args.jev_contract),
            load_contract(args.contract),
            items,
            groups,
            args.output_dir,
        )
    except DecisionRefusal as exc:
        print(str(exc))
        return 2
    return 0


def cmd_latency(args: argparse.Namespace) -> int:
    """Run the separately registered, sequential latency study."""
    import httpx

    from swapcheck import budget, cost
    from swapcheck.configs import load_configurations
    from swapcheck.http import Sender
    from swapcheck.latency import ORDER, LatencyError, frozen_entries, run_study
    from swapcheck.providers import get_adapter

    load_env()
    configs = load_configurations()
    prompts = {cid: prompt.load_prompt(configs[cid].prompt_path) for cid in ORDER}
    runs_dir = REPO_ROOT / "runs"
    try:
        frozen_entries(runs_dir, configs, prompts)
    except LatencyError as exc:
        print(str(exc))
        return 2
    adapters = {cid: get_adapter(configs[cid]) for cid in ORDER}
    keys = {}
    for cid, adapter in adapters.items():
        key = os.environ.get(adapter.api_key_env)
        if not key:
            raise SystemExit(f"{adapter.api_key_env} is not set (put it in .env)")
        keys[cid] = key

    async def go() -> int:
        async with httpx.AsyncClient() as http_client:
            senders = {cid: Sender(http_client, adapters[cid], keys[cid], trace_timing=True) for cid in ORDER}
            try:
                study = await run_study(
                    client=args.client,
                    rounds=args.rounds,
                    items=data.load_splits(load_groups())["dev"],
                    configs=configs,
                    prompts=prompts,
                    senders=senders,
                    prices=cost.load_prices(),
                    budget=budget.load_budget(),
                    runs_dir=runs_dir,
                    repo_root=REPO_ROOT,
                )
            except LatencyError as exc:
                print(str(exc))
                return 2
        print(f"{study.study_id}: {'complete' if study.complete else study.incomplete_reason}")
        return 0 if study.complete else 3

    return asyncio.run(go())


def cmd_latency_report(args: argparse.Namespace) -> int:
    """Replay exactly one completed latency study."""
    from swapcheck.latency import LatencyError, write_report

    try:
        write_report(args.runs_dir, args.output_dir)
    except LatencyError as exc:
        print(str(exc))
        return 2
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Write measured dev discordance for margin selection."""
    from swapcheck.contract import load_contract
    from swapcheck.report import write_pdisc

    contract = load_contract(args.contract)
    groups = load_groups()
    write_pdisc(args.runs_dir, contract, data.load_splits(groups)["dev"], groups, args.pdisc_json)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="swapcheck")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("data", help="download, verify and split Banking77").set_defaults(func=cmd_data)
    p_prompt = sub.add_parser("prompt", help="check the prompt and generate the Jev and Decisions translations")
    p_prompt.add_argument("--check", action="store_true", help="fail instead of writing")
    p_prompt.set_defaults(func=cmd_prompt)
    p_run = sub.add_parser("run", help="run, resume or retry one configuration on one split")
    p_run.add_argument("config")
    p_run.add_argument("split", choices=["pilot", "dev", "cert", "aa"])
    p_run.add_argument("--run-id", help="resume this run (same configuration and split)")
    p_run.add_argument("--retry-errors", metavar="RUN_ID", help="the single API-error retry pass of a finished run")
    p_run.add_argument("--ceiling-usd", type=float, help="absolute provider spend at which this run stops")
    p_run.add_argument("--capture-dir", type=Path, help="also save every 2xx response here (pilot fixtures, T-L6)")
    p_run.add_argument(
        "--contract-tag", default=CONTRACT_TAG, help="contract a cert/aa run is frozen under (spec §7.9: contract-v2)"
    )
    p_run.set_defaults(func=cmd_run)
    p_decide = sub.add_parser("decide", help="replay certification evidence into frozen decision records")
    p_decide.add_argument("--runs-dir", type=Path, default=REPO_ROOT / "runs")
    p_decide.add_argument("--contract", type=Path, default=REPO_ROOT / "contracts" / "contract-v1.yaml")
    p_decide.add_argument("--output-dir", type=Path, default=REPO_ROOT / "decisions")
    p_decide.set_defaults(func=cmd_decide)
    p_jev = sub.add_parser("jev-policy", help="replay the amendment 2 Jev report (spec §7.9)")
    p_jev.add_argument("--runs-dir", type=Path, default=REPO_ROOT / "runs")
    p_jev.add_argument("--base-contract", type=Path, default=REPO_ROOT / "contracts" / "contract-v1.yaml")
    p_jev.add_argument("--contract", type=Path, default=REPO_ROOT / "contracts" / "contract-v2.yaml")
    p_jev.add_argument("--output-dir", type=Path, default=REPO_ROOT / "decisions")
    p_jev.set_defaults(func=cmd_jev_policy)
    p_limits = sub.add_parser("risk-limits", help="replay the amendment 3 risk-limit report (spec §7.10)")
    p_limits.add_argument("--runs-dir", type=Path, default=REPO_ROOT / "runs")
    p_limits.add_argument("--base-contract", type=Path, default=REPO_ROOT / "contracts" / "contract-v1.yaml")
    p_limits.add_argument("--jev-contract", type=Path, default=REPO_ROOT / "contracts" / "contract-v2.yaml")
    p_limits.add_argument("--contract", type=Path, default=REPO_ROOT / "contracts" / "contract-v3.yaml")
    p_limits.add_argument("--output-dir", type=Path, default=REPO_ROOT / "decisions")
    p_limits.set_defaults(func=cmd_risk_limits)
    p_latency = sub.add_parser("latency", help="run the sequential descriptive latency study")
    p_latency.add_argument("--client", required=True, help="client city and network type")
    p_latency.add_argument("--rounds", type=int, default=200)
    p_latency.set_defaults(func=cmd_latency)
    p_latency_report = sub.add_parser("latency-report", help="replay exactly one complete latency study")
    p_latency_report.add_argument("--runs-dir", type=Path, default=REPO_ROOT / "runs")
    p_latency_report.add_argument("--output-dir", type=Path, default=REPO_ROOT / "decisions")
    p_latency_report.set_defaults(func=cmd_latency_report)
    p_report = sub.add_parser("report", help="write final-plan own-threshold dev discordance")
    p_report.add_argument("--runs-dir", type=Path, default=REPO_ROOT / "runs")
    p_report.add_argument("--contract", type=Path, default=REPO_ROOT / "contracts" / "contract-v1.yaml")
    p_report.add_argument("--pdisc-json", type=Path, required=True, metavar="PATH")
    p_report.set_defaults(func=cmd_report)
    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
