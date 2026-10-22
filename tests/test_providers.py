from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import FakeClock

from swapcheck.configs import Configuration, load_configurations
from swapcheck.cost import attempt_cost_usd, load_prices
from swapcheck.groups import OUT_OF_SCOPE
from swapcheck.http import Sender, SendResult
from swapcheck.parse import RAW_OUTPUT_CAP
from swapcheck.prompt import Prompt
from swapcheck.providers import get_adapter
from swapcheck.providers.anthropic_messages import ANTHROPIC_VERSION
from swapcheck.records import Parsed, Usage
from swapcheck.schema import llm_output_schema, schema_sha256

FIXTURES = Path(__file__).parent / "fixtures" / "responses"
CONFIGS = load_configurations()
PRICES = load_prices()
# luna-none-x's prompt is written at M4; every other configuration is snapshot here.
SNAPSHOT_IDS = sorted(cid for cid in CONFIGS if cid != "luna-none-x")
RAW_TEXT = "  Where's my new card?? It's been 2 weeks…\n\tI'm in Zürich 💳  "
FAKE_KEY = "sk-test-NOT-A-REAL-KEY-0123456789"


def _request(cid: str, prompt: Prompt, cache_key: str | None = None) -> dict[str, Any]:
    cfg = CONFIGS[cid]
    request = get_adapter(cfg).build_request(cfg, prompt, RAW_TEXT, cache_key)
    assert request.method == "POST"
    return request.body


# --- T-R1: request snapshots -------------------------------------------------------------------------------------

OPENAI_EXPECTED: dict[str, dict[str, Any]] = {
    "inc": {
        "model": "gpt-4o-mini-2024-07-18",
        "temperature": 0,
        "reasoning": None,
        "max_output_tokens": 100,
        "prompt_cache_options": None,
        "breakpoint": False,
    },
    "luna-none": {
        "model": "gpt-6-luna",
        "temperature": 0,
        "reasoning": {"effort": "none"},
        "max_output_tokens": 200,
        "prompt_cache_options": {"mode": "explicit", "ttl": "30m"},
        "breakpoint": True,
    },
    "luna-low": {
        "model": "gpt-6-luna",
        "temperature": None,
        "reasoning": {"effort": "low"},
        "max_output_tokens": 1024,
        "prompt_cache_options": {"mode": "explicit", "ttl": "30m"},
        "breakpoint": True,
    },
    "luna-medium": {
        "model": "gpt-6-luna",
        "temperature": None,
        "reasoning": {"effort": "medium"},
        "max_output_tokens": 4096,
        "prompt_cache_options": {"mode": "explicit", "ttl": "30m"},
        "breakpoint": True,
    },
    "luna-none-implicit": {
        "model": "gpt-6-luna",
        "temperature": 0,
        "reasoning": {"effort": "none"},
        "max_output_tokens": 200,
        "prompt_cache_options": {"mode": "implicit"},
        "breakpoint": False,
    },
}

ANTHROPIC_EXPECTED: dict[str, dict[str, Any]] = {
    "haiku55-off": {"thinking": {"type": "disabled"}, "effort": "low", "max_tokens": 200},
    "haiku55-low": {"thinking": {"type": "adaptive"}, "effort": "low", "max_tokens": 1024},
    "haiku55-medium": {"thinking": {"type": "adaptive"}, "effort": "medium", "max_tokens": 4096},
}

JEV_EXPECTED: dict[str, tuple[str, bool]] = {  # design, reversed
    "jev-c51": ("c51", False),
    "jev-noul": ("noul", False),
    "jev-c51-reversed": ("c51", True),
    "jev-noul-reversed": ("noul", True),
}

DECISIONS_EXPECTED: dict[str, bool] = {"luna-dec": False, "luna-dec-reversed": True}  # reversed


def test_r1_every_snapshot_configuration_has_an_expectation() -> None:
    expected = set(OPENAI_EXPECTED) | set(ANTHROPIC_EXPECTED) | set(JEV_EXPECTED) | set(DECISIONS_EXPECTED)
    assert set(SNAPSHOT_IDS) == expected


@pytest.mark.parametrize("cid", sorted(OPENAI_EXPECTED))
def test_r1_openai_request(incumbent: Prompt, cid: str) -> None:
    exp = OPENAI_EXPECTED[cid]
    body = _request(cid, incumbent)
    expected_keys = {"model", "store", "input", "text", "max_output_tokens"}
    expected_keys |= {k for k in ("temperature", "reasoning", "prompt_cache_options") if exp[k] is not None}
    assert set(body) == expected_keys
    assert body["model"] == exp["model"]
    assert body["store"] is False
    assert body.get("temperature") == exp["temperature"]
    assert body.get("reasoning") == exp["reasoning"]
    assert body["max_output_tokens"] == exp["max_output_tokens"]
    assert body.get("prompt_cache_options") == exp["prompt_cache_options"]
    developer, user = body["input"]
    part: dict[str, Any] = {"type": "input_text", "text": incumbent.developer_message()}
    if exp["breakpoint"]:
        part["prompt_cache_breakpoint"] = {"mode": "explicit"}
    assert developer == {"role": "developer", "content": [part]}
    assert user == {"role": "user", "content": RAW_TEXT}
    assert body["text"] == {
        "format": {"type": "json_schema", "name": "routing", "strict": True, "schema": llm_output_schema(incumbent)}
    }


