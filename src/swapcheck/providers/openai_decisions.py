"""OpenAI Decisions API adapter (`luna-dec`; spec §3.2, §4, §4.2, §9.2)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from swapcheck.configs import Configuration
from swapcheck.prompt import DECISIONS_QUESTION, Prompt
from swapcheck.providers.answers import InvalidAnswer, probability_map, unit
from swapcheck.providers.base import HttpRequest
from swapcheck.providers.headers import get_header, select_headers
from swapcheck.providers.openai_responses import RATE_LIMIT_NAMES, openai_usage
from swapcheck.records import Parsed
from swapcheck.schema import decisions_design

URL = "https://api.openai.com/v1/decisions"


class OpenAIDecisionsAdapter:
    provider = "openai"
    api_key_env = "OPENAI_API_KEY"

    def auth_headers(self, api_key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key}"}

    def cache_key(self, cfg: Configuration, item_digest: str) -> str | None:
        return None

    def warmup_cache_keys(self, cfg: Configuration) -> list[str | None]:
        return []  # no cache to warm (spec §4)

    def build_request(self, cfg: Configuration, prompt: Prompt, text: str, cache_key: str | None) -> HttpRequest:
        """Exactly `model`, `input` and `questions`: the endpoint has no sampling, reasoning, token-limit or
        storage parameters, and no cache parameters are sent (spec §4)."""
        body = {"model": cfg.model, "input": text, **decisions_design(cfg, prompt)}
        return HttpRequest("POST", URL, {"content-type": "application/json"}, body)

    def parse_response(self, cfg: Configuration, prompt: Prompt, body: Mapping[str, Any]) -> Parsed:
        usage = openai_usage(body.get("usage") or {})
        model_id = body.get("model")
        raw_output = json.dumps(body, ensure_ascii=False)
        (question,) = decisions_design(cfg, prompt)["questions"]
        values = [c["value"] for c in question["choices"]]
        try:
            fields = _answer_fields(body.get("answers"), values)
        except InvalidAnswer as e:
            return Parsed(
                status="invalid_output", error_code=e.code, raw_output=raw_output, model_id=model_id, usage=usage
            )
        return Parsed(status="ok", raw_output=raw_output, model_id=model_id, usage=usage, **fields)

    def request_id(self, headers: Mapping[str, str]) -> str | None:
        return get_header(headers, "x-request-id")

    def rate_limit_headers(self, headers: Mapping[str, str]) -> dict[str, str]:
        return select_headers(headers, ("x-ratelimit-",), RATE_LIMIT_NAMES)


def _answer_fields(answers: Any, values: list[str]) -> dict[str, Any]:
    """`intent`, `confidence` and `probabilities` (value -> probability), or raise `InvalidAnswer` (§9.2)."""
    if not isinstance(answers, list) or not answers:
        raise InvalidAnswer("missing_answer")
    if len(answers) > 1:
        raise InvalidAnswer("unexpected_answer")
    (answer,) = answers
    if not isinstance(answer, Mapping) or answer.get("name") != DECISIONS_QUESTION:
        raise InvalidAnswer("wrong_answer_name")
    if answer.get("type") == "refusal":
        raise InvalidAnswer("refusal")
    if answer.get("type") != "choice":
        raise InvalidAnswer("wrong_answer_type")
    choice = answer.get("choice")
    if not isinstance(choice, str) or choice not in values:
        raise InvalidAnswer("unknown_choice")
    confidence = unit(answer, "confidence", "confidence")
    entries = answer.get("probabilities")
    if not isinstance(entries, list):
        raise InvalidAnswer("probabilities_missing")
    probabilities: dict[str, Any] = {}
    for entry in entries:
        value = entry.get("value") if isinstance(entry, Mapping) else None
        if not isinstance(value, str) or value in probabilities:
            raise InvalidAnswer("probabilities_keys")
        probabilities[value] = entry.get("probability")
    return {"intent": choice, "confidence": confidence, "probabilities": probability_map(probabilities, values)}
