"""OpenAI Responses API adapter (`inc`, `luna-*`; spec §4)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from swapcheck.configs import Configuration
from swapcheck.parse import llm_invalid, llm_parsed
from swapcheck.prompt import Prompt
from swapcheck.providers.base import HttpRequest
from swapcheck.providers.headers import get_header, select_headers
from swapcheck.records import Parsed, Usage
from swapcheck.schema import llm_output_schema

URL = "https://api.openai.com/v1/responses"
SCHEMA_NAME = "routing"
INCOMPLETE_CODES = {"max_output_tokens": "truncated", "content_filter": "content_filter"}
RATE_LIMIT_NAMES = frozenset({"retry-after", "openai-processing-ms"})


def _key_routed(cfg: Configuration) -> bool:
    """Pre-GPT-5.6 models (`inc`): implicit caching routed by `prompt_cache_key`, no `prompt_cache_options`."""
    return cfg.prompt_cache_keys is not None


class OpenAIResponsesAdapter:
    provider = "openai"
    api_key_env = "OPENAI_API_KEY"

    def auth_headers(self, api_key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key}"}

    def cache_key(self, cfg: Configuration, item_digest: str) -> str | None:
        if cfg.prompt_cache_keys is None:
            return None
        return f"msc-{int(item_digest, 16) % cfg.prompt_cache_keys}"

    def warmup_cache_keys(self, cfg: Configuration) -> list[str | None]:
        if cfg.prompt_cache_keys is None:
            return [None]
        return [f"msc-{i}" for i in range(cfg.prompt_cache_keys)]

    def build_request(self, cfg: Configuration, prompt: Prompt, text: str, cache_key: str | None) -> HttpRequest:
        developer_part: dict[str, Any] = {"type": "input_text", "text": prompt.developer_message()}
        if cfg.cache_mode == "explicit":
            developer_part["prompt_cache_breakpoint"] = {"mode": "explicit"}
        body: dict[str, Any] = {
            "model": cfg.model,
            "store": False,
            "input": [
                {"role": "developer", "content": [developer_part]},
                {"role": "user", "content": text},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": SCHEMA_NAME,
                    "strict": True,
                    "schema": llm_output_schema(prompt),
                }
            },
            "max_output_tokens": cfg.max_output_tokens,
        }
        if cfg.temperature is not None:
            body["temperature"] = cfg.temperature
        if cfg.reasoning_effort is not None:
            body["reasoning"] = {"effort": cfg.reasoning_effort}
        if cfg.cache_mode == "explicit":
            options: dict[str, Any] = {"mode": "explicit"}
            if cfg.cache_ttl is not None:
                options["ttl"] = cfg.cache_ttl
            body["prompt_cache_options"] = options
        elif cfg.cache_mode == "implicit" and not _key_routed(cfg):
            body["prompt_cache_options"] = {"mode": "implicit"}
        if cache_key is not None:
            body["prompt_cache_key"] = cache_key
        return HttpRequest("POST", URL, {"content-type": "application/json"}, body)

    def parse_response(self, cfg: Configuration, prompt: Prompt, body: Mapping[str, Any]) -> Parsed:
        usage = _usage(body.get("usage") or {})
        model_id = body.get("model")
        status = body.get("status")
        incomplete_reason = (body.get("incomplete_details") or {}).get("reason")
        stop_reason = incomplete_reason if status == "incomplete" and incomplete_reason else status
        message = next((o for o in body.get("output") or [] if o.get("type") == "message"), None)
        parts: list[Mapping[str, Any]] = (message or {}).get("content") or []
        text = "".join(p.get("text", "") for p in parts if p.get("type") == "output_text")
        refusal = next((p for p in parts if p.get("type") == "refusal"), None)
        if refusal is not None:
            return llm_invalid(
                "refusal", refusal.get("refusal") or "", stop_reason=stop_reason, model_id=model_id, usage=usage
            )
        if status == "incomplete":
            code = INCOMPLETE_CODES.get(incomplete_reason or "", "incomplete")
            return llm_invalid(code, text, stop_reason=stop_reason, model_id=model_id, usage=usage)
        return llm_parsed(text, prompt.enum, stop_reason=stop_reason, model_id=model_id, usage=usage)

    def request_id(self, headers: Mapping[str, str]) -> str | None:
        return get_header(headers, "x-request-id")

    def rate_limit_headers(self, headers: Mapping[str, str]) -> dict[str, str]:
        return select_headers(headers, ("x-ratelimit-",), RATE_LIMIT_NAMES)


def _usage(raw: Mapping[str, Any]) -> Usage:
    details = raw.get("input_tokens_details") or {}
    cache_read = details.get("cached_tokens") or 0
    cache_write = details.get("cache_write_tokens") or 0
    reasoning = (raw.get("output_tokens_details") or {}).get("reasoning_tokens")
    return Usage(
        uncached_input=(raw.get("input_tokens") or 0) - cache_read - cache_write,
        cache_read=cache_read,
        cache_write=cache_write,
        output=raw.get("output_tokens") or 0,
        reasoning=reasoning,
    )