@pytest.mark.parametrize("cid", sorted(ANTHROPIC_EXPECTED))
def test_r1_anthropic_request(incumbent: Prompt, cid: str) -> None:
    exp = ANTHROPIC_EXPECTED[cid]
    cfg = CONFIGS[cid]
    request = get_adapter(cfg).build_request(cfg, incumbent, RAW_TEXT, None)
    body = request.body
    # No top-level cache_control and no sampling parameters (temperature/top_p/top_k are rejected by Haiku 5.5).
    assert set(body) == {"model", "max_tokens", "system", "messages", "thinking", "output_config"}
    assert body["model"] == "claude-haiku-5-5"
    assert body["max_tokens"] == exp["max_tokens"]
    assert body["thinking"] == exp["thinking"]
    assert body["system"] == [
        {"type": "text", "text": incumbent.developer_message(), "cache_control": {"type": "ephemeral"}}
    ]
    assert body["messages"] == [{"role": "user", "content": RAW_TEXT}]
    assert body["output_config"] == {
        "effort": exp["effort"],
        "format": {"type": "json_schema", "schema": llm_output_schema(incumbent)},
    }
    assert request.headers["anthropic-version"] == ANTHROPIC_VERSION


def test_r1_identical_schema_object_across_llms(incumbent: Prompt) -> None:
    schemas = []
    for cid in SNAPSHOT_IDS:
        body = _request(cid, incumbent)
        if cid in OPENAI_EXPECTED:
            schemas.append(body["text"]["format"]["schema"])
        elif cid in ANTHROPIC_EXPECTED:
            schemas.append(body["output_config"]["format"]["schema"])
    assert len(schemas) == len(OPENAI_EXPECTED) + len(ANTHROPIC_EXPECTED)
    assert all(s == schemas[0] for s in schemas)
    assert schemas[0]["properties"]["intent"]["enum"] == incumbent.enum


@pytest.mark.parametrize("cid", sorted(JEV_EXPECTED))
def test_r1_jev_request(incumbent: Prompt, cid: str) -> None:
    design, reversed_order = JEV_EXPECTED[cid]
    body = _request(cid, incumbent)
    assert set(body) == {"model", "state", "questions"}
    assert body["model"] == "jev-1.13.0"
    assert body["state"] == RAW_TEXT
    questions = body["questions"]
    choice = questions["intent"]
    assert set(choice) == {"type", "instructions", "criteria"}
    assert choice["type"] == "choice"
    entries = {e.intent: e for e in incumbent.catalog}
    if design == "c51":
        assert set(questions) == {"intent"}
        assert choice["instructions"] == f"{incumbent.routing_instruction} {incumbent.oos_clause}"
        catalog_ids = incumbent.intents
        assert list(choice["criteria"])[-1] == OUT_OF_SCOPE
    else:
        assert set(questions) == {"intent", "match"}
        assert choice["instructions"] == incumbent.routing_instruction
        catalog_ids = incumbent.intents
        assert OUT_OF_SCOPE not in choice["criteria"]
        assert questions["match"] == {
            "type": "noul",
            "instructions": {
                "question": "Does the customer message ask about any of the topics in catalog?",
                "catalog": {e.intent: e.description for e in incumbent.catalog},
            },
        }
    order = [k for k in choice["criteria"] if k != OUT_OF_SCOPE]
    assert order == (catalog_ids[::-1] if reversed_order else catalog_ids)
    for k in order:
        assert choice["criteria"][k] == {"description": entries[k].description, "example": entries[k].example}


@pytest.mark.parametrize("cid", sorted(DECISIONS_EXPECTED))
def test_r1_decisions_request(incumbent: Prompt, cid: str) -> None:
    cfg = CONFIGS[cid]
    request = get_adapter(cfg).build_request(cfg, incumbent, RAW_TEXT, None)
    assert (request.method, request.url) == ("POST", "https://api.openai.com/v1/decisions")
    assert request.headers == {"content-type": "application/json"}
    body = request.body
    # no store, temperature, reasoning, max-token or cache parameters
    assert set(body) == {"model", "input", "questions"}
    assert body["model"] == "gpt-6-luna"
    assert body["input"] == RAW_TEXT
    (question,) = body["questions"]
    assert set(question) == {"type", "name", "instructions", "choices"}
    assert (question["type"], question["name"]) == ("choice", "intent")
    assert question["instructions"] == f"{incumbent.routing_instruction} {incumbent.oos_clause}"
    *intents, oos = question["choices"]
    assert oos == {"value": OUT_OF_SCOPE, "description": "The customer message is about none of the other options."}
    catalog = incumbent.catalog[::-1] if DECISIONS_EXPECTED[cid] else incumbent.catalog
    assert intents == [{"value": e.intent, "description": f"{e.description} Example: {e.example}"} for e in catalog]


