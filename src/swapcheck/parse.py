"""Parser for the LLM structured output `{"intent": <enum>, "confidence": <number>}` (spec §3.2, §9.2)."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Literal

from swapcheck.records import Parsed, Usage

RAW_OUTPUT_CAP = 2_000  # LLM `raw_output` is stored capped (spec §10); Jev, `luna-dec` keep the full response JSON
FIELDS = ("intent", "confidence")


@dataclass(frozen=True)
class ParseResult:
    status: Literal["ok", "invalid_output"]
    error_code: str | None = None  # malformed_json, missing_field, unexpected_field, unknown_intent,
    # confidence_not_numeric, confidence_out_of_range
    intent: str | None = None
    confidence: float | None = None
    case_normalized: bool = False


def _invalid(code: str) -> ParseResult:
    return ParseResult(status="invalid_output", error_code=code)


def match_intent(value: str, enum: list[str]) -> tuple[str, bool] | None:
    """The enum value `value` names: exact match first, else case-insensitive (casefold). None if neither."""
    if value in enum:
        return value, False
    folded = value.casefold()
    for candidate in enum:
        if candidate.casefold() == folded:
            return candidate, True
    return None


def parse_llm_output(text: str, enum: list[str]) -> ParseResult:
    try:
        obj = json.loads(text)
    except ValueError:
        return _invalid("malformed_json")
    if not isinstance(obj, dict):
        return _invalid("malformed_json")
    if any(f not in obj for f in FIELDS):
        return _invalid("missing_field")
    if set(obj) - set(FIELDS):
        return _invalid("unexpected_field")
    intent = obj["intent"]
    matched = match_intent(intent, enum) if isinstance(intent, str) else None
    if matched is None:
        return _invalid("unknown_intent")
    confidence = obj["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, int | float):
        return _invalid("confidence_not_numeric")
    if math.isnan(confidence) or not 0.0 <= confidence <= 1.0:
        return _invalid("confidence_out_of_range")
    return ParseResult(status="ok", intent=matched[0], confidence=float(confidence), case_normalized=matched[1])


def llm_parsed(text: str, enum: list[str], *, stop_reason: str | None, model_id: str | None, usage: Usage) -> Parsed:
    """A completed LLM response: its text parsed against the enum, `raw_output` capped."""
    result = parse_llm_output(text, enum)
    return Parsed(
        status=result.status,
        error_code=result.error_code,
        stop_reason=stop_reason,
        raw_output=text[:RAW_OUTPUT_CAP],
        intent=result.intent,
        confidence=result.confidence,
        case_normalized=result.case_normalized,
        model_id=model_id,
        usage=usage,
    )


def llm_invalid(error_code: str, text: str, *, stop_reason: str | None, model_id: str | None, usage: Usage) -> Parsed:
    """A response that is invalid before parsing (refusal, truncation, content filter)."""
    return Parsed(
        status="invalid_output",
        error_code=error_code,
        stop_reason=stop_reason,
        raw_output=text[:RAW_OUTPUT_CAP],
        model_id=model_id,
        usage=usage,
    )
