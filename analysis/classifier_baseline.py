"""Classifier baseline (docs/classifier-baseline.md): embeddings plus logistic regression, post hoc.

Steps, each writing under `baselines/embed-lr/`:

    python analysis/classifier_baseline.py embed      # paid: embeds every examples, dev and cert message once
    python analysis/classifier_baseline.py latency    # paid: 100 sequential single-message embedding calls
    python analysis/classifier_baseline.py fit        # local: fits both variants, writes text-free predictions
    python analysis/classifier_baseline.py fit-folds  # local, added after the results: fold-average test predictions
    python analysis/classifier_baseline.py report     # local: prints the Markdown tables from the predictions

The embeddings themselves stay in the git-ignored `data/embeddings/` (derived from message text); the committed
predictions hold item IDs, the predicted intent and its probability only. `fit` and `fit-folds` need the optional
`baseline` dependencies (scikit-learn).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import time
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from statistics import NormalDist, median, quantiles
from typing import Any

import httpx
import numpy as np
from numpy.typing import NDArray

from swapcheck.calibrate import fit_candidate
from swapcheck.cli import load_env
from swapcheck.data import Item, load_splits
from swapcheck.decide import wilson_bounds
from swapcheck.groups import OUT_OF_SCOPE, REPO_ROOT, IntentGroups, load_groups
from swapcheck.outcomes import AnalysisRun, dev_weights
from swapcheck.records import Status

MODEL = "text-embedding-3-small"
PRICE_PER_MTOK = 0.02  # USD, developers.openai.com/api/docs/pricing, read 2026-10-23
URL = "https://api.openai.com/v1/embeddings"
BATCH = 256
OUT_DIR = REPO_ROOT / "baselines" / "embed-lr"
EMBEDDINGS = REPO_ROOT / "data" / "embeddings" / f"{MODEL}.npz"
SEED = 20261023
FOLDS = 5
C_GRID = (0.1, 1.0, 10.0, 100.0, 1000.0)
JOBS = 4  # parallel fits in the C search; 3 GB of RAM leaves room for four copies of the training matrix
LIMITS = tuple(Fraction(p, 100) for p in (1, 2, 5, 10, 15))  # the amendment 3 limits (spec §7.10)
VARIANTS = ("lr-51", "lr-50")  # with and without a trained "none of these" class
LATENCY_CALLS = 100


# --- embed and latency (paid) ----------------------------------------------------------------------------------------


def _all_items(groups: IntentGroups) -> list[Item]:
    splits = load_splits(groups)
    return [*splits["examples"], *splits["dev"], *splits["cert"]]


def _post(client: httpx.Client, key: str, texts: list[str]) -> tuple[dict[str, Any], httpx.Headers, float]:
    for attempt in range(4):
        start = time.perf_counter()
        r = client.post(
            URL,
            headers={"Authorization": f"Bearer {key}"},
            json={"model": MODEL, "input": texts, "encoding_format": "float"},
            timeout=60,
        )
        elapsed = time.perf_counter() - start
        if r.status_code == 200:
            return r.json(), r.headers, elapsed
        if r.status_code not in (429, 500, 502, 503) or attempt == 3:
            raise SystemExit(f"embeddings API {r.status_code}: {r.text[:300]}")
        time.sleep(2**attempt)
    raise AssertionError("unreachable")


def _key() -> str:
    load_env()
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise SystemExit("OPENAI_API_KEY is not set (put it in .env)")
    return key


def cmd_embed(_: argparse.Namespace) -> None:
    items = _all_items(load_groups())
    if EMBEDDINGS.exists():
        raise SystemExit(f"{EMBEDDINGS.relative_to(REPO_ROOT)} exists; delete it to pay for a new embedding run")
    key = _key()
    vectors: list[list[float]] = []
    tokens = 0
    request_ids = []
    with httpx.Client() as client:
        for start in range(0, len(items), BATCH):
            body, headers, _elapsed = _post(client, key, [it.text for it in items[start : start + BATCH]])
            vectors.extend(d["embedding"] for d in sorted(body["data"], key=lambda d: d["index"]))
            tokens += body["usage"]["prompt_tokens"]
            request_ids.append(headers.get("x-request-id"))
    matrix = np.asarray(vectors, dtype=np.float32)
    EMBEDDINGS.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(EMBEDDINGS, item_ids=np.array([it.item_id for it in items]), vectors=matrix)
    meta = {
        "model": MODEL,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "items": len(items),
        "dimensions": int(matrix.shape[1]),
        "prompt_tokens": tokens,
        "cost_usd": tokens * PRICE_PER_MTOK / 1e6,
        "price_per_mtok_usd": PRICE_PER_MTOK,
        "vectors_sha256": hashlib.sha256(matrix.tobytes()).hexdigest(),
        "request_ids": request_ids,
    }
    _write_json(OUT_DIR / "embeddings.json", meta)
    print(f"{len(items)} messages, {tokens} tokens, ${meta['cost_usd']:.4f}")


def cmd_latency(_: argparse.Namespace) -> None:
    """One message per request, one request at a time, like the latency study's LLM calls."""
    cert = load_splits(load_groups())["cert"][:LATENCY_CALLS]
    key = _key()
    rows = []
    tokens = 0
    with httpx.Client() as client:
        _post(client, key, ["Hello"])  # warm the connection, as the latency study does; not recorded
        for it in cert:
            body, headers, elapsed = _post(client, key, [it.text])
            tokens += body["usage"]["prompt_tokens"]
            rows.append(
                {
                    "item_id": it.item_id,
                    "latency_ms": round(elapsed * 1000, 1),
                    "openai_processing_ms": headers.get("openai-processing-ms"),
                }
            )
    _write_json(
        OUT_DIR / "latency.json",
        {
            "model": MODEL,
            "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "calls": rows,
            "prompt_tokens": tokens,
            "cost_usd": tokens * PRICE_PER_MTOK / 1e6,
        },
    )
    ms = [r["latency_ms"] for r in rows]
    print(f"{len(ms)} calls, p50 {median(ms):.0f} ms")


