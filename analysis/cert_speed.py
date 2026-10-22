"""Cost and speed of the `cert` runs (docs/cert.md): one row per configuration in runs/manifest.yaml.

Prints Markdown with the §11 cost model (billed, steady, sparse), tokens per message, the wall-clock latency
of the final attempt as in the decision records, and OpenAI's server time (`openai-processing-ms`, the only
provider that sends one). Only structured fields of the run records are read: no message text.

Usage:
    python analysis/cert_speed.py [--runs-dir runs]
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from swapcheck import cost
from swapcheck.configs import load_configurations
from swapcheck.manifest import load_manifest
from swapcheck.records import read_meta, read_rows


def _q(values: Sequence[float], q: float) -> float:
    return float(np.quantile(np.asarray(values, dtype=float), q, method="higher"))


def _pair(values: Sequence[float], unit: float) -> str:
    return f"{_q(values, 0.5) / unit:.2f}/{_q(values, 0.95) / unit:.2f}" if values else "-"


def _usd(v: float | None) -> str:
    return "-" if v is None else f"{v:.3f}"


def report(runs_dir: Path) -> str:
    configs = load_configurations()
    prices = cost.load_prices()
    lines = [
        "| Configuration | Model | Billed $/1,000 | Steady $/1,000 | Sparse $/1,000 "
        "| Input/output tokens per message | Wall clock p50/p95 s | Server p50/p95 s |",
        "|---|---|---:|---:|---:|---|---|---|",
    ]
    for entry in load_manifest(runs_dir).runs:
        if entry.split != "cert":
            continue
        run_dir = runs_dir / entry.run_id
        meta, rows = read_meta(run_dir), read_rows(run_dir)
        cfg = configs[meta.config_id]
        model = cost.cost_model(cfg, rows, meta.warmups, prices)
        tokens = model.tokens
        inputs = sum(tokens[c].mean for c in ("uncached_input", "cache_read", "cache_write"))
        wall = [r.latency_ms for r in rows if r.latency_ms is not None]
        server = [
            float(r.attempts[-1].headers["openai-processing-ms"])
            for r in rows
            if r.attempts and "openai-processing-ms" in r.attempts[-1].headers
        ]
        lines.append(
            f"| `{cfg.id}` | `{cfg.model}` | {_usd(model.billed_per_1000)} | {_usd(model.steady_per_1000)} "
            f"| {_usd(model.sparse_per_1000)} | {inputs:,.0f}/{tokens['output'].mean:,.1f} "
            f"| {_pair(wall, 1000)} | {_pair(server, 1000)} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    print(report(parser.parse_args().runs_dir))


if __name__ == "__main__":
    main()
