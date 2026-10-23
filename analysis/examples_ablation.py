"""Examples ablation on `dev` (docs/examples-ablation.md): post hoc and descriptive, no verdict.

Compares `inc` with `inc-ex` and `luna-none` with `luna-none-ex`, the same configurations with six catalog
examples replaced (prompts/examples-ablation.md). Prints Markdown: weighted dev automation and misroutes at each
configuration's own 2% threshold (spec §7.8) and at the fixed 0.95; top-pick accuracy on in-scope items with an
exact two-sided sign test on the items whose correctness changed; and, per replaced example, how often the
intent's own items are picked correctly and how many wrong picks it attracts. Reads labels and structured fields
only: no message text.

Usage:
    python analysis/examples_ablation.py [--runs-dir runs]
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from math import comb
from pathlib import Path

from swapcheck.calibrate import fit_candidate
from swapcheck.data import load_splits
from swapcheck.groups import OUT_OF_SCOPE, REPO_ROOT, load_groups
from swapcheck.outcomes import AnalysisRun, build_run, dev_weights, weighted_rates
from swapcheck.prompt import INCUMBENT_PROMPT, PROMPTS_DIR, load_prompt
from swapcheck.records import read_meta, read_rows
from swapcheck.runner import run_validity

ABLATION_PROMPT = PROMPTS_DIR / "examples-ablation.md"
PAIRS = (("inc", "inc-ex"), ("luna-none", "luna-none-ex"))
POLICY_LIMIT = Fraction(1, 50)  # spec §7.8
FIXED_TAU = 0.95  # the incumbent's registered threshold, kept by the naive swap (D-A1)


@dataclass(frozen=True)
class DevData:
    runs: dict[str, AnalysisRun]
    dev_counts: dict[str, int]
    cert_counts: dict[str, int]


def swapped_intents() -> list[str]:
    old, new = load_prompt(INCUMBENT_PROMPT), load_prompt(ABLATION_PROMPT)
    return [a.intent for a, b in zip(old.catalog, new.catalog, strict=True) if a.example != b.example]


def load_dev(runs_dir: Path, config_ids: set[str]) -> DevData:
    """The one complete, valid dev run of each configuration; API-error items are dropped (they have no outcome)."""
    groups = load_groups()
    splits = load_splits(groups)
    ablation_sha = load_prompt(ABLATION_PROMPT).sha256()
    found: dict[str, list[AnalysisRun]] = {cid: [] for cid in config_ids}
    for run_dir in sorted(p for p in runs_dir.iterdir() if (p / "run.json").exists()):
        meta = read_meta(run_dir)
        if meta.split != "dev" or meta.config_id not in config_ids:
            continue
        rows = read_rows(run_dir)
        ok, why = run_validity(meta, rows)
        if not ok:
            raise SystemExit(f"{meta.run_id}: {why}")
        if meta.config_id.endswith("-ex") and meta.prompt_sha256 != ablation_sha:
            raise SystemExit(f"{meta.run_id}: prompt is not prompts/examples-ablation.md")
        run = build_run(splits["dev"], rows, split="dev", groups=groups, complete=meta.complete)
        found[meta.config_id].append(run.take([i for i, s in enumerate(run.status) if s != "api_error"]))
    for cid, runs in found.items():
        if len(runs) != 1:
            raise SystemExit(f"{cid}: expected one dev run, found {len(runs)}")
    return DevData(
        {cid: runs[0] for cid, runs in found.items()},
        dict(Counter(i.intent for i in splits["dev"])),
        dict(Counter(i.intent for i in splits["cert"])),
    )


def sign_test(b: int, c: int) -> float:
    """Exact two-sided sign test on b items that improved and c that got worse."""
    n = b + c
    if n == 0:
        return 1.0
    tail = Fraction(sum(comb(n, k) for k in range(min(b, c) + 1)), 1 << n)
    return float(min(Fraction(1), 2 * tail))


def _pct(value: Fraction | float) -> str:
    return f"{float(value) * 100:.2f}%"


def thresholds_table(d: DevData) -> list[str]:
    lines = [
        "| Configuration | τ at the 2% limit | A at the limit | W at the limit | A at 0.95 | W at 0.95 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for pair in PAIRS:
        for cid in pair:
            run = d.runs[cid]
            weights = dev_weights(run.truth, d.dev_counts, d.cert_counts)
            cal = fit_candidate(run, weights, POLICY_LIMIT)
            fixed = weighted_rates(run, FIXED_TAU, weights)
            lines.append(
                f"| `{cid}` | {cal.tau:.2f} | {_pct(cal.automation)} | {_pct(cal.wrong)} "
                f"| {_pct(fixed.automation)} | {_pct(fixed.wrong)} |"
            )
    return lines


def accuracy_lines(d: DevData, base: str, variant: str) -> list[str]:
    old, new = d.runs[base], d.runs[variant]
    new_index = {item_id: i for i, item_id in enumerate(new.item_ids)}
    pairs = [
        (i, new_index[item_id])
        for i, item_id in enumerate(old.item_ids)
        if item_id in new_index and old.slices[i] != OUT_OF_SCOPE
    ]
    old_right = sum(bool(old.correct[i]) for i, _ in pairs)
    new_right = sum(bool(new.correct[j]) for _, j in pairs)
    better = sum(bool(new.correct[j] and not old.correct[i]) for i, j in pairs)
    worse = sum(bool(old.correct[i] and not new.correct[j]) for i, j in pairs)
    n = len(pairs)
    return [
        f"`{base}` → `{variant}`: top pick right on {_pct(old_right / n)} → {_pct(new_right / n)} of {n} in-scope "
        f"items answered in both runs; {better} items improved, {worse} got worse (sign test p = "
        f"{sign_test(better, worse):.2g})."
    ]


def intent_table(d: DevData, intents: list[str]) -> list[str]:
    head = " | ".join(f"`{cid}`" for pair in PAIRS for cid in pair)
    lines = [
        "Per replaced example: own items picked right / wrong picks attracted (all dev items, out of scope included).",
        "",
        f"| Intent | {head} |",
        "|---|" + "---:|" * (2 * len(PAIRS)),
    ]
    for intent in intents:
        cells = []
        for pair in PAIRS:
            for cid in pair:
                run = d.runs[cid]
                own = [bool(c) for t, c in zip(run.truth, run.correct, strict=True) if t == intent]
                attracted = sum(
                    1
                    for t, p, s in zip(run.truth, run.intent, run.status, strict=True)
                    if s == "ok" and p == intent and t != intent
                )
                cells.append(f"{_pct(sum(own) / len(own))} / {attracted}")
        lines.append(f"| `{intent}` | " + " | ".join(cells) + " |")
    return lines


def report(runs_dir: Path) -> str:
    d = load_dev(runs_dir, {cid for pair in PAIRS for cid in pair})
    intents = swapped_intents()
    return "\n".join(
        [
            *thresholds_table(d),
            "",
            *(line for base, variant in PAIRS for line in accuracy_lines(d, base, variant)),
            "",
            *intent_table(d, intents),
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs-dir", type=Path, default=REPO_ROOT / "runs")
    print(report(parser.parse_args().runs_dir))


if __name__ == "__main__":
    main()