# --- fit (local) -----------------------------------------------------------------------------------------------------


def _label(intent: str, groups: IntentGroups, variant: str) -> str | None:
    """Training label: in-scope intents as themselves; out-of-scope ones as one class (lr-51) or left out (lr-50)."""
    if groups.slice_of(intent) != OUT_OF_SCOPE:
        return intent
    return OUT_OF_SCOPE if variant == "lr-51" else None


def _model(c: float) -> Any:
    from sklearn.linear_model import LogisticRegression

    return LogisticRegression(C=c, max_iter=5000)


def _cv_loss(
    xt: NDArray[np.float32], y: NDArray[Any], c: float, fit_idx: NDArray[np.intp], held: NDArray[np.intp]
) -> float:
    from sklearn.metrics import log_loss

    clf = _model(c).fit(xt[fit_idx], y[fit_idx])
    return float(log_loss(y[held], clf.predict_proba(xt[held]), labels=clf.classes_))


def cmd_fit(_: argparse.Namespace) -> None:
    from joblib import Parallel, delayed
    from sklearn import __version__ as sklearn_version
    from sklearn.model_selection import StratifiedKFold

    groups = load_groups()
    splits = load_splits(groups)
    stored = np.load(EMBEDDINGS)
    row = {str(item_id): i for i, item_id in enumerate(stored["item_ids"])}
    vectors: NDArray[np.float32] = stored["vectors"]

    def x(items: Sequence[Item]) -> NDArray[np.float32]:
        return vectors[[row[it.item_id] for it in items]]

    def predict(clf: Any, items: Sequence[Item]) -> list[dict[str, Any]]:
        proba = clf.predict_proba(x(items))
        top = proba.argmax(axis=1)
        return [
            {"item_id": it.item_id, "intent": str(clf.classes_[k]), "confidence": round(float(p[k]), 6)}
            for it, k, p in zip(items, top, proba, strict=True)
        ]

    examples, dev, cert = splits["examples"], splits["dev"], splits["cert"]
    fit_record: dict[str, Any] = {"sklearn": sklearn_version, "seed": SEED, "folds": FOLDS, "c_grid": list(C_GRID)}
    for variant in VARIANTS:
        train = [it for it in (*examples, *dev) if _label(it.intent, groups, variant) is not None]
        y = np.array([_label(it.intent, groups, variant) for it in train])
        # C by 5-fold cross-validated log loss on the training items, fits in parallel.
        xt = x(train)
        folds = list(StratifiedKFold(FOLDS, shuffle=True, random_state=SEED).split(xt, y))
        jobs = [(c, fit_idx, held_idx) for c in C_GRID for fit_idx, held_idx in folds]
        scores = Parallel(n_jobs=JOBS)(delayed(_cv_loss)(xt, y, c, f, h) for c, f, h in jobs)
        losses = {c: float(np.mean([s for (jc, _, _), s in zip(jobs, scores, strict=True) if jc == c])) for c in C_GRID}
        best = min(C_GRID, key=lambda c: (losses[c], c))
        # Cross-fitted dev predictions: each dev item is predicted by a model that never saw it.
        dev_truth = np.array([_label(it.intent, groups, "lr-51") for it in dev])
        dev_preds: dict[str, dict[str, Any]] = {}
        for _fit_idx, held_idx in StratifiedKFold(FOLDS, shuffle=True, random_state=SEED).split(x(dev), dev_truth):
            held_ids = {dev[i].item_id for i in held_idx}
            fold_train = [it for it in train if it.item_id not in held_ids]
            clf = _model(best).fit(x(fold_train), [_label(it.intent, groups, variant) for it in fold_train])
            for p in predict(clf, [dev[i] for i in held_idx]):
                dev_preds[p["item_id"]] = p
        final = _model(best).fit(x(train), y)
        cert_preds = predict(final, cert)
        start = time.perf_counter()
        final.predict_proba(x(cert))
        per_message_us = (time.perf_counter() - start) / len(cert) * 1e6
        _write_predictions(
            OUT_DIR / f"predictions-{variant}.jsonl.gz",
            [{"split": "dev", **dev_preds[it.item_id]} for it in dev] + [{"split": "cert", **p} for p in cert_preds],
        )
        fit_record[variant] = {
            "train_items": len(train),
            "classes": len(final.classes_),
            "cv_log_loss": {str(c): round(v, 6) for c, v in losses.items()},
            "c": best,
            "predict_us_per_message": round(per_message_us, 2),
        }
        print(f"{variant}: C={best}, train {len(train)}, {len(final.classes_)} classes")
    _write_json(OUT_DIR / "fit.json", fit_record)


