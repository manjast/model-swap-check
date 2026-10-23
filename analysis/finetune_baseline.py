"""Fine-tuned encoder baselines (docs/finetune-baseline.md): ModernBERT and SetFit, post hoc.

Training needs the optional `finetune` dependencies (PyTorch); every step is local and free:

    python analysis/finetune_baseline.py train modernbert 50   # five cross-fitting folds; resumes after a stop
    python analysis/finetune_baseline.py train modernbert 51
    python analysis/finetune_baseline.py train setfit 50
    python analysis/finetune_baseline.py train setfit 51
    python analysis/finetune_baseline.py report                # Markdown table from the committed predictions

Each finished fold is saved to the git-ignored `data/finetune/`, so a stopped run continues at the next fold. After
the fifth fold, `train` writes text-free predictions (item ID, predicted intent, its probability) and a run record to
`baselines/<model>/`, in the format of `analysis/classifier_baseline.py`.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import subprocess
import tempfile
import time
from collections.abc import Callable, Sequence
from importlib.metadata import version
from statistics import median, quantiles
from typing import Any

import numpy as np
from classifier_baseline import LIMITS, _write_json, _write_predictions, automation
from numpy.typing import NDArray

from swapcheck.data import Item, load_splits
from swapcheck.groups import OUT_OF_SCOPE, REPO_ROOT, IntentGroups, load_groups

SEED = 20261023  # the classifier baseline's seed: same five folds
FOLDS = 5
MODELS = {  # Hugging Face model and the revision fixed before training
    "modernbert": ("answerdotai/ModernBERT-base", "8949b909ec900327062f0ebf497f51aef5e6f0c8"),
    "setfit": ("sentence-transformers/paraphrase-mpnet-base-v2", "6cc9279c672dc57f94445ef259b28a1b736fec8f"),
}
VARIANTS = ("50", "51")  # without and with a trained "none of these" class
# ModernBERT recipe, fixed before training, no tuning.
MAX_TOKENS = 128  # above the longest message, so nothing is cut
BATCH = 32
LEARNING_RATE = 5e-5
EPOCHS = 10
WEIGHT_DECAY = 0.01
WARMUP = 0.1
# SetFit recipe, fixed before training: the SetFit paper's 20 iterations (pairs per message). SetFit 1.2's own default
# samples every pair combination, millions here.
SETFIT_ITERATIONS = 20
SETFIT_BATCH = 16
SETFIT_EPOCHS = 1
SETFIT_HEAD_MAX_ITER = 5000  # the logistic head's default 100 stops before convergence here; the LR baseline's value
PREDICT_BATCH = 128
LATENCY_CALLS = 100
WORK_DIR = REPO_ROOT / "data" / "finetune"
OUT_ROOT = REPO_ROOT / "baselines"

Predict = Callable[[list[str]], NDArray[np.float32]]


def _label(intent: str, groups: IntentGroups, variant: str) -> str | None:
    """In-scope intents as themselves; out-of-scope ones as one class (51) or left out of training (50)."""
    if groups.slice_of(intent) != OUT_OF_SCOPE:
        return intent
    return OUT_OF_SCOPE if variant == "51" else None


def _folds(dev: Sequence[Item], groups: IntentGroups) -> list[NDArray[np.intp]]:
    """Held-out `dev` indices of the classifier baseline's five folds (stratified on the 51 labels, same seed)."""
    from sklearn.model_selection import StratifiedKFold

    truth = np.array([_label(it.intent, groups, "51") for it in dev])
    folds = StratifiedKFold(FOLDS, shuffle=True, random_state=SEED).split(np.zeros(len(dev)), truth)
    return [held for _, held in folds]


def _device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _train_modernbert(texts: list[str], labels: list[int], n_classes: int, device: str) -> Predict:
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

    name, revision = MODELS["modernbert"]
    torch.manual_seed(SEED)
    tokenizer = AutoTokenizer.from_pretrained(name, revision=revision)
    model = AutoModelForSequenceClassification.from_pretrained(name, revision=revision, num_labels=n_classes)
    model.to(device)
    steps = EPOCHS * math.ceil(len(texts) / BATCH)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE, weight_decay=WEIGHT_DECAY)
    schedule = get_linear_schedule_with_warmup(optimizer, round(WARMUP * steps), steps)
    order = torch.Generator().manual_seed(SEED)
    y = torch.tensor(labels)

    def batch(chunk: list[str]) -> Any:
        return tokenizer(chunk, padding=True, truncation=True, max_length=MAX_TOKENS, return_tensors="pt").to(device)

    model.train()
    start, done = time.perf_counter(), 0
    for epoch in range(EPOCHS):
        for idx in torch.randperm(len(texts), generator=order).split(BATCH):
            loss = model(**batch([texts[i] for i in idx]), labels=y[idx].to(device)).loss
            loss.backward()
            optimizer.step()
            schedule.step()
            optimizer.zero_grad()
            done += 1
            if done == 10 or done % math.ceil(len(texts) / BATCH) == 0:
                elapsed = time.perf_counter() - start
                left = elapsed / done * (steps - done) / 60
                print(f"    epoch {epoch + 1}/{EPOCHS}, step {done}/{steps}, about {left:.0f} min left", flush=True)
    model.eval()

    def predict(chunk: list[str]) -> NDArray[np.float32]:
        out = []
        with torch.no_grad():
            for i in range(0, len(chunk), PREDICT_BATCH):
                logits = model(**batch(chunk[i : i + PREDICT_BATCH])).logits
                out.append(torch.softmax(logits.float(), dim=-1).cpu().numpy())
        return np.concatenate(out).astype(np.float32)

    return predict


