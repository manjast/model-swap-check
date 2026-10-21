"""Provider adapter contract. Adapters are pure: they build request bodies and parse response
bodies. Sending, retries, rate limits and records belong to the runner."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from swapcheck.configs import Configuration
from swapcheck.prompt import Prompt
from swapcheck.records import Parsed

WARMUP_TEXT = "Hello"  # spec §4: fixed warm-up user message


@dataclass(frozen=True)
class HttpRequest:
    """One request. `headers` never contains credentials; the runner adds `auth_headers`."""

    method: str
    url: str
    headers: dict[str, str]
    body: dict[str, Any]


class ProviderAdapter(Protocol):
    provider: str
    api_key_env: str  # environment variable holding the key, e.g. "OPENAI_API_KEY"

    def auth_headers(self, api_key: str) -> dict[str, str]: ...

    def cache_key(self, cfg: Configuration, item_digest: str) -> str | None:
        """Per-item cache routing key (`inc`: `msc-<int(digest, 16) mod 16>`), else None."""
        ...

    def warmup_cache_keys(self, cfg: Configuration) -> list[str | None]:
        """One entry per warm-up request (spec §4: 16 for `inc`, 1 for other LLMs, none for Jev)."""
        ...

    def build_request(self, cfg: Configuration, prompt: Prompt, text: str, cache_key: str | None) -> HttpRequest: ...

    def parse_response(self, cfg: Configuration, prompt: Prompt, body: Mapping[str, Any]) -> Parsed:
        """Parse a 2xx body into `ok` or `invalid_output` (spec §3.2, §9.2), with usage and model ID."""
        ...

    def request_id(self, headers: Mapping[str, str]) -> str | None: ...

    def rate_limit_headers(self, headers: Mapping[str, str]) -> dict[str, str]:
        """The provider's rate-limit headers, verbatim, for the pilot's limits (spec §9.4)."""
        ...