def test_r1_decisions_design_hash_tracks_option_order(incumbent: Prompt) -> None:
    normal, reversed_order = CONFIGS["luna-dec"], CONFIGS["luna-dec-reversed"]
    assert schema_sha256(normal, incumbent) != schema_sha256(reversed_order, incumbent)
    assert schema_sha256(normal, incumbent) not in {
        schema_sha256(CONFIGS[c], incumbent) for c in ("luna-none", "jev-c51")
    }


def test_get_adapter_refuses_an_api_the_provider_lacks() -> None:
    with pytest.raises(ValueError, match="no adapter"):
        get_adapter(CONFIGS["haiku55-off"].model_copy(update={"api": "decisions"}))


def test_r1_jev_refuses_alias_model(incumbent: Prompt) -> None:
    adapter = get_adapter(CONFIGS["jev-c51"])
    for alias in ("jev-latest", "jev-preview"):
        cfg = CONFIGS["jev-c51"].model_copy(update={"model": alias})
        with pytest.raises(ValueError, match="pinned"):
            adapter.build_request(cfg, incumbent, RAW_TEXT, None)


def test_r1_no_credentials_in_requests(incumbent: Prompt) -> None:
    for cid in SNAPSHOT_IDS:
        cfg = CONFIGS[cid]
        adapter = get_adapter(cfg)
        request = adapter.build_request(cfg, incumbent, RAW_TEXT, adapter.cache_key(cfg, "ab" * 32))
        lowered = {k.lower() for k in request.headers}
        assert not lowered & {"authorization", "x-api-key"}
        assert FAKE_KEY not in json.dumps([request.url, request.headers, request.body])
    assert get_adapter(CONFIGS["inc"]).auth_headers(FAKE_KEY) == {"Authorization": f"Bearer {FAKE_KEY}"}
    assert get_adapter(CONFIGS["luna-dec"]).auth_headers(FAKE_KEY) == {"Authorization": f"Bearer {FAKE_KEY}"}
    assert get_adapter(CONFIGS["haiku55-off"]).auth_headers(FAKE_KEY) == {"x-api-key": FAKE_KEY}
    assert get_adapter(CONFIGS["jev-c51"]).auth_headers(FAKE_KEY) == {"Authorization": f"Bearer {FAKE_KEY}"}


def test_r1_inc_prompt_cache_key_mapping(incumbent: Prompt) -> None:
    adapter = get_adapter(CONFIGS["inc"])
    inc = CONFIGS["inc"]
    assert adapter.cache_key(inc, "0" * 64) == "msc-0"
    assert adapter.cache_key(inc, "0" * 63 + "f") == "msc-15"
    assert adapter.cache_key(inc, "0" * 62 + "11") == "msc-1"  # 17 mod 16
    digest = "9c" * 32
    assert adapter.cache_key(inc, digest) == f"msc-{int(digest, 16) % 16}"
    body = _request("inc", incumbent, adapter.cache_key(inc, digest))
    assert body["prompt_cache_key"] == adapter.cache_key(inc, digest)
    for cid in ("luna-none", "luna-low", "luna-medium", "luna-none-implicit"):
        assert adapter.cache_key(CONFIGS[cid], digest) is None
        assert "prompt_cache_key" not in _request(cid, incumbent)


def test_r1_warmup_cache_keys() -> None:
    assert get_adapter(CONFIGS["inc"]).warmup_cache_keys(CONFIGS["inc"]) == [f"msc-{i}" for i in range(16)]
    for cid in SNAPSHOT_IDS:
        cfg = CONFIGS[cid]
        if cid == "inc":
            continue
        no_warmup = cfg.provider == "typesafe" or cid in DECISIONS_EXPECTED
        expected: list[str | None] = [] if no_warmup else [None]
        assert get_adapter(cfg).warmup_cache_keys(cfg) == expected, cid


# --- T-R2: response normalization from fixtures --------------------------------------------------------------------


def _fixture(name: str) -> tuple[Configuration, httpx.Headers, dict[str, Any]]:
    doc = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return CONFIGS[doc["config_id"]], httpx.Headers(doc["headers"]), doc["body"]


def _parse(name: str, prompt: Prompt) -> tuple[Parsed, str | None, dict[str, str]]:
    cfg, headers, body = _fixture(name)
    adapter = get_adapter(cfg)
    return adapter.parse_response(cfg, prompt, body), adapter.request_id(headers), adapter.rate_limit_headers(headers)


