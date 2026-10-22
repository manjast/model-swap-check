"""Provider adapters (spec §4): pure request builders and response parsers."""

from __future__ import annotations

from swapcheck.configs import Configuration
from swapcheck.providers.anthropic_messages import AnthropicMessagesAdapter
from swapcheck.providers.base import ProviderAdapter
from swapcheck.providers.openai_decisions import OpenAIDecisionsAdapter
from swapcheck.providers.openai_responses import OpenAIResponsesAdapter
from swapcheck.providers.typesafe_systemone import TypeSafeSystemOneAdapter

# (provider, api): `api` None is the provider's default API.
_ADAPTERS: dict[tuple[str, str | None], ProviderAdapter] = {
    ("openai", None): OpenAIResponsesAdapter(),
    ("openai", "decisions"): OpenAIDecisionsAdapter(),
    ("anthropic", None): AnthropicMessagesAdapter(),
    ("typesafe", None): TypeSafeSystemOneAdapter(),
}


def get_adapter(cfg: Configuration) -> ProviderAdapter:
    try:
        return _ADAPTERS[(cfg.provider, cfg.api)]
    except KeyError:
        raise ValueError(f"{cfg.id}: no adapter for provider {cfg.provider!r} with api {cfg.api!r}") from None
