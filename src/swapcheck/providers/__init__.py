"""Provider adapters (spec §4): pure request builders and response parsers."""

from __future__ import annotations

from swapcheck.providers.anthropic_messages import AnthropicMessagesAdapter
from swapcheck.providers.base import ProviderAdapter
from swapcheck.providers.openai_responses import OpenAIResponsesAdapter
from swapcheck.providers.typesafe_systemone import TypeSafeSystemOneAdapter

_ADAPTERS: dict[str, ProviderAdapter] = {
    "openai": OpenAIResponsesAdapter(),
    "anthropic": AnthropicMessagesAdapter(),
    "typesafe": TypeSafeSystemOneAdapter(),
}


def get_adapter(provider: str) -> ProviderAdapter:
    try:
        return _ADAPTERS[provider]
    except KeyError:
        raise ValueError(f"unknown provider {provider!r}") from None
