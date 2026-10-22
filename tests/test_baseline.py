from __future__ import annotations

import math
from fractions import Fraction

import pytest

from swapcheck.baseline import TextIntent, check_competence, fold_diagnostics, leave_one_out

# T-B1: six documents, two labels. Every raw TF and per-fold df below is
# enumerated by hand, independently of tokenization or vectorizer helpers.
CORPUS: tuple[TextIntent, ...] = (
    ("red red", "a"),
    ("red", "a"),
    ("red blue", "a"),
    ("blue blue", "b"),
    ("blue", "b"),
    ("blue red", "b"),
)
TF: tuple[dict[str, int], ...] = (
    {"red": 2, "red red": 1},
    {"red": 1},
    {"red": 1, "blue": 1, "red blue": 1},
    {"blue": 2, "blue blue": 1},
    {"blue": 1},
    {"blue": 1, "red": 1, "blue red": 1},
)
# Coordinates: blue, blue blue, blue red, red, red blue, red red.
TERMS = ("blue", "blue blue", "blue red", "red", "red blue", "red red")
FOLD_DF = (
    (4, 1, 1, 3, 1, 0),
    (4, 1, 1, 3, 1, 1),
    (3, 1, 1, 3, 0, 1),
    (3, 0, 1, 4, 1, 1),
    (3, 1, 1, 4, 1, 1),
    (3, 1, 0, 3, 1, 1),
)
PREDICTIONS = ("a", "a", "b", "b", "b", "a")


@pytest.mark.parametrize("held_out", range(6))
def test_b1_hand_idf_vectors_centroids_and_cosines(held_out: int) -> None:
    actual = fold_diagnostics(CORPUS, held_out)
    # N=5 always, not six; absent training features have no vocabulary entry.
    idf = {
        term: 1 + math.log(6 / (1 + frequency))
        for term, frequency in zip(TERMS, FOLD_DF[held_out], strict=True)
        if frequency
    }
    assert dict(actual.idf) == pytest.approx(idf)
    assert actual.held_out == held_out
    assert set(actual.training_vectors) == set(range(6)) - {held_out}

    expected_vectors: list[dict[str, float]] = []
    for raw in TF:
        squared_length = sum((raw.get(term, 0) * value) ** 2 for term, value in idf.items())
        expected_vectors.append(
            {term: raw[term] * value / math.sqrt(squared_length) for term, value in idf.items() if term in raw}
        )
    assert dict(actual.held_out_vector) == pytest.approx(expected_vectors[held_out])
    for row, vector in actual.training_vectors.items():
        assert dict(vector) == pytest.approx(expected_vectors[row])
        assert sum(value**2 for value in vector.values()) == pytest.approx(1)

    for label in ("a", "b"):
        rows = [row for row in range(6) if row != held_out and CORPUS[row][1] == label]
        # Sparse means keep only coordinates that occur in the class.
        mean = {
            term: sum(expected_vectors[row].get(term, 0.0) for row in rows) / len(rows)
            for term in idf
            if any(term in expected_vectors[row] for row in rows)
        }
        assert dict(actual.centroids[label]) == pytest.approx(mean)
        cosine = sum(expected_vectors[held_out].get(term, 0) * value for term, value in mean.items()) / math.sqrt(
            sum(value**2 for value in mean.values())
        )
        assert actual.similarities[label] == pytest.approx(cosine)
    assert actual.prediction == PREDICTIONS[held_out]