# Real pilot responses (T-L6). Expected values are read off each body by hand: usage classes follow billing
# (uncached = input - cache read - cache write; reasoning is part of output).
PILOT_EXPECTED: dict[str, tuple[str, float, Usage, str | None, str, str]] = {
    # fixture: (intent, confidence, usage, stop reason, model, request ID)
    "pilot-inc.json": (
        "why_verify_identity",
        0.9,
        Usage(uncached_input=234, cache_read=2432, output=14, reasoning=0),
        "completed",
        "gpt-4o-mini-2024-07-18",
        "req_224b3a38572b46ac8630a4b6e6881981",
    ),
    "pilot-luna-none.json": (
        "exchange_charge",
        0.91,
        Usage(uncached_input=20, cache_read=2648, output=19, reasoning=0),
        "completed",
        "gpt-6-luna",
        "req_144d0dd314e3434fa7ac880a855f381b",
    ),
    "pilot-luna-low.json": (  # a reasoning item precedes the message
        "fiat_currency_support",
        0.88,
        Usage(uncached_input=13, cache_read=2648, output=49, reasoning=26),
        "completed",
        "gpt-6-luna",
        "req_d3a712bf84eb4063adcaca0310b3ad1a",
    ),
    "pilot-luna-low-warmup.json": (
        OUT_OF_SCOPE,
        0.99,
        Usage(uncached_input=8, cache_write=2648, output=20, reasoning=0),
        "completed",
        "gpt-6-luna",
        "req_3c82facf0e204fb3bc019f6e223952ad",
    ),
    "pilot-haiku55-off.json": (  # JSON with spaces after the separators
        "cancel_transfer",
        0.9,
        Usage(uncached_input=22, cache_read=4368, output=25, reasoning=0),
        "end_turn",
        "claude-haiku-5-5",
        "req_011CgH2LCW6z5Kkubjz1TifJ",
    ),
    "pilot-haiku55-off-warmup.json": (
        OUT_OF_SCOPE,
        0.9,
        Usage(uncached_input=9, cache_write=4368, output=22, reasoning=0),
        "end_turn",
        "claude-haiku-5-5",
        "req_011CgH2JrVoYo8mgs39WMP3A",
    ),
    "pilot-haiku55-low.json": (  # an empty thinking block precedes the text
        OUT_OF_SCOPE,
        0.6,
        Usage(uncached_input=24, cache_read=4369, output=334, reasoning=311),
        "end_turn",
        "claude-haiku-5-5",
        "req_011CgH2P1GkZvikQYpXH7V6c",
    ),
    "pilot-jev-c51.json": (
        OUT_OF_SCOPE,
        0.88,
        Usage(uncached_input=3463, output=560),
        None,
        "jev-1.13.0",
        "req_01a162e5f6ca77d294a1a587836f061e",
    ),
    "pilot-jev-noul.json": (
        "card_arrival",
        1.0,
        Usage(uncached_input=4791, output=568),
        None,
        "jev-1.13.0",
        "req_01a162e6e1f272b38b1125b9379b6434",
    ),
    "pilot-luna-dec.json": (
        "direct_debit_payment_not_recognised",
        0.9,
        Usage(uncached_input=2316, output=0, reasoning=0),
        None,
        "gpt-6-luna",
        "req_72dc2cddfc534d8e8c2563f9963924d7",
    ),
}


def test_r2_every_pilot_fixture_has_an_expectation() -> None:
    assert {p.name for p in FIXTURES.glob("pilot-*.json")} == set(PILOT_EXPECTED)


@pytest.mark.parametrize("name", sorted(PILOT_EXPECTED))
def test_r2_pilot_response(incumbent: Prompt, name: str) -> None:
    intent, confidence, usage, stop_reason, model, req = PILOT_EXPECTED[name]
    cfg, _, body = _fixture(name)
    parsed, request_id, limits = _parse(name, incumbent)
    assert (parsed.status, parsed.error_code, parsed.case_normalized) == ("ok", None, False)
    assert (parsed.intent, parsed.confidence, parsed.stop_reason, parsed.model_id) == (
        intent,
        confidence,
        stop_reason,
        model,
    )
    assert parsed.usage == usage
    assert request_id == req
    if cfg.provider == "openai":
        assert {"openai-processing-ms", "x-ratelimit-limit-requests", "x-ratelimit-limit-tokens"} <= set(limits)
    if cfg.provider == "anthropic":
        assert {"anthropic-ratelimit-requests-limit", "anthropic-ratelimit-input-tokens-limit"} <= set(limits)
    if cfg.is_decision_interface:
        assert json.loads(parsed.raw_output) == body  # full response JSON kept