def cmd_fit_folds(_: argparse.Namespace) -> None:
    """Added after the results (docs/classifier-baseline.md): `cert` probabilities averaged over the five
    cross-fitting models instead of one model retrained on everything, so the test confidences come from the same
    models whose `dev` predictions set the thresholds. Same C, folds and `dev` predictions as `fit`."""
    from sklearn.model_selection import StratifiedKFold

    groups = load_groups()
    splits = load_splits(groups)
    stored = np.load(EMBEDDINGS)
    row = {str(item_id): i for i, item_id in enumerate(stored["item_ids"])}
    vectors: NDArray[np.float32] = stored["vectors"]

    def x(items: Sequence[Item]) -> NDArray[np.float32]:
        return vectors[[row[it.item_id] for it in items]]

    examples, dev, cert = splits["examples"], splits["dev"], splits["cert"]
    fit_record = json.loads((OUT_DIR / "fit.json").read_text())
    for variant in VARIANTS:
        c = float(fit_record[variant]["c"])
        train = [it for it in (*examples, *dev) if _label(it.intent, groups, variant) is not None]
        dev_truth = np.array([_label(it.intent, groups, "lr-51") for it in dev])
        proba_sum: NDArray[np.float64] | None = None
        classes: Any = None
        for _fit_idx, held_idx in StratifiedKFold(FOLDS, shuffle=True, random_state=SEED).split(x(dev), dev_truth):
            held_ids = {dev[i].item_id for i in held_idx}
            fold_train = [it for it in train if it.item_id not in held_ids]
            clf = _model(c).fit(x(fold_train), [_label(it.intent, groups, variant) for it in fold_train])
            proba = clf.predict_proba(x(cert))
            proba_sum = proba if proba_sum is None else proba_sum + proba
            classes = clf.classes_
        assert proba_sum is not None
        mean = proba_sum / FOLDS
        top = mean.argmax(axis=1)
        with gzip.open(OUT_DIR / f"predictions-{variant}.jsonl.gz", "rt", encoding="utf-8") as f:
            dev_rows = [r for r in map(json.loads, f) if r["split"] == "dev"]
        cert_rows = [
            {"split": "cert", "item_id": it.item_id, "intent": str(classes[k]), "confidence": round(float(p[k]), 6)}
            for it, k, p in zip(cert, top, mean, strict=True)
        ]
        _write_predictions(OUT_DIR / f"predictions-{variant}-folds.jsonl.gz", dev_rows + cert_rows)
        print(f"{variant}-folds: C={c:g}")


# --- report (local, no scikit-learn) ----------------------------------------------------------------------------------


def _run(items: Sequence[Item], preds: dict[str, dict[str, Any]], groups: IntentGroups, split: str) -> AnalysisRun:
    intents = [str(preds[it.item_id]["intent"]) for it in items]
    slices = tuple(groups.slice_of(it.intent) for it in items)
    ok: Status = "ok"
    status = (ok,) * len(items)
    return AnalysisRun(
        "dev" if split == "dev" else "cert",
        tuple(it.item_id for it in items),
        tuple(it.intent for it in items),
        slices,
        status,
        tuple(intents),
        np.array([float(preds[it.item_id]["confidence"]) for it in items]),
        np.array([p != OUT_OF_SCOPE for p in intents], dtype=np.bool_),
        np.array(
            [p == it.intent and s != OUT_OF_SCOPE for p, it, s in zip(intents, items, slices, strict=True)],
            dtype=np.bool_,
        ),
    )


