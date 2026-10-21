"""Anthropic Messages API adapter (`haiku55-*`; spec §4)."""

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

URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"  # recorded per run (RunMeta.versions)
STOP_CODES = {"refusal": "refusal", "max_tokens": "truncated"}
RATE_LIMIT_NAMES = frozenset({"retry-after"})


class AnthropicMessagesAdapter:
    provider = "anthropic"
    api_key_env = "ANTHROPIC_API_KEY"

    def auth_headers(self, api_key: str) -> dict[str, str]:
        return {"x-api-key": api_key}

    def cache_key(self, cfg: Configuration, item_digest: str) -> str | None:
        return None

    def warmup_cache_keys(self, cfg: Configuration) -> list[str | None]:
        return [None]

    def build_request(self, cfg: Configuration, prompt: Prompt, text: str, cache_key: str | None) -> HttpRequest:
        assert cfg.temperature is None, "Haiku 5.5 rejects sampling parameters; never send temperature"
        output_config: dict[str, Any] = {"format": {"type": "json_schema", "schema": llm_output_schema(prompt)}}
        if cfg.effort is not None:
            output_config = {"effort": cfg.effort, **output_config}
        body: dict[str, Any] = {
            "model": cfg.model,
            "max_tokens": cfg.max_output_tokens,
            "system": [{"type": "text", "text": prompt.developer_message(), "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": text}],
            "output_config": output_config,
        }
        if cfg.thinking is not None:
            body["thinking"] = {"type": cfg.thinking}
        headers = {"anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"}
        return HttpRequest("POST", URL, headers, body)

    def parse_response(self, cfg: Configuration, prompt: Prompt, body: Mapping[str, Any]) -> Parsed:
        usage = _usage(body.get("usage") or {})
        model_id = body.get("model")
        stop_reason = body.get("stop_reason")
        blocks: list[Mapping[str, Any]] = body.get("content") or []
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        code = STOP_CODES.get(stop_reason or "")
        if code is not None:
            return llm_invalid(code, text, stop_reason=stop_reason, model_id=model_id, usage=usage)
        return llm_parsed(text, prompt.enum, stop_reason=stop_reason, model_id=model_id, usage=usage)

    def request_id(self, headers: Mapping[str, str]) -> str | None:
        return get_header(headers, "request-id")

    def rate_limit_headers(self, headers: Mapping[str, str]) -> dict[str, str]:
        return select_headers(headers, ("anthropic-ratelimit-",), RATE_LIMIT_NAMES)


def _usage(raw: Mapping[str, Any]) -> Usage:
    return Usage(
        uncached_input=raw.get("input_tokens") or 0,
        cache_read=raw.get("cache_read_input_tokens") or 0,
        cache_write=raw.get("cache_creation_input_tokens") or 0,
        output=raw.get("output_tokens") or 0,
        reasoning=(raw.get("output_tokens_details") or {}).get("thinking_tokens"),
    )
