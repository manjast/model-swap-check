"""Record types shared by providers, runner, cost and analysis (spec §10).

Token classes (`Usage`) follow billing: `output` is every billed output token, including
reasoning/thinking; `reasoning` is the reasoning/thinking subset of `output`, reported, never
billed twice. `uncached_input` excludes cache reads and cache writes.

Run directory layout (spec §9.3): `runs/<run_id>/run.json` is written when the run starts
(`complete: false`) and rewritten after every completed warm-up and when the run ends. Item rows
are appended to `items.jsonl` during the run; finalizing writes `items.jsonl.gz` and removes the
plain file. A `--retry-errors` pass journals each rewritten row to `items.retry.jsonl` (flushed and
fsynced per line) while `run.json` marks it in progress; finishing the pass folds the journal into
`items.jsonl.gz` and removes it. Until then, a journaled row replaces the row of the same item.
"""

from __future__ import annotations

import gzip
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Status = Literal["ok", "invalid_output", "api_error"]
Split = Literal["examples", "dev", "cert", "pilot", "aa", "latency"]
RUN_JSON = "run.json"
ITEMS_PLAIN = "items.jsonl"
ITEMS_FINAL = "items.jsonl.gz"
ITEMS_RETRY = "items.retry.jsonl"


class Usage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uncached_input: int = 0
    cache_read: int = 0
    cache_write: int = 0
    output: int = 0
    reasoning: int | None = None  # None when the provider does not report it


class Timing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headers_ms: float | None = None
    connect_ms: float | None = None
    tls_ms: float | None = None


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
    headers: dict[str, str] = {}  # the response's rate-limit and timing headers (spec §9.4), keys lowercased
    timing: Timing | None = Field(default=None, exclude_if=lambda value: value is None)


class Parsed(BaseModel):
    """What a provider adapter extracts from one successful (HTTP 2xx) response body."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "invalid_output"]
    error_code: str | None = None
    stop_reason: str | None = None
    # LLMs: the model's text (capped at 2,000 chars by the runner); for an unbilled Anthropic refusal, the
    # reported `stop_details` and `usage` as JSON (its `usage` here is zero). Jev, `luna-dec`: full response JSON.
    raw_output: str
    intent: str | None = None
    confidence: float | None = None
    probabilities: dict[str, float] | None = None  # Jev and `luna-dec` only
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
    retry_errors_passes: int  # 1 from the moment the single pass starts
    retry_errors_rewritten: int
    retry_errors_in_progress: bool = False  # the pass started and has not finished; it can only be resumed
    study_id: str | None = Field(default=None, exclude_if=lambda value: value is None)
    totals: RunTotals


def _complete_rows(data: bytes) -> list[ItemRow]:
    """Rows of a JSONL byte string up to its last newline: a killed writer can leave a partial last line,
    possibly cut inside a multibyte character, so it is dropped before decoding."""
    text = data[: data.rfind(b"\n") + 1].decode("utf-8")
    return [ItemRow.model_validate_json(line) for line in text.split("\n") if line]


def read_retry_journal(run_dir: Path) -> list[ItemRow]:
    """Rows rewritten so far by an unfinished `--retry-errors` pass, in completion order."""
    journal = run_dir / ITEMS_RETRY
    return _complete_rows(journal.read_bytes()) if journal.exists() else []


def read_rows(run_dir: Path) -> list[ItemRow]:
    """Item rows of a finalized or in-progress run. A trailing partial line (killed run) is ignored, and
    rows journaled by an unfinished retry pass replace the finalized rows of their items."""
    final, plain = run_dir / ITEMS_FINAL, run_dir / ITEMS_PLAIN
    if final.exists():
        rows = _complete_rows(gzip.decompress(final.read_bytes()))
        retried = {row.item_id: row for row in read_retry_journal(run_dir)}
        return [retried.get(row.item_id, row) for row in rows]
    if plain.exists():
        return _complete_rows(plain.read_bytes())
    return []


def read_meta(run_dir: Path) -> RunMeta:
    return RunMeta.model_validate_json((run_dir / RUN_JSON).read_text(encoding="utf-8"))
