"""`swapcheck` command line (spec §12)."""

from __future__ import annotations

import argparse
from collections import Counter

from swapcheck import data, prompt
from swapcheck.groups import OUT_OF_SCOPE, load_groups


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="swapcheck")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("data", help="download, verify and split Banking77").set_defaults(func=cmd_data)
    p_prompt = sub.add_parser("prompt", help="check the prompt and generate the Jev translation")
    p_prompt.add_argument("--check", action="store_true", help="fail instead of writing")
    p_prompt.set_defaults(func=cmd_prompt)
    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
