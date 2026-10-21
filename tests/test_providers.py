from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from swapcheck.configs import Configuration, load_configurations
from swapcheck.groups import OUT_OF_SCOPE
from swapcheck.parse import RAW_OUTPUT_CAP
from swapcheck.prompt import Prompt
from swapcheck.providers import get_adapter
from swapcheck.providers.anthropic_messages import ANTHROPIC_VERSION
from swapcheck.records import Parsed, Usage
from swapcheck.schema import llm_output_schema

FIXTURES = Path(__file__).parent / "fixtures" / "responses"
CONFIGS = load_configurations()
# luna-none-x's prompt is written at M4; every other configuration is snapshot here.
SNAPSHOT_IDS = sorted(cid for cid in CONFIGS if cid != "luna-none-x")
RAW_TEXT = "  Where's my new card?? It's been 2 weeks…\n\tI'm in Zürich 💳  "
FAKE_KEY = "sk-test-NOT-A-REAL-KEY-0123456789"


def _request(cid: str, prompt: Prompt, cache_key: str | None = None) -> dict[str, Any]:
    cfg = CONFIGS[cid]
    request = get_adapter(cfg.provider).build_request(cfg, prompt, RAW_TEXT, cache_key)
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


def test_r1_every_snapshot_configuration_has_an_expectation() -> None:
    assert set(SNAPSHOT_IDS) == set(OPENAI_EXPECTED) | set(ANTHROPIC_EXPECTED) | set(JEV_EXPECTED)


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
    request = get_adapter("anthropic").build_request(cfg, incumbent, RAW_TEXT, None)
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
        if CONFIGS[cid].provider == "openai":
            schemas.append(body["text"]["format"]["schema"])
        elif CONFIGS[cid].provider == "anthropic":
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


def test_r1_jev_refuses_alias_model(incumbent: Prompt) -> None:
    adapter = get_adapter("typesafe")
    for alias in ("jev-latest", "jev-preview"):
        cfg = CONFIGS["jev-c51"].model_copy(update={"model": alias})
        with pytest.raises(ValueError, match="pinned"):
            adapter.build_request(cfg, incumbent, RAW_TEXT, None)


def test_r1_no_credentials_in_requests(incumbent: Prompt) -> None:
    for cid in SNAPSHOT_IDS:
        cfg = CONFIGS[cid]
        adapter = get_adapter(cfg.provider)
        request = adapter.build_request(cfg, incumbent, RAW_TEXT, adapter.cache_key(cfg, "ab" * 32))
        lowered = {k.lower() for k in request.headers}
        assert not lowered & {"authorization", "x-api-key"}
        assert FAKE_KEY not in json.dumps([request.url, request.headers, request.body])
    assert get_adapter("openai").auth_headers(FAKE_KEY) == {"Authorization": f"Bearer {FAKE_KEY}"}
    assert get_adapter("anthropic").auth_headers(FAKE_KEY) == {"x-api-key": FAKE_KEY}
    assert get_adapter("typesafe").auth_headers(FAKE_KEY) == {"Authorization": f"Bearer {FAKE_KEY}"}


def test_r1_inc_prompt_cache_key_mapping(incumbent: Prompt) -> None:
    adapter = get_adapter("openai")
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
    assert get_adapter("openai").warmup_cache_keys(CONFIGS["inc"]) == [f"msc-{i}" for i in range(16)]
    for cid in SNAPSHOT_IDS:
        cfg = CONFIGS[cid]
        if cid == "inc":
            continue
        expected: list[str | None] = [] if cfg.provider == "typesafe" else [None]
        assert get_adapter(cfg.provider).warmup_cache_keys(cfg) == expected, cid


# --- T-R2: response normalization from fixtures --------------------------------------------------------------------


def _fixture(name: str) -> tuple[Configuration, httpx.Headers, dict[str, Any]]:
    doc = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return CONFIGS[doc["config_id"]], httpx.Headers(doc["headers"]), doc["body"]


def _parse(name: str, prompt: Prompt) -> tuple[Parsed, str | None, dict[str, str]]:
    cfg, headers, body = _fixture(name)
    adapter = get_adapter(cfg.provider)
    return adapter.parse_response(cfg, prompt, body), adapter.request_id(headers), adapter.rate_limit_headers(headers)


def test_r2_openai_inc_ok(incumbent: Prompt) -> None:
    parsed, request_id, limits = _parse("doc-openai-inc-ok.json", incumbent)
    assert (parsed.status, parsed.intent, parsed.confidence) == ("ok", "card_arrival", 0.93)
    assert parsed.raw_output == '{"intent":"card_arrival","confidence":0.93}'
    assert parsed.model_id == "gpt-4o-mini-2024-07-18"
    assert parsed.stop_reason == "completed"
    # cache_write_tokens absent on pre-5.6 models → 0
    assert parsed.usage == Usage(uncached_input=290, cache_read=1920, cache_write=0, output=14, reasoning=0)
    assert request_id == "req_inc_ok_0001"
    assert limits == {
        "openai-processing-ms": "412",
        "x-ratelimit-limit-requests": "30000",
        "x-ratelimit-remaining-requests": "29999",
        "x-ratelimit-reset-requests": "2ms",
        "x-ratelimit-limit-tokens": "150000000",
        "x-ratelimit-remaining-tokens": "149997600",
        "x-ratelimit-reset-tokens": "0s",
    }


