"""Record types shared by providers, runner, cost and analysis (spec §10).

Token classes (`Usage`) follow billing: `output` is every billed output token, including
reasoning/thinking; `reasoning` is the reasoning/thinking subset of `output`, reported, never
billed twice. `uncached_input` excludes cache reads and cache writes.

Run directory layout (spec §9.3): `runs/<run_id>/run.json` is written when the run starts
(`complete: false`, warm-ups included) and rewritten when it ends. Item rows are appended to
`items.jsonl` during the run; finalizing writes `items.jsonl.gz` and removes the plain file.
"""

from __future__ import annotations

import gzip
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

Status = Literal["ok", "invalid_output", "api_error"]
Split = Literal["examples", "dev", "cert", "pilot", "aa"]
RUN_JSON = "run.json"
ITEMS_PLAIN = "items.jsonl"
ITEMS_FINAL = "items.jsonl.gz"


class Usage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uncached_input: int = 0
    cache_read: int = 0
    cache_write: int = 0
    output: int = 0
    reasoning: int | None = None  # None when the provider does not report it


class Attempt(BaseModel):
    """One HTTP attempt. A timed-out attempt carries an estimated, charged usage (spec §9.5)."""

    model_config = ConfigDict(extra="forbid")

    number: int  # 1-based
    http_status: int | None  # None for connection errors and timeouts
    error: str | None = None  # e.g. "timeout", "connection", "http_429"; None on success
    usage: Usage = Usage()
    usage_estimated: bool = False  # True when usage is the timeout charge, not provider-reported
    latency_ms: float | None = None
    request_id: str | None = None
    retry_after_s: float | None = None


class Parsed(BaseModel):
    """What a provider adapter extracts from one successful (HTTP 2xx) response body."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "invalid_output"]
    error_code: str | None = None
    stop_reason: str | None = None
    raw_output: str  # LLMs: the model's text (capped at 2,000 chars by the runner); Jev: full response JSON
    intent: str | None = None
    confidence: float | None = None
    probabilities: dict[str, float] | None = None  # Jev only
    match_probability: float | None = None  # jev-noul only
    case_normalized: bool = False
    model_id: str | None = None
    usage: Usage = Usage()


class ItemRow(BaseModel):
    """One row of `runs/<run_id>/items.jsonl(.gz)`. Ground truth is never stored here."""

    model_config = ConfigDict(extra="forbid")

    item_id: str
    status: Status
    error_code: str | None
    stop_reason: str | None
    raw_output: str | None
    intent: str | None
    confidence: float | None
    probabilities: dict[str, float] | None
    match_probability: float | None
    case_normalized: bool
    latency_ms: float | None  # final attempt
    request_id: str | None  # final attempt
    model_id: str | None
    attempts: list[Attempt]


class Warmup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cache_key: str | None
    attempts: list[Attempt]


class RunTotals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    by_status: dict[str, int]
    tokens: Usage  # summed over every attempt of every item and warm-up
    billed_usd: float
    case_normalized: int
    n_429: int


class RunMeta(BaseModel):
    """`runs/<run_id>/run.json`."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    config_id: str
    config_sha256: str
    split: Split
    item_list_sha256: str
    prompt_sha256: str
    schema_sha256: str
    requested_model: str
    returned_model_ids: list[str]
    versions: dict[str, str]  # python, httpx, swapcheck; Anthropic API version header
    git_commit: str
    contract_tag_commit: str | None
    warmups: list[Warmup]
    started_at: str
    ended_at: str | None
    complete: bool
    incomplete_reason: str | None  # e.g. "spend ceiling", "budget cap"
    retry_errors_passes: int
    retry_errors_rewritten: int
    totals: RunTotals


def read_rows(run_dir: Path) -> list[ItemRow]:
    """Item rows of a finalized or in-progress run. A trailing partial line (killed run) is ignored."""
    final, plain = run_dir / ITEMS_FINAL, run_dir / ITEMS_PLAIN
    if final.exists():
        text = gzip.decompress(final.read_bytes()).decode("utf-8")
    elif plain.exists():
        text = plain.read_text(encoding="utf-8")
    else:
        return []
    complete_lines = text.split("\n")[:-1]  # text after the last newline is empty or a partial row
    return [ItemRow.model_validate_json(line) for line in complete_lines if line]


def read_meta(run_dir: Path) -> RunMeta:
    return RunMeta.model_validate_json((run_dir / RUN_JSON).read_text(encoding="utf-8"))
