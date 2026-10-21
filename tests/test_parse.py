from __future__ import annotations

import pytest

from swapcheck.parse import parse_llm_output
from swapcheck.prompt import Prompt


def test_p1_valid_output_is_ok(incumbent: Prompt) -> None:
    result = parse_llm_output('{"intent": "card_arrival", "confidence": 0.93}', incumbent.enum)
    assert (result.status, result.error_code, result.intent, result.confidence) == ("ok", None, "card_arrival", 0.93)
    assert not result.case_normalized


@pytest.mark.parametrize("confidence", ["0", "1", "1.0", "0.5"])
def test_p1_confidence_bounds_are_inclusive_and_ints_accepted(incumbent: Prompt, confidence: str) -> None:
    result = parse_llm_output(f'{{"intent": "out_of_scope", "confidence": {confidence}}}', incumbent.enum)
    assert result.status == "ok"
    assert isinstance(result.confidence, float)


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ('{"intent": "card_arrival", "confidence": 0.9', "malformed_json"),
        ("", "malformed_json"),
        ('["card_arrival", 0.9]', "malformed_json"),
        ('"card_arrival"', "malformed_json"),
        ('{"intent": "card_arrival"}', "missing_field"),
        ('{"confidence": 0.9}', "missing_field"),
        ('{"intent": "card_arrival", "confidence": 0.9, "reason": "x"}', "unexpected_field"),
        ('{"intent": "not_an_intent", "confidence": 0.9}', "unknown_intent"),
        ('{"intent": null, "confidence": 0.9}', "unknown_intent"),
        ('{"intent": "card arrival", "confidence": 0.9}', "unknown_intent"),
        ('{"intent": "card_arrival", "confidence": -0.01}', "confidence_out_of_range"),
        ('{"intent": "card_arrival", "confidence": 1.01}', "confidence_out_of_range"),
        ('{"intent": "card_arrival", "confidence": NaN}', "confidence_out_of_range"),
        ('{"intent": "card_arrival", "confidence": Infinity}', "confidence_out_of_range"),
        ('{"intent": "card_arrival", "confidence": "0.9"}', "confidence_not_numeric"),
        ('{"intent": "card_arrival", "confidence": true}', "confidence_not_numeric"),
        ('{"intent": "card_arrival", "confidence": null}', "confidence_not_numeric"),
    ],
)
def test_p2_invalid_llm_output_codes(incumbent: Prompt, text: str, code: str) -> None:
    result = parse_llm_output(text, incumbent.enum)
    assert (result.status, result.error_code) == ("invalid_output", code)
    assert result.intent is None and result.confidence is None


def test_p3_case_insensitive_enum_match_is_normalized_and_flagged(incumbent: Prompt) -> None:
    assert "Refund_not_showing_up" in incumbent.enum
    result = parse_llm_output('{"intent": "refund_not_showing_up", "confidence": 0.8}', incumbent.enum)
    assert (result.status, result.intent, result.case_normalized) == ("ok", "Refund_not_showing_up", True)
    exact = parse_llm_output('{"intent": "Refund_not_showing_up", "confidence": 0.8}', incumbent.enum)
    assert (exact.intent, exact.case_normalized) == ("Refund_not_showing_up", False)


def test_p3_exact_match_wins_over_case_insensitive_match() -> None:
    enum = ["Topic", "topic", "out_of_scope"]
    result = parse_llm_output('{"intent": "topic", "confidence": 0.5}', enum)
    assert (result.intent, result.case_normalized) == ("topic", False)
