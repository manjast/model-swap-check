"""Output schema (spec §3.2) and the request-design hash recorded per run."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from swapcheck.configs import Configuration
from swapcheck.groups import OUT_OF_SCOPE
from swapcheck.prompt import DECISIONS_CONFIG, Prompt, decisions_translation, jev_translation


def llm_output_schema(prompt: Prompt) -> dict[str, Any]:
    """The JSON schema every LLM configuration receives, unchanged across providers."""
    return {
        "type": "object",
        "properties": {
            "intent": {"type": "string", "enum": prompt.enum},
            "confidence": {"type": "number"},
        },
        "required": ["intent", "confidence"],
        "additionalProperties": False,
    }


def jev_design(cfg: Configuration, prompt: Prompt) -> dict[str, Any]:
    """The §4.1 request design for a Jev configuration, with the pilot's reversed order applied."""
    assert cfg.jev_design is not None
    design: dict[str, Any] = json.loads(json.dumps(jev_translation(prompt)[f"jev-{cfg.jev_design}"]))
    if cfg.option_order == "reversed":
        criteria = design["choice"]["criteria"]
        intents = [k for k in criteria if k != "out_of_scope"][::-1]
        tail = ["out_of_scope"] if "out_of_scope" in criteria else []
        design["choice"]["criteria"] = {k: criteria[k] for k in intents + tail}
    return design


def decisions_design(cfg: Configuration, prompt: Prompt) -> dict[str, Any]:
    """The §4.2 request design for `luna-dec` (its `questions`), with the pilot's reversed order applied:
    the 50 intents reversed, `out_of_scope` kept last."""
    assert cfg.api == "decisions"
    design: dict[str, Any] = json.loads(json.dumps(decisions_translation(prompt)[DECISIONS_CONFIG]))
    if cfg.option_order == "reversed":
        (question,) = design["questions"]
        choices = question["choices"]
        intents = [c for c in choices if c["value"] != OUT_OF_SCOPE][::-1]
        question["choices"] = intents + [c for c in choices if c["value"] == OUT_OF_SCOPE]
    return design


def schema_sha256(cfg: Configuration, prompt: Prompt) -> str:
    """LLMs: hash of the output schema. Decision interfaces (Jev, `luna-dec`): hash of the request design
    (the options are the schema)."""
    obj: dict[str, Any]
    if cfg.api == "decisions":
        obj = decisions_design(cfg, prompt)
    elif cfg.provider == "typesafe":
        obj = jev_design(cfg, prompt)
    else:
        obj = llm_output_schema(prompt)
    return hashlib.sha256(json.dumps(obj, separators=(",", ":")).encode()).hexdigest()