def test_r2_pilot_jev_and_decisions_probabilities(incumbent: Prompt) -> None:
    """Jev c51 and Decisions return the 51 enum values (Decisions as a list, mapped by value); Jev noul the
    50 intents plus a separate match probability."""
    for name, keys in (
        ("pilot-jev-c51.json", incumbent.enum),
        ("pilot-luna-dec.json", incumbent.enum),
        ("pilot-jev-noul.json", incumbent.enum[:-1]),
    ):
        cfg, _, body = _fixture(name)
        parsed = get_adapter(cfg).parse_response(cfg, incumbent, body)
        assert parsed.probabilities is not None and sorted(parsed.probabilities) == sorted(keys)
        assert sum(parsed.probabilities.values()) == pytest.approx(1.0, abs=0.01)
    _, _, body = _fixture("pilot-luna-dec.json")
    (answer,) = body["answers"]
    parsed = get_adapter(CONFIGS["luna-dec"]).parse_response(CONFIGS["luna-dec"], incumbent, body)
    assert parsed.probabilities == {p["value"]: p["probability"] for p in answer["probabilities"]}
    assert attempt_cost_usd(PRICES, CONFIGS["luna-dec"], parsed.usage) == pytest.approx(2316 * 0.10e-6)
    noul = get_adapter(CONFIGS["jev-noul"]).parse_response(
        CONFIGS["jev-noul"], incumbent, _fixture("pilot-jev-noul.json")[2]
    )
    assert noul.match_probability == 0.99


def test_r2_openai_cache_write_reasoning_and_case_normalization(incumbent: Prompt) -> None:
    parsed, request_id, _ = _parse("doc-openai-luna-low-cache-write.json", incumbent)
    # The message item is not the first output item (a reasoning item precedes it).
    assert (parsed.status, parsed.intent, parsed.case_normalized) == ("ok", "Refund_not_showing_up", False)
    assert parsed.usage == Usage(uncached_input=39, cache_read=0, cache_write=2201, output=212, reasoning=196)
    assert parsed.model_id == "gpt-6-luna"
    assert request_id == "req_luna_write_0002"


def test_p2_r2_openai_refusal(incumbent: Prompt) -> None:
    parsed, request_id, _ = _parse("doc-openai-refusal.json", incumbent)
    assert (parsed.status, parsed.error_code) == ("invalid_output", "refusal")
    assert parsed.raw_output == "I'm sorry, I cannot assist with that request."
    assert parsed.intent is None
    assert parsed.usage.output == 11  # refusals are billed
    assert request_id == "req_refusal_0004"


def test_p2_r2_openai_truncation(incumbent: Prompt) -> None:
    parsed, _, _ = _parse("doc-openai-incomplete.json", incumbent)
    assert (parsed.status, parsed.error_code) == ("invalid_output", "truncated")
    assert parsed.stop_reason == "max_output_tokens"
    assert parsed.usage == Usage(uncached_input=35, cache_read=2201, cache_write=0, output=4096, reasoning=4096)


def test_p2_openai_content_filter(incumbent: Prompt) -> None:
    cfg, _, body = _fixture("doc-openai-luna-none-cache-read.json")
    body = {**body, "status": "incomplete", "incomplete_details": {"reason": "content_filter"}}
    parsed = get_adapter(cfg).parse_response(cfg, incumbent, body)
    assert (parsed.status, parsed.error_code) == ("invalid_output", "content_filter")
    assert parsed.stop_reason == "content_filter"


def test_r2_anthropic_cache_write(incumbent: Prompt) -> None:
    parsed, request_id, limits = _parse("doc-anthropic-off-cache-write.json", incumbent)
    assert (parsed.status, parsed.intent, parsed.confidence) == ("ok", "card_arrival", 0.95)
    assert parsed.stop_reason == "end_turn"
    assert parsed.model_id == "claude-haiku-5-5"
    assert parsed.usage == Usage(uncached_input=16, cache_read=0, cache_write=2741, output=18, reasoning=0)
    assert request_id == "req_018EeWyXxfu5pfWkrYcMdjWG"
    assert set(limits) == {
        f"anthropic-ratelimit-{kind}-{field}"
        for kind in ("requests", "input-tokens", "output-tokens")
        for field in ("limit", "remaining", "reset")
    }


def test_r2_anthropic_thinking_cache_read_and_case_normalization(incumbent: Prompt) -> None:
    parsed, _, _ = _parse("doc-anthropic-low-thinking-cache-read.json", incumbent)
    assert (parsed.status, parsed.intent, parsed.case_normalized) == ("ok", "Refund_not_showing_up", True)
    assert parsed.raw_output == '{"intent":"Refund_Not_Showing_Up","confidence":0.82}'  # thinking block ignored
    assert parsed.usage == Usage(uncached_input=16, cache_read=2741, cache_write=0, output=171, reasoning=152)


