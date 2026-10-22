"""T-D5 to T-D8: prompt definition, leakage, the Jev and the Decisions translations (spec §2.5, §3.1, §4.1, §4.2)."""

from __future__ import annotations

import re

import yaml

from swapcheck import data, prompt
from swapcheck.groups import OUT_OF_SCOPE, IntentGroups
from swapcheck.prompt import Prompt


def oos_token_hits(text: str, groups: IntentGroups) -> list[str]:
    return [
        name
        for name in groups.out_of_scope
        if re.search(rf"(?<![A-Za-z0-9_?]){re.escape(name)}(?![A-Za-z0-9_?])", text)
    ]


def test_d5_catalog_and_enum_order(incumbent: Prompt, groups: IntentGroups) -> None:
    expected = sorted((i for g in groups.in_scope_groups.values() for i in g), key=lambda s: (s.casefold(), s))
    assert incumbent.intents == expected
    assert incumbent.intents[:3] == ["activate_my_card", "apple_pay_or_google_pay", "automatic_top_up"]
    assert incumbent.intents.index("Refund_not_showing_up") == incumbent.intents.index("pending_transfer") + 1
    assert incumbent.enum == [*expected, OUT_OF_SCOPE]


def test_d5_no_out_of_scope_names(incumbent: Prompt, groups: IntentGroups) -> None:
    file_text = prompt.INCUMBENT_PROMPT.read_text(encoding="utf-8")
    translations = (prompt.JEV_PROMPT.read_text("utf-8"), prompt.DECISIONS_PROMPT.read_text("utf-8"))
    for text in (file_text, incumbent.developer_message(), *translations):
        assert oos_token_hits(text, groups) == []
    # The matcher must not fire inside a longer in-scope name.
    assert oos_token_hits("card_payment_wrong_exchange_rate", groups) == []
    assert oos_token_hits("about exchange_rate.", groups) == ["exchange_rate"]

    instructions = " ".join(
        [
            incumbent.routing_instruction,
            incumbent.oos_clause,
            incumbent.output_clause,
            prompt.JEV_OOS_CRITERION,
            prompt.JEV_NOUL_QUESTION,
        ]
    ).casefold()
    for name in groups.out_of_scope:
        spaced = name.replace("_", " ").casefold()
        assert not re.search(rf"\b{re.escape(spaced)}\b", instructions), name


def test_d5_instruction_parts_and_prefix_length(incumbent: Prompt) -> None:
    message = incumbent.developer_message()
    assert message.startswith(f"{incumbent.routing_instruction} {incumbent.oos_clause}\n\n")
    assert f"\n\n{incumbent.output_clause}\n\n" in message
    assert all(f"intent: {e.intent}\n" in message for e in incumbent.catalog)
    assert prompt.prefix_tokens(incumbent) >= 1100


def prompt_sentences(incumbent: Prompt) -> list[str]:
    lines = [
        re.sub(r"^(intent|description|example): ", "", line)
        for line in incumbent.developer_message().splitlines()
        if line.strip()
    ]
    lines += [prompt.JEV_OOS_CRITERION, prompt.JEV_NOUL_QUESTION]
    sentences = [s for line in lines for s in re.split(r"(?<=[.!?])\s+", line)]
    return sentences + [e.example for e in incumbent.catalog]


def test_d6_no_dev_or_cert_text_in_the_prompt(incumbent: Prompt, splits: dict[str, list[data.Item]]) -> None:
    held_out = {data.normalize(it.text) for name in ("dev", "cert") for it in splits[name]}
    hits = [s for s in prompt_sentences(incumbent) if data.normalize(s) in held_out]
    assert hits == []


def test_d6_examples_come_from_the_examples_split(incumbent: Prompt, splits: dict[str, list[data.Item]]) -> None:
    """Each example is its intent's smallest-digest `examples` message, verbatim (spec §3.1)."""
    first: dict[str, data.Item] = {}
    for it in splits["examples"]:  # splits are in ascending digest order
        first.setdefault(it.intent, it)
    assert {e.intent: e.example for e in incumbent.catalog} == {i: it.text for i, it in first.items()}
    cert = {data.normalize(it.text) for it in splits["cert"]}
    assert not any(data.normalize(it.text) in cert for it in splits["examples"])


def test_d7_jev_translation_reproduces_the_committed_file(incumbent: Prompt) -> None:
    committed = prompt.JEV_PROMPT.read_text(encoding="utf-8")
    assert prompt.render_jev_yaml(incumbent) == committed

    designs = yaml.safe_load(committed)
    c51, noul = designs["jev-c51"]["choice"], designs["jev-noul"]["choice"]
    expected_criteria = {e.intent: {"description": e.description, "example": e.example} for e in incumbent.catalog}
    assert c51["instructions"] == f"{incumbent.routing_instruction} {incumbent.oos_clause}"
    assert list(c51["criteria"]) == [*incumbent.intents, OUT_OF_SCOPE]
    assert c51["criteria"][OUT_OF_SCOPE] == "The customer message is about none of the other options."
    assert c51["criteria"] == {**expected_criteria, OUT_OF_SCOPE: prompt.JEV_OOS_CRITERION}
    assert noul["instructions"] == incumbent.routing_instruction
    assert list(noul["criteria"]) == incumbent.intents
    assert noul["criteria"] == expected_criteria
    assert designs["jev-noul"]["noul"]["instructions"] == {
        "question": "Does the customer message ask about any of the topics in catalog?",
        "catalog": {e.intent: e.description for e in incumbent.catalog},
    }
    assert incumbent.output_clause not in committed


def test_d8_decisions_translation_reproduces_the_committed_file(incumbent: Prompt) -> None:
    committed = prompt.DECISIONS_PROMPT.read_text(encoding="utf-8")
    assert prompt.render_decisions_yaml(incumbent) == committed

    designs = yaml.safe_load(committed)
    assert list(designs) == ["luna-dec"]
    (question,) = designs["luna-dec"]["questions"]
    assert list(question) == ["type", "name", "instructions", "choices"]
    assert (question["type"], question["name"]) == ("choice", "intent")
    assert question["instructions"] == f"{incumbent.routing_instruction} {incumbent.oos_clause}"
    assert [c["value"] for c in question["choices"]] == [*incumbent.intents, OUT_OF_SCOPE]
    for entry, choice in zip(incumbent.catalog, question["choices"], strict=False):
        assert choice["description"] == f"{entry.description} Example: {entry.example}"
    assert question["choices"][-1] == {
        "value": OUT_OF_SCOPE,
        "description": "The customer message is about none of the other options.",
    }
    assert incumbent.output_clause not in committed