def test_b1_fold_zero_explicit_scalar_oracle() -> None:
    fold = fold_diagnostics(CORPUS, 0)
    r = 1 + math.log(6 / 4)
    b = 1 + math.log(6 / 5)
    rare = 1 + math.log(3)
    mixed_norm = math.sqrt(r * r + b * b + rare * rare)
    blue_norm = math.sqrt(4 * b * b + rare * rare)
    # Held-out-only 'red red' disappears, so the query is the red unit vector.
    assert dict(fold.held_out_vector) == {"red": 1.0}
    assert fold.training_vectors[2]["red"] == pytest.approx(r / mixed_norm)
    assert fold.training_vectors[3]["blue"] == pytest.approx(2 * b / blue_norm)
    a_red = (1 + r / mixed_norm) / 2
    a_blue = b / mixed_norm / 2
    a_bigram = rare / mixed_norm / 2
    a_cosine = a_red / math.sqrt(a_red**2 + a_blue**2 + a_bigram**2)
    b_red = r / mixed_norm / 3
    b_blue = (2 * b / blue_norm + 1 + b / mixed_norm) / 3
    b_cosine = b_red / math.sqrt(b_red**2 + b_blue**2 + (rare / blue_norm / 3) ** 2 + (rare / mixed_norm / 3) ** 2)
    assert fold.similarities == pytest.approx({"a": a_cosine, "b": b_cosine})
    assert a_cosine > b_cosine


def test_b1_leave_one_out_predictions_and_strict_same_item_competence() -> None:
    assert leave_one_out(CORPUS) == PREDICTIONS
    equal = check_competence(CORPUS, PREDICTIONS)
    assert equal.baseline_predictions == PREDICTIONS
    assert equal.baseline_accuracy == equal.incumbent_accuracy == Fraction(2, 3)
    assert not equal.passed
    better = check_competence(CORPUS, ("a", "a", "a", "b", "b", "a"))
    assert better.incumbent_accuracy == Fraction(5, 6)
    assert better.passed
    oos = check_competence(CORPUS, ("out_of_scope", "a", "a", "b", "b", None))
    assert oos.incumbent_accuracy == Fraction(2, 3)
    assert not oos.passed


def test_b1_tokens_raw_counts_and_cross_punctuation_bigrams() -> None:
    corpus = (("DON'T, Pay42! don't", "a"), ("don't pay42", "a"), ("OTHER", "b"))
    fold = fold_diagnostics(corpus, 2)
    assert set(fold.idf) == {"don't", "pay42", "don't pay42", "pay42 don't"}
    rare = 1 + math.log(3 / 2)
    norm = math.sqrt(4 + 1 + 1 + rare**2)
    assert dict(fold.training_vectors[0]) == pytest.approx(
        {"don't": 2 / norm, "pay42": 1 / norm, "don't pay42": 1 / norm, "pay42 don't": rare / norm}
    )
    assert dict(fold.held_out_vector) == {}
    assert fold.similarities == {"a": 0.0}


def test_b1_zero_vectors_and_ties_use_sorted_training_labels() -> None:
    corpus = (("???", "z"), ("", "b"), ("", "a"))
    fold = fold_diagnostics(corpus, 0)
    assert fold.idf == {}
    assert fold.centroids == {"a": {}, "b": {}}
    assert fold.similarities == {"a": 0.0, "b": 0.0}
    assert fold.prediction == "a"
    # Nonzero identical vectors also tie; row order does not break the tie.
    assert fold_diagnostics((("same", "z"), ("same", "b"), ("same", "a")), 0).prediction == "a"


def test_b1_pure_functions_leave_inputs_unchanged() -> None:
    items = list(CORPUS)
    predictions = list(PREDICTIONS)
    check_competence(items, predictions)
    assert items == list(CORPUS)
    assert predictions == list(PREDICTIONS)


def test_b1_rejects_unaligned_predictions_oos_truth_and_small_corpus() -> None:
    with pytest.raises(ValueError, match="align"):
        check_competence(CORPUS, ("a",))
    with pytest.raises(ValueError, match="in-scope truths"):
        leave_one_out((("one", "a"), ("two", "out_of_scope")))
    with pytest.raises(ValueError, match="at least two"):
        leave_one_out((("one", "a"),))
    with pytest.raises(ValueError, match="at least two"):
        leave_one_out(())
    for index in (-1, 6):
        with pytest.raises(IndexError, match="outside"):
            fold_diagnostics(CORPUS, index)