def test_p2_r2_anthropic_unbilled_refusal_bills_zero_and_keeps_reported_counts(incumbent: Prompt) -> None:
    cfg, _, _ = _fixture("doc-anthropic-refusal.json")  # pre-output, category `cyber`: not billed
    parsed, request_id, _ = _parse("doc-anthropic-refusal.json", incumbent)
    assert (parsed.status, parsed.error_code, parsed.stop_reason) == ("invalid_output", "refusal", "refusal")
    assert parsed.usage == Usage()
    assert attempt_cost_usd(PRICES, cfg, parsed.usage) == 0.0
    diagnostics = json.loads(parsed.raw_output)
    assert diagnostics["billed"] is False
    assert diagnostics["stop_details"]["category"] == "cyber"
    assert diagnostics["usage"]["input_tokens"] == 2757  # reported, kept for diagnostics
    assert len(parsed.raw_output) <= RAW_OUTPUT_CAP
    assert request_id == "req_01XFUDYJgAACzvnptvVoYEL"


@pytest.mark.parametrize("category", ["general_harms", None])
def test_p2_anthropic_other_unbilled_refusal_categories(incumbent: Prompt, category: str | None) -> None:
    cfg, _, body = _fixture("doc-anthropic-refusal.json")
    body = {**body, "stop_details": {"type": "refusal", "category": category, "explanation": None}}
    parsed = get_adapter(cfg).parse_response(cfg, incumbent, body)
    assert (parsed.status, parsed.error_code, parsed.usage) == ("invalid_output", "refusal", Usage())
    assert json.loads(parsed.raw_output)["stop_details"]["category"] == category


def test_p2_r2_anthropic_billed_refusal_category_is_charged(incumbent: Prompt) -> None:
    cfg, _, body = _fixture("doc-anthropic-refusal-bio.json")  # pre-output, category `bio`: billed
    parsed, request_id, _ = _parse("doc-anthropic-refusal-bio.json", incumbent)
    assert (parsed.status, parsed.error_code, parsed.stop_reason) == ("invalid_output", "refusal", "refusal")
    assert parsed.usage == Usage(uncached_input=19, cache_read=2741)
    assert attempt_cost_usd(PRICES, cfg, parsed.usage) > 0
    assert parsed.raw_output == ""  # no model text
    assert request_id == "req_01Hb7RkQpLm2VnTzW4sYcXbD"
    for category in ("frontier_llm", "reasoning_extraction", "some_future_category"):
        changed = {**body, "stop_details": {**body["stop_details"], "category": category}}
        assert get_adapter(cfg).parse_response(cfg, incumbent, changed).usage == parsed.usage, category


def test_p2_anthropic_mid_output_or_uncategorized_refusal_is_charged(incumbent: Prompt) -> None:
    cfg, _, body = _fixture("doc-anthropic-refusal.json")
    mid_output = {
        **body,
        "content": [{"type": "text", "text": '{"intent": "card_'}],
        "usage": {**body["usage"], "output_tokens": 7},
    }
    parsed = get_adapter(cfg).parse_response(cfg, incumbent, mid_output)
    assert (parsed.status, parsed.error_code) == ("invalid_output", "refusal")
    assert parsed.usage == Usage(uncached_input=2757, output=7)
    assert parsed.raw_output == '{"intent": "card_'
    no_details = {k: v for k, v in body.items() if k != "stop_details"}  # category unknown: charge
    assert get_adapter(cfg).parse_response(cfg, incumbent, no_details).usage == Usage(uncached_input=2757)


def test_p2_r2_anthropic_truncation(incumbent: Prompt) -> None:
    parsed, _, _ = _parse("doc-anthropic-max-tokens.json", incumbent)
    assert (parsed.status, parsed.error_code, parsed.stop_reason) == ("invalid_output", "truncated", "max_tokens")
    assert parsed.usage.output == 4096 and parsed.usage.reasoning == 4096


def test_r2_raw_output_capped_for_llms_only(incumbent: Prompt) -> None:
    cfg, _, body = _fixture("doc-anthropic-off-cache-write.json")
    long_text = '{"intent": "card_arrival", "confidence": 0.9' + " " * 3000 + "}"
    body = {**body, "content": [{"type": "text", "text": long_text}]}
    parsed = get_adapter(cfg).parse_response(cfg, incumbent, body)
    assert parsed.status == "ok"  # parsed from the full text, stored capped
    assert parsed.raw_output == long_text[:RAW_OUTPUT_CAP]
    cfg, _, body = _fixture("doc-typesafe-c51-ok.json")
    body = {**body, "note": "x" * 3000}  # Jev raw_output is the full response JSON, never capped
    jev = get_adapter(cfg).parse_response(cfg, incumbent, body)
    assert json.loads(jev.raw_output) == body
    cfg, _, body = _fixture("doc-openai-decisions-ok.json")
    body = {**body, "note": "x" * 3000}  # so is the Decisions API's
    assert json.loads(get_adapter(cfg).parse_response(cfg, incumbent, body).raw_output) == body