def _train_setfit(texts: list[str], labels: list[int], n_classes: int, device: str) -> Predict:
    from datasets import Dataset
    from setfit import SetFitModel, Trainer, TrainingArguments

    name, revision = MODELS["setfit"]
    head = {"max_iter": SETFIT_HEAD_MAX_ITER}
    model = SetFitModel.from_pretrained(name, revision=revision, device=device, head_params=head)
    with tempfile.TemporaryDirectory() as scratch:
        # No checkpoints or logger files: the trainer's defaults write both into the working directory.
        args = TrainingArguments(
            output_dir=scratch,
            save_strategy="no",
            report_to="none",
            batch_size=SETFIT_BATCH,
            num_iterations=SETFIT_ITERATIONS,
            num_epochs=SETFIT_EPOCHS,
            seed=SEED,
        )
        dataset = Dataset.from_dict({"text": texts, "label": labels})
        Trainer(model=model, args=args, train_dataset=dataset).train()
    # Every class is in every fold's training data (the `examples` cover all 50 queues), so the head's columns are
    # the label indices in order.
    assert list(model.model_head.classes_) == list(range(n_classes))

    def predict(chunk: list[str]) -> NDArray[np.float32]:
        return np.asarray(model.predict_proba(chunk, batch_size=PREDICT_BATCH, as_numpy=True), dtype=np.float32)

    return predict


TRAINERS: dict[str, Callable[[list[str], list[int], int, str], Predict]] = {
    "modernbert": _train_modernbert,
    "setfit": _train_setfit,
}


def cmd_train(args: argparse.Namespace) -> None:
    import torch

    groups = load_groups()
    splits = load_splits(groups)
    examples, dev, cert = splits["examples"], splits["dev"], splits["cert"]
    classes = [*groups.in_scope, *([OUT_OF_SCOPE] if args.variant == "51" else [])]
    index = {c: i for i, c in enumerate(classes)}
    name = f"{args.model}-{args.variant}"
    device = _device()
    hardware = torch.cuda.get_device_name(0) if device == "cuda" else platform.processor() or platform.machine()
    where = f"{device} ({hardware})"
    print(f"{name}: {len(classes)} classes on {where}, {torch.get_num_threads()} threads", flush=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    for k, held in enumerate(_folds(dev, groups)):
        path = WORK_DIR / f"{name}-fold{k}.npz"
        if path.exists():
            print(f"  fold {k + 1}/{FOLDS}: done earlier", flush=True)
            continue
        held_ids = {dev[i].item_id for i in held}
        train = [it for it in (*examples, *dev) if it.item_id not in held_ids]
        train = [it for it in train if _label(it.intent, groups, args.variant) is not None]
        print(f"  fold {k + 1}/{FOLDS}: training on {len(train)} messages", flush=True)
        start = time.perf_counter()
        labels = [index[str(_label(it.intent, groups, args.variant))] for it in train]
        predict = TRAINERS[args.model]([it.text for it in train], labels, len(classes), device)
        train_seconds = time.perf_counter() - start
        held_items = [dev[i] for i in held]
        # One message per call, like a router handling messages as they arrive; first fold only.
        latency_ms = []
        if k == 0:
            for it in cert[:LATENCY_CALLS]:
                t = time.perf_counter()
                predict([it.text])
                latency_ms.append((time.perf_counter() - t) * 1000)
        # Written under a temporary name and renamed when complete: a disconnect mid-write must not leave a file that
        # the resume check above takes for a finished fold.
        partial = path.with_name(f"{path.stem}.partial.npz")
        np.savez_compressed(
            partial,
            dev_ids=np.array([it.item_id for it in held_items]),
            dev_proba=predict([it.text for it in held_items]),
            cert_proba=predict([it.text for it in cert]),
            train_items=len(train),
            train_seconds=train_seconds,
            latency_ms=np.array(latency_ms),
            device=where,
        )
        partial.replace(path)
        print(f"  fold {k + 1}/{FOLDS}: {train_seconds / 60:.1f} min", flush=True)
    _assemble(args.model, args.variant, classes, dev, cert)


def _assemble(model: str, variant: str, classes: list[str], dev: Sequence[Item], cert: Sequence[Item]) -> None:
    """Cross-fitted `dev` predictions and fold-average `cert` predictions, as the classifier baseline's `fit-folds`."""
    import torch

    name = f"{model}-{variant}"
    folds = [np.load(WORK_DIR / f"{name}-fold{k}.npz") for k in range(FOLDS)]
    dev_preds: dict[str, dict[str, Any]] = {}
    for fold in folds:
        for item_id, p in zip(fold["dev_ids"], fold["dev_proba"], strict=True):
            dev_preds[str(item_id)] = _row(str(item_id), p, classes)
    mean = np.mean([fold["cert_proba"] for fold in folds], axis=0)
    out = OUT_ROOT / model
    _write_predictions(
        out / f"predictions-{name}.jsonl.gz",
        [{"split": "dev", **dev_preds[it.item_id]} for it in dev]
        + [{"split": "cert", **_row(it.item_id, p, classes)} for it, p in zip(cert, mean, strict=True)],
    )
    record_path = out / "fit.json"
    record = json.loads(record_path.read_text()) if record_path.exists() else {}
    ms = [float(v) for v in folds[0]["latency_ms"]]
    model_id, revision = MODELS[model]
    record[name] = {
        "model": model_id,
        "revision": revision,
        "recipe": _recipe(model),
        "seed": SEED,
        "classes": len(classes),
        "train_items": [int(fold["train_items"]) for fold in folds],
        "train_minutes": [round(float(fold["train_seconds"]) / 60, 1) for fold in folds],
        "device": sorted({str(fold["device"]) for fold in folds}),
        "machine": f"{platform.system()} {platform.machine()}",
        "commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True
        ).stdout.strip(),
        "threads": torch.get_num_threads(),
        "latency_ms": {"calls": len(ms), "p50": round(median(ms), 1), "p90": round(quantiles(ms, n=10)[-1], 1)},
        "versions": {p: version(p) for p in ("torch", "transformers", "sentence-transformers", "setfit")},
    }
    _write_json(record_path, record)
    print(f"{name}: predictions and run record written to {out}")