def test_r2_openai_cache_write_reasoning_and_case_normalization(incumbent: Prompt) -> None:
    parsed, request_id, _ = _parse("doc-openai-luna-low-cache-write.json", incumbent)
    # The message item is not the first output item (a reasoning item precedes it).
    assert (parsed.status, parsed.intent, parsed.case_normalized) == ("ok", "Refund_not_showing_up", False)
    assert parsed.usage == Usage(uncached_input=39, cache_read=0, cache_write=2201, output=212, reasoning=196)
    assert parsed.model_id == "gpt-6-luna"
    assert request_id == "req_luna_write_0002"


def test_r2_openai_cache_read(incumbent: Prompt) -> None:
    parsed, _, _ = _parse("doc-openai-luna-none-cache-read.json", incumbent)
    assert (parsed.status, parsed.intent, parsed.confidence) == ("ok", OUT_OF_SCOPE, 0.71)
    assert parsed.usage == Usage(uncached_input=35, cache_read=2201, cache_write=0, output=15, reasoning=0)


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
    parsed = get_adapter("openai").parse_response(cfg, incumbent, body)
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


def test_p2_r2_anthropic_refusal(incumbent: Prompt) -> None:
    parsed, request_id, _ = _parse("doc-anthropic-refusal.json", incumbent)
    assert (parsed.status, parsed.error_code, parsed.stop_reason) == ("invalid_output", "refusal", "refusal")
    assert parsed.usage == Usage(uncached_input=2757, reasoning=None)  # thinking_tokens unreported
    assert request_id == "req_01XFUDYJgAACzvnptvVoYEL"


def test_p2_r2_anthropic_truncation(incumbent: Prompt) -> None:
    parsed, _, _ = _parse("doc-anthropic-max-tokens.json", incumbent)
    assert (parsed.status, parsed.error_code, parsed.stop_reason) == ("invalid_output", "truncated", "max_tokens")
    assert parsed.usage.output == 4096 and parsed.usage.reasoning == 4096


def test_r2_jev_c51(incumbent: Prompt) -> None:
    parsed, request_id, _ = _parse("doc-typesafe-c51-ok.json", incumbent)
    _, _, body = _fixture("doc-typesafe-c51-ok.json")
    answer = body["answers"]["intent"]
    assert (parsed.status, parsed.intent, parsed.confidence) == ("ok", "card_arrival", answer["confidence"])
    assert parsed.probabilities == answer["probabilities"]
    assert parsed.probabilities is not None and list(parsed.probabilities) == incumbent.enum
    assert parsed.match_probability is None
    assert parsed.model_id == "jev-1.13.0"
    assert parsed.usage == Usage(uncached_input=1832, output=34)
    assert json.loads(parsed.raw_output) == body
    assert request_id == "ts_req_c51_0001"


def test_r2_jev_noul(incumbent: Prompt) -> None:
    parsed, request_id, _ = _parse("doc-typesafe-noul-ok.json", incumbent)
    _, _, body = _fixture("doc-typesafe-noul-ok.json")
    assert (parsed.status, parsed.intent) == ("ok", "Refund_not_showing_up")
    assert parsed.match_probability == 0.93
    assert parsed.probabilities == body["answers"]["intent"]["probabilities"]
    assert json.loads(parsed.raw_output) == body
    assert request_id == "ts_req_noul_0002"


def test_r2_raw_output_capped_for_llms_only(incumbent: Prompt) -> None:
    cfg, _, body = _fixture("doc-anthropic-off-cache-write.json")
    long_text = '{"intent": "card_arrival", "confidence": 0.9' + " " * 3000 + "}"
    body = {**body, "content": [{"type": "text", "text": long_text}]}
    parsed = get_adapter("anthropic").parse_response(cfg, incumbent, body)
    assert parsed.status == "ok"  # parsed from the full text, stored capped
    assert parsed.raw_output == long_text[:RAW_OUTPUT_CAP]
    cfg, _, body = _fixture("doc-typesafe-c51-ok.json")
    body = {**body, "note": "x" * 3000}  # Jev raw_output is the full response JSON, never capped
    jev = get_adapter("typesafe").parse_response(cfg, incumbent, body)
    assert json.loads(jev.raw_output) == body


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
    return get_adapter("typesafe").parse_response(cfg, prompt, body)


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
    _, _, body = _fixture("doc-typesafe-noul-ok.json")
    parsed = get_adapter("typesafe").parse_response(CONFIGS["jev-noul-reversed"], incumbent, body)
    assert (parsed.status, parsed.match_probability) == ("ok", 0.93)