# --- T-P2: Jev invalid outputs -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("doc-typesafe-noul-missing-answer.json", "missing_answer"),
        ("doc-typesafe-c51-extra-answer.json", "unexpected_answer"),
        ("doc-typesafe-c51-choice-outside-criteria.json", "unknown_choice"),
        ("doc-typesafe-c51-probabilities-sum-0.9.json", "probabilities_sum"),
    ],
)
def test_p2_jev_invalid_fixtures(incumbent: Prompt, name: str, code: str) -> None:
    parsed, _, _ = _parse(name, incumbent)
    assert (parsed.status, parsed.error_code) == ("invalid_output", code)
    assert parsed.intent is None and parsed.probabilities is None
    assert parsed.usage.uncached_input > 0  # still billed
    assert parsed.raw_output  # full response kept


def _mutated_jev(name: str, prompt: Prompt, mutate: Any) -> Parsed:
    cfg, _, body = _fixture(name)
    mutate(body["answers"])
    return get_adapter(cfg).parse_response(cfg, prompt, body)


def _set(path: tuple[str, ...], value: Any) -> Any:
    def mutate(answers: dict[str, Any]) -> None:
        target = answers
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    return mutate


def _scale_probabilities(factor: float) -> Any:
    def mutate(answers: dict[str, Any]) -> None:
        probs = answers["intent"]["probabilities"]
        for k in probs:
            probs[k] *= factor

    return mutate


@pytest.mark.parametrize(
    ("name", "mutate", "code"),
    [
        ("doc-typesafe-c51-ok.json", _set(("intent", "confidence"), 1.2), "confidence_out_of_range"),
        ("doc-typesafe-c51-ok.json", _set(("intent", "confidence"), -0.1), "confidence_out_of_range"),
        ("doc-typesafe-c51-ok.json", _set(("intent", "confidence"), "high"), "confidence_not_numeric"),
        ("doc-typesafe-noul-ok.json", _set(("match", "noul"), 1.5), "match_probability_out_of_range"),
        ("doc-typesafe-noul-ok.json", _set(("match", "noul"), -0.01), "match_probability_out_of_range"),
        ("doc-typesafe-c51-ok.json", lambda a: a["intent"].pop("probabilities"), "probabilities_missing"),
        ("doc-typesafe-c51-ok.json", lambda a: a["intent"].pop("confidence"), "missing_field"),
        ("doc-typesafe-noul-ok.json", lambda a: a["match"].pop("noul"), "missing_field"),
        ("doc-typesafe-c51-ok.json", lambda a: a["intent"]["probabilities"].pop("card_arrival"), "probabilities_keys"),
        ("doc-typesafe-c51-ok.json", _scale_probabilities(1.02), "probabilities_sum"),
        ("doc-typesafe-noul-ok.json", _set(("intent", "choice"), OUT_OF_SCOPE), "unknown_choice"),
    ],
)
def test_p2_jev_invalid_values(incumbent: Prompt, name: str, mutate: Any, code: str) -> None:
    parsed = _mutated_jev(name, incumbent, mutate)
    assert (parsed.status, parsed.error_code) == ("invalid_output", code)


@pytest.mark.parametrize("factor", [0.991, 1.009])
def test_p2_jev_probability_sum_within_tolerance_is_ok(incumbent: Prompt, factor: float) -> None:
    parsed = _mutated_jev("doc-typesafe-c51-ok.json", incumbent, _scale_probabilities(factor))
    assert parsed.status == "ok"


def test_p2_jev_reversed_order_accepts_same_criteria(incumbent: Prompt) -> None:
    cfg = CONFIGS["jev-noul-reversed"]
    _, _, body = _fixture("doc-typesafe-noul-ok.json")
    parsed = get_adapter(cfg).parse_response(cfg, incumbent, body)
    assert (parsed.status, parsed.match_probability) == ("ok", 0.93)


# --- T-R2, T-P2: Decisions API (`luna-dec`) ------------------------------------------------------------------------


def test_r2_decisions_usage_classes_and_input_only_cost(incumbent: Prompt) -> None:
    cfg, _, body = _fixture("doc-openai-decisions-ok.json")
    usage = {
        "input_tokens": 2318,
        "input_tokens_details": {"cached_tokens": 2048, "cache_write_tokens": 0},
        "output_tokens": 7,
        "output_tokens_details": {"reasoning_tokens": 7},
    }
    parsed = get_adapter(cfg).parse_response(cfg, incumbent, {**body, "usage": usage})
    assert parsed.usage == Usage(uncached_input=270, cache_read=2048, cache_write=0, output=7, reasoning=7)
    # cached input priced as input, output free (spec §10)
    assert attempt_cost_usd(PRICES, cfg, parsed.usage) == pytest.approx(2318 * 0.10e-6)


def test_r2_openai_usage_cache_counters_above_input_never_go_negative(incumbent: Prompt) -> None:
    cfg, _, body = _fixture("doc-openai-decisions-ok.json")
    usage = {"input_tokens": 100, "input_tokens_details": {"cached_tokens": 80, "cache_write_tokens": 40}}
    parsed = get_adapter(cfg).parse_response(cfg, incumbent, {**body, "usage": usage})
    assert parsed.usage == Usage(uncached_input=0, cache_read=80, cache_write=40, output=0, reasoning=None)