def _row(item_id: str, proba: NDArray[np.float32], classes: list[str]) -> dict[str, Any]:
    k = int(proba.argmax())
    return {"item_id": item_id, "intent": classes[k], "confidence": round(float(proba[k]), 6)}


def _recipe(model: str) -> dict[str, Any]:
    if model == "modernbert":
        return {
            "max_tokens": MAX_TOKENS,
            "batch": BATCH,
            "learning_rate": LEARNING_RATE,
            "epochs": EPOCHS,
            "weight_decay": WEIGHT_DECAY,
            "warmup": WARMUP,
        }
    return {
        "iterations": SETFIT_ITERATIONS,
        "batch": SETFIT_BATCH,
        "epochs": SETFIT_EPOCHS,
        "head": f"logistic regression, max_iter {SETFIT_HEAD_MAX_ITER}",
    }


def report() -> str:
    groups = load_groups()
    splits = load_splits(groups)
    dev, cert = splits["dev"], splits["cert"]
    head = " | ".join(f"{float(limit) * 100:g}%" for limit in LIMITS)
    lines = [
        f"Automation (misroutes) on the {len(cert):,} test messages at each misroute limit; threshold fitted on "
        "cross-fitted tuning predictions, test probabilities averaged over the five fold models. \\* marks a "
        "one-sided 95% Wilson upper bound of W at or above the limit.",
        "",
        f"| Variant | {head} | Top pick right, tuning / test | Training per fold | Latency p50 |",
        "|---|" + "---:|" * len(LIMITS) + "---:|---:|---:|",
    ]
    for variant in VARIANTS:
        lr = OUT_ROOT / "embed-lr" / f"predictions-lr-{variant}-folds.jsonl.gz"
        cells, accuracy = automation(lr, groups, dev, cert)
        lines.append(f"| `lr-{variant}` (embeddings + LR) | " + " | ".join(cells) + f" | {accuracy} | - | - |")
    machines = set()
    for model in MODELS:
        path = OUT_ROOT / model / "fit.json"
        records = json.loads(path.read_text()) if path.exists() else {}
        for variant in VARIANTS:
            name = f"{model}-{variant}"
            if name not in records:
                continue
            r = records[name]
            cells, accuracy = automation(OUT_ROOT / model / f"predictions-{name}.jsonl.gz", groups, dev, cert)
            minutes, p50 = median(r["train_minutes"]), r["latency_ms"]["p50"]
            lines.append(f"| `{name}` | " + " | ".join(cells) + f" | {accuracy} | {minutes:.1f} min | {p50:.0f} ms |")
            machines.add(f"{', '.join(r['device'])} on {r['machine']}, {r['threads']} threads")
    if machines:
        lines += ["", "Training time and single-message latency measured on: " + "; ".join(sorted(machines)) + "."]
    return "\n".join(lines)


def cmd_report(_: argparse.Namespace) -> None:
    print(report())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(required=True)
    train = sub.add_parser("train")
    train.add_argument("model", choices=MODELS)
    train.add_argument("variant", choices=VARIANTS)
    train.set_defaults(fn=cmd_train)
    sub.add_parser("report").set_defaults(fn=cmd_report)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
