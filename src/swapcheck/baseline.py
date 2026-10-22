"""Pure leave-one-out competence baseline (spec §3.4).

Inputs are already-selected in-scope (text, intent) pairs, in evaluation order;
OOS truths are rejected rather than silently changing the comparison population.
Each fold fits vocabulary and IDF ln((1+N)/(1+df))+1 on training items only:
N is the number of documents remaining after holding one out, and df counts
those training documents containing the feature (not tokens or whole intents).
TF is the raw count of lowercase ``[a-z0-9']+`` tokens and adjacent bigrams
(joined by a space); held-out-only features are ignored. Documents are L2
normalized before arithmetic-mean centroids are formed. Comparison uses cosine
with those means, not an unnormalized dot product. Empty vectors have cosine
zero, and exact score ties choose the lexicographically smallest training label.
An intent with no remaining training documents has no centroid in that fold.
Incumbent predictions are positional on these same items; None and OOS are wrong.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise

from swapcheck.groups import OUT_OF_SCOPE

_TOKEN = re.compile(r"[a-z0-9']+")
type TextIntent = tuple[str, str]
type SparseVector = Mapping[str, float]


@dataclass(frozen=True)
class FoldDiagnostics:
    """Sparse coordinates omit zeroes; training-vector indices refer to input rows."""

    held_out: int
    idf: Mapping[str, float]
    training_vectors: Mapping[int, SparseVector]
    held_out_vector: SparseVector
    centroids: Mapping[str, SparseVector]
    similarities: Mapping[str, float]
    prediction: str


@dataclass(frozen=True)
class CompetenceCheck:
    baseline_predictions: tuple[str, ...]
    baseline_accuracy: Fraction
    incumbent_accuracy: Fraction
    passed: bool


def _counts(text: str) -> Counter[str]:
    tokens = _TOKEN.findall(text.lower())
    counts = Counter(tokens)
    counts.update(f"{left} {right}" for left, right in pairwise(tokens))
    return counts


def _prepare(items: Sequence[TextIntent]) -> tuple[tuple[Counter[str], ...], Counter[str]]:
    if len(items) < 2:
        raise ValueError("leave-one-out requires at least two in-scope items")
    if any(intent == OUT_OF_SCOPE for _, intent in items):
        raise ValueError("baseline inputs must contain only in-scope truths")
    counts = tuple(_counts(text) for text, _ in items)
    df: Counter[str] = Counter()
    for document in counts:
        df.update(document.keys())
    return counts, df


def _normalize(counts: Mapping[str, int], idf: Mapping[str, float]) -> dict[str, float]:
    vector = {term: count * idf[term] for term, count in counts.items() if term in idf}
    norm = math.sqrt(sum(value * value for value in vector.values()))
    if norm:
        for term in vector:
            vector[term] /= norm
    return vector


def _fold(
    items: Sequence[TextIntent],
    counts: tuple[Counter[str], ...],
    df: Counter[str],
    held_out: int,
) -> FoldDiagnostics:
    # Global document frequencies minus this row are exactly the training-fold df.
    training_size = len(items) - 1
    idf = {
        term: math.log((1 + training_size) / (1 + fold_df)) + 1
        for term, frequency in df.items()
        if (fold_df := frequency - int(term in counts[held_out])) > 0
    }
    vectors: dict[int, SparseVector] = {}
    sums: dict[str, dict[str, float]] = {}
    sizes: Counter[str] = Counter()
    for index, (_, label) in enumerate(items):
        if index == held_out:
            continue
        vector = _normalize(counts[index], idf)
        vectors[index] = vector
        centroid_sum = sums.setdefault(label, {})
        sizes[label] += 1
        for term, value in vector.items():
            centroid_sum[term] = centroid_sum.get(term, 0.0) + value
    centroids = {label: {term: value / sizes[label] for term, value in sums[label].items()} for label in sorted(sums)}
    query = _normalize(counts[held_out], idf)
    similarities: dict[str, float] = {}
    for label, centroid in centroids.items():
        norm = math.sqrt(sum(value * value for value in centroid.values()))
        similarities[label] = (
            sum(value * centroid.get(term, 0.0) for term, value in query.items()) / norm if norm else 0.0
        )
    prediction = max(similarities, key=lambda label: similarities[label])
    return FoldDiagnostics(held_out, idf, vectors, query, centroids, similarities, prediction)


def fold_diagnostics(items: Sequence[TextIntent], held_out: int) -> FoldDiagnostics:
    """Fit one fold, exposing IDF, normalized vectors, means, cosine and top-1."""
    counts, df = _prepare(items)
    if not 0 <= held_out < len(items):
        raise IndexError("held-out index is outside the corpus")
    return _fold(items, counts, df, held_out)


def leave_one_out(items: Sequence[TextIntent]) -> tuple[str, ...]:
    """Predict each original row without training on that row's text or label."""
    counts, df = _prepare(items)
    return tuple(_fold(items, counts, df, index).prediction for index in range(len(items)))


def check_competence(items: Sequence[TextIntent], incumbent_predictions: Sequence[str | None]) -> CompetenceCheck:
    """Require strictly greater same-item top-1 accuracy; confidence is irrelevant."""
    if len(items) != len(incumbent_predictions):
        raise ValueError("incumbent predictions must align with every baseline item")
    predictions = leave_one_out(items)
    baseline_correct = sum(prediction == item[1] for item, prediction in zip(items, predictions, strict=True))
    incumbent_correct = sum(
        prediction == item[1] for item, prediction in zip(items, incumbent_predictions, strict=True)
    )
    return CompetenceCheck(
        predictions,
        Fraction(baseline_correct, len(items)),
        Fraction(incumbent_correct, len(items)),
        incumbent_correct > baseline_correct,
    )