def _accuracy(run: AnalysisRun) -> float:
    in_scope = [i for i, s in enumerate(run.slices) if s != OUT_OF_SCOPE]
    return sum(bool(run.correct[i]) for i in in_scope) / len(in_scope)


def report() -> str:
    groups = load_groups()
    splits = load_splits(groups)
    dev, cert = splits["dev"], splits["cert"]
    dev_counts = dict(Counter(it.intent for it in dev))
    cert_counts = dict(Counter(it.intent for it in cert))
    z = NormalDist().inv_cdf(0.95)
    fit_record = json.loads((OUT_DIR / "fit.json").read_text())
    embed = json.loads((OUT_DIR / "embeddings.json").read_text())
    latency = json.loads((OUT_DIR / "latency.json").read_text())
    head = " | ".join(f"{float(limit) * 100:g}%" for limit in LIMITS)
    lines = [
        f"Automation (misroutes) on the {len(cert):,} test messages at each misroute limit; threshold fitted on "
        "cross-fitted tuning predictions. \\* marks a one-sided 95% Wilson upper bound of W at or above the limit.",
        "",
        f"| Variant | {head} | Top pick right, tuning / test | C |",
        "|---|" + "---:|" * len(LIMITS) + "---:|---:|",
    ]
    names = [*VARIANTS, *(f"{v}-folds" for v in VARIANTS if (OUT_DIR / f"predictions-{v}-folds.jsonl.gz").exists())]
    for name in names:
        preds: dict[str, dict[str, dict[str, Any]]] = {"dev": {}, "cert": {}}
        with gzip.open(OUT_DIR / f"predictions-{name}.jsonl.gz", "rt", encoding="utf-8") as f:
            for line in f:
                p = json.loads(line)
                preds[p["split"]][p["item_id"]] = p
        dev_run, cert_run = _run(dev, preds["dev"], groups, "dev"), _run(cert, preds["cert"], groups, "cert")
        weights = dev_weights(dev_run.truth, dev_counts, cert_counts)
        cells = []
        for limit in LIMITS:
            tau = fit_candidate(dev_run, weights, limit).tau
            auto = cert_run.auto_mask(tau)
            n, wrong, routed = len(cert_run), int(np.count_nonzero(auto & ~cert_run.correct)), int(auto.sum())
            flag = "\\*" if wilson_bounds(wrong, n, z)[1] >= float(limit) else ""
            cells.append(f"{routed / n * 100:.2f} ({wrong / n * 100:.2f}){flag}")
        variant = name.removesuffix("-folds")
        label = f"`{variant}`" + (", fold average†" if name != variant else "")
        lines.append(
            f"| {label} | " + " | ".join(cells) + f" | {_accuracy(dev_run) * 100:.1f}% / "
            f"{_accuracy(cert_run) * 100:.1f}% | {fit_record[variant]['c']:g} |"
        )
    if len(names) > len(VARIANTS):
        lines += [
            "",
            "† Added after the results: test probabilities averaged over the five cross-fitting models, the same "
            "models whose tuning predictions set the thresholds, instead of one model retrained on all items.",
        ]
    ms = [float(c["latency_ms"]) for c in latency["calls"]]
    per_message = embed["prompt_tokens"] / embed["items"] * embed["price_per_mtok_usd"] / 1e6
    lines += [
        "",
        f"Cost: {embed['prompt_tokens']:,} tokens for {embed['items']:,} messages, ${embed['cost_usd']:.4f} in total; "
        f"${per_message * 1000:.4f} per 1,000 messages at ${embed['price_per_mtok_usd']} per million tokens. "
        f"Logistic regression adds {fit_record['lr-51']['predict_us_per_message']:.0f} µs per message on this "
        "machine.",
        f"Latency: {len(ms)} single-message embedding calls from Belgrade, p50 {median(ms):.0f} ms, "
        f"p90 {quantiles(ms, n=10)[-1]:.0f} ms.",
    ]
    return "\n".join(lines)


def cmd_report(_: argparse.Namespace) -> None:
    print(report())


# --- files -----------------------------------------------------------------------------------------------------------


def _write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def _write_predictions(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.GzipFile(path, "wb", mtime=0) as raw:
        raw.write("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows).encode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(required=True)
    commands = (("embed", cmd_embed), ("latency", cmd_latency), ("fit", cmd_fit), ("fit-folds", cmd_fit_folds))
    for name, fn in (*commands, ("report", cmd_report)):
        sub.add_parser(name).set_defaults(fn=fn)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