def test_r2_decisions_reversed_order_accepts_same_values(incumbent: Prompt) -> None:
    _, _, body = _fixture("doc-openai-decisions-ok.json")
    cfg = CONFIGS["luna-dec-reversed"]
    parsed = get_adapter(cfg).parse_response(cfg, incumbent, body)
    assert (parsed.status, parsed.intent) == ("ok", "card_arrival")


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("doc-openai-decisions-refusal.json", "refusal"),
        ("doc-openai-decisions-two-answers.json", "unexpected_answer"),
        ("doc-openai-decisions-choice-outside-values.json", "unknown_choice"),
        ("doc-openai-decisions-probabilities-sum-0.9.json", "probabilities_sum"),
        ("doc-openai-decisions-missing-confidence.json", "missing_field"),
    ],
)
def test_p2_decisions_invalid_fixtures(incumbent: Prompt, name: str, code: str) -> None:
    parsed, request_id, _ = _parse(name, incumbent)
    assert (parsed.status, parsed.error_code) == ("invalid_output", code)
    assert parsed.intent is None and parsed.confidence is None and parsed.probabilities is None
    assert parsed.usage.uncached_input == 2318  # still billed
    _, _, body = _fixture(name)
    assert json.loads(parsed.raw_output) == body  # full response kept
    assert request_id is not None


def _mutated_decision(prompt: Prompt, mutate: Any) -> Parsed:
    cfg, _, body = _fixture("doc-openai-decisions-ok.json")
    mutate(body["answers"])
    return get_adapter(cfg).parse_response(cfg, prompt, body)


def _set_answer(field: str, value: Any) -> Any:
    def mutate(answers: list[dict[str, Any]]) -> None:
        answers[0][field] = value

    return mutate


def _edit_probabilities(edit: Any) -> Any:
    def mutate(answers: list[dict[str, Any]]) -> None:
        answers[0]["probabilities"] = edit(answers[0]["probabilities"])

    return mutate


def _scaled(factor: float) -> Any:
    return _edit_probabilities(lambda ps: [{**p, "probability": p["probability"] * factor} for p in ps])


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda a: a.clear(), "missing_answer"),
        (_set_answer("name", "department"), "wrong_answer_name"),
        (_set_answer("type", "predicate"), "wrong_answer_type"),
        (_set_answer("choice", "Card_Arrival"), "unknown_choice"),  # no case normalization: values are typed
        (_set_answer("choice", True), "unknown_choice"),
        (_set_answer("confidence", 1.2), "confidence_out_of_range"),
        (_set_answer("confidence", -0.1), "confidence_out_of_range"),
        (_set_answer("confidence", "high"), "confidence_not_numeric"),
        (lambda a: a[0].pop("probabilities"), "probabilities_missing"),
        (_edit_probabilities(lambda ps: ps[1:]), "probabilities_keys"),
        (_edit_probabilities(lambda ps: [*ps, {"value": "other", "probability": 0.0}]), "probabilities_keys"),
        (_edit_probabilities(lambda ps: [*ps[:-1], ps[0]]), "probabilities_keys"),  # duplicate value
        (_edit_probabilities(lambda ps: [{**ps[0], "probability": None}, *ps[1:]]), "probabilities_not_numeric"),
        (_scaled(1.02), "probabilities_sum"),
    ],
)
def test_p2_decisions_invalid_values(incumbent: Prompt, mutate: Any, code: str) -> None:
    parsed = _mutated_decision(incumbent, mutate)
    assert (parsed.status, parsed.error_code) == ("invalid_output", code)


@pytest.mark.parametrize("factor", [0.991, 1.009])
def test_p2_decisions_probability_sum_within_tolerance_is_ok(incumbent: Prompt, factor: float) -> None:
    assert _mutated_decision(incumbent, _scaled(factor)).status == "ok"


def test_p2_decisions_http_400_is_api_error(incumbent: Prompt) -> None:
    cfg = CONFIGS["luna-dec"]
    adapter = get_adapter(cfg)
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        error = {"error": {"type": "invalid_request_error", "code": "too_many_choices", "message": "bad"}}
        return httpx.Response(400, json=error, headers={"x-request-id": "req_dec_400"})

    async def go() -> SendResult:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            sender = Sender(client=client, adapter=adapter, api_key=FAKE_KEY, clock=FakeClock())
            return await sender.send(
                adapter.build_request(cfg, incumbent, RAW_TEXT, None),
                tokens=10,
                parse=lambda body: adapter.parse_response(cfg, incumbent, body),
                timeout_usage=Usage,
            )

    result = asyncio.run(go())
    assert (result.parsed, result.error_code) == (None, "http_400")
    assert [a.request_id for a in result.attempts] == ["req_dec_400"]
    assert str(seen[0].url) == "https://api.openai.com/v1/decisions"
    assert seen[0].headers["authorization"] == f"Bearer {FAKE_KEY}"
