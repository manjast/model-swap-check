"""Configurations under test (spec §4), loaded from `config/configurations.yaml`."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from swapcheck.groups import REPO_ROOT

CONFIGURATIONS_PATH = REPO_ROOT / "config" / "configurations.yaml"
DEFAULT_PROMPT = "prompts/incumbent-v1.md"

Provider = Literal["openai", "anthropic", "typesafe"]


class Configuration(BaseModel):
    """One configuration. Fields that do not apply to a provider stay None."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    provider: Provider
    model: str
    prompt: str = DEFAULT_PROMPT
    max_output_tokens: int | None = None
    temperature: float | None = None
    # OpenAI
    reasoning_effort: Literal["none", "low", "medium"] | None = None
    prompt_cache_keys: int | None = None
    cache_ttl: str | None = None
    # Anthropic
    thinking: Literal["disabled", "adaptive"] | None = None
    effort: Literal["low", "medium"] | None = None
    # OpenAI and Anthropic
    cache_mode: Literal["implicit", "explicit", "system_block"] | None = None
    # TypeSafe
    jev_design: Literal["c51", "noul"] | None = None
    option_order: Literal["normal", "reversed"] = "normal"
    pilot_only: bool = False

    @property
    def is_llm(self) -> bool:
        return self.provider != "typesafe"

    @property
    def prompt_path(self) -> Path:
        return REPO_ROOT / self.prompt

    def sha256(self) -> str:
        """Hash of the canonical JSON of every field (spec §7.7, §10)."""
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


def load_configurations(path: Path = CONFIGURATIONS_PATH) -> dict[str, Configuration]:
    """All configurations, including the pilot-only variants (marked `pilot_only`)."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    configs = {cid: Configuration(id=cid, **fields) for cid, fields in raw["configurations"].items()}
    for cid, fields in raw.get("pilot_variants", {}).items():
        overrides = dict(fields)
        base = configs[overrides.pop("base")]
        configs[cid] = Configuration(**{**base.model_dump(), "id": cid, "pilot_only": True, **overrides})
    return configs
