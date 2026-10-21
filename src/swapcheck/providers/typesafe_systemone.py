"""TypeSafe System One adapter (`jev-*`; spec §4, §4.1, §9.2)."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any

from swapcheck.configs import Configuration
from swapcheck.prompt import Prompt
from swapcheck.providers.base import HttpRequest
from swapcheck.providers.headers import get_header, select_headers
from swapcheck.records import Parsed, Usage
from swapcheck.schema import jev_design

URL = "https://api.typesafe.ai/v1/systemone"
INTENT_QUESTION = "intent"
MATCH_QUESTION = "match"  # jev-noul: "does the message ask about any catalog topic?"
ALIAS_SUFFIXES = ("-latest", "-preview")
PROBABILITY_SUM_TOLERANCE = 0.01
RATE_LIMIT_NAMES = frozenset({"retry-after", "retry-after-ms"})


class _Invalid(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _unit(answer: Mapping[str, Any], field: str, code_prefix: str) -> float:
    """A required number in [0, 1]; error codes `<code_prefix>_not_numeric` / `<code_prefix>_out_of_range`."""
    if field not in answer:
        raise _Invalid("missing_field")
    value = _number(answer[field])
    if value is None:
        raise _Invalid(f"{code_prefix}_not_numeric")
    if math.isnan(value) or not 0.0 <= value <= 1.0:
        raise _Invalid(f"{code_prefix}_out_of_range")
    return value


def _questions(cfg: Configuration, prompt: Prompt) -> dict[str, Any]:
    design = jev_design(cfg, prompt)
    questions: dict[str, Any] = {INTENT_QUESTION: {"type": "choice", **design["choice"]}}
    if "noul" in design:
        questions[MATCH_QUESTION] = {"type": "noul", "instructions": design["noul"]["instructions"]}
    return questions


class TypeSafeSystemOneAdapter:
    provider = "typesafe"
    api_key_env = "TYPESAFE_API_KEY"

    def auth_headers(self, api_key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key}"}

    def cache_key(self, cfg: Configuration, item_digest: str) -> str | None:
        return None

    def warmup_cache_keys(self, cfg: Configuration) -> list[str | None]:
        return []

    def build_request(self, cfg: Configuration, prompt: Prompt, text: str, cache_key: str | None) -> HttpRequest:
        if cfg.model.endswith(ALIAS_SUFFIXES):
            raise ValueError(f"{cfg.id}: Jev model must be a pinned version ID, not the alias {cfg.model!r}")
        body = {"model": cfg.model, "state": text, "questions": _questions(cfg, prompt)}
        return HttpRequest("POST", URL, {"content-type": "application/json"}, body)

    def parse_response(self, cfg: Configuration, prompt: Prompt, body: Mapping[str, Any]) -> Parsed:
        raw = body.get("usage") or {}
        usage = Usage(uncached_input=raw.get("input_tokens") or 0, output=raw.get("output_tokens") or 0)
        model_id = body.get("model")
        raw_output = json.dumps(body, ensure_ascii=False)
        criteria = list(jev_design(cfg, prompt)["choice"]["criteria"])
        try:
            fields = _answer_fields(body.get("answers"), criteria, cfg.jev_design == "noul")
        except _Invalid as e:
            return Parsed(
                status="invalid_output", error_code=e.code, raw_output=raw_output, model_id=model_id, usage=usage
            )
        return Parsed(status="ok", raw_output=raw_output, model_id=model_id, usage=usage, **fields)

    def request_id(self, headers: Mapping[str, str]) -> str | None:
        return get_header(headers, "x-typesafe-request-id")

    def rate_limit_headers(self, headers: Mapping[str, str]) -> dict[str, str]:
        return select_headers(headers, ("x-ratelimit-",), RATE_LIMIT_NAMES)


def _answer_fields(answers: Any, criteria: list[str], noul: bool) -> dict[str, Any]:
    """`intent`, `confidence`, `probabilities` and (noul) `match_probability`, or raise `_Invalid` (spec §9.2)."""
    expected = {INTENT_QUESTION, MATCH_QUESTION} if noul else {INTENT_QUESTION}
    if not isinstance(answers, Mapping):
        raise _Invalid("missing_answer")
    if expected - set(answers):
        raise _Invalid("missing_answer")
    if set(answers) - expected:
        raise _Invalid("unexpected_answer")
    choice_answer = answers[INTENT_QUESTION]
    if not isinstance(choice_answer, Mapping) or choice_answer.get("type") != "choice":
        raise _Invalid("wrong_answer_type")
    choice = choice_answer.get("choice")
    if choice not in criteria:
        raise _Invalid("unknown_choice")
    confidence = _unit(choice_answer, "confidence", "confidence")
    probabilities = choice_answer.get("probabilities")
    if not isinstance(probabilities, Mapping):
        raise _Invalid("probabilities_missing")
    if set(probabilities) != set(criteria):
        raise _Invalid("probabilities_keys")
    values = {k: _number(v) for k, v in probabilities.items()}
    clean = {k: v for k, v in values.items() if v is not None and math.isfinite(v)}
    if len(clean) != len(values):
        raise _Invalid("probabilities_not_numeric")
    if abs(sum(clean.values()) - 1.0) > PROBABILITY_SUM_TOLERANCE + 1e-9:  # 1e-9: float slack at the bound
        raise _Invalid("probabilities_sum")
    fields: dict[str, Any] = {"intent": choice, "confidence": confidence, "probabilities": clean}
    if noul:
        match_answer = answers[MATCH_QUESTION]
        if not isinstance(match_answer, Mapping) or match_answer.get("type") != "noul":
            raise _Invalid("wrong_answer_type")
        fields["match_probability"] = _unit(match_answer, "noul", "match_probability")
    return fields
