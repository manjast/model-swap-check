"""Case-insensitive response-header helpers shared by the adapters (plain dicts and `httpx.Headers`)."""

from __future__ import annotations

from collections.abc import Mapping


def get_header(headers: Mapping[str, str], name: str) -> str | None:
    return next((v for k, v in headers.items() if k.lower() == name), None)


def select_headers(headers: Mapping[str, str], prefixes: tuple[str, ...], names: frozenset[str]) -> dict[str, str]:
    """Headers whose lowercased name starts with one of `prefixes` or is in `names`, keys lowercased."""
    return {k.lower(): v for k, v in headers.items() if k.lower().startswith(prefixes) or k.lower() in names}
