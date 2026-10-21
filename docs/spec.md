# Specification v1

**Status:** draft for review, 2026-10-21. Becomes binding for M0–M7 once merged. Values marked *(M4)* are fixed from `dev` data before the contract is frozen; values marked *(pilot)* are resolved by the M3 pilot.

**Question.** Can a production LLM routing feature built on `gpt-4o-mini` move to a current model before OpenAI removes `gpt-4o-mini` from its API on 2027-01-14? The answer is a pre-registered, replayable decision per candidate.

**Scope (budget scenario S3):** large certification set, prompt caching on, Claude Haiku 4.5 deferred (a later `contract-v2` may add it without code changes).

## 1. Decisions under test

| ID | Incumbent → candidate | Question |
|---|---|---|
| D-A1 | `inc` → `luna-none` | OpenAI's recommended replacement, no reasoning |
| D-A2 | `inc` → `luna-low` | same model, low reasoning effort |
| D-B1 | `inc` → `haiku55-off` | cross-provider, thinking disabled |
| D-B2 | `inc` → `haiku55-low` | cross-provider, adaptive thinking at low effort |
| D-X | `inc` → `luna-none-x` | OpenAI's replacement with a prompt adapted on `dev` (§8) |

**Not tested:** default reasoning effort (`medium`) on either new model; Claude Haiku 4.5; multi-turn conversations; languages other than English; streaming; real production traffic.

## 2. Data

### 2.1 Sources (pinned)

| File | Source | SHA-256 |
|---|---|---|
| `train.csv` (10,003 rows) | `github.com/PolyAI-LDN/task-specific-datasets` @ `57ec275d8078af65b7731c2a98be812d844a6d6b`, `banking_data/train.csv` | `b06e26ac675513959a63135f11b94ea7786ed02da65db93a5650d8838cbc664b` |
| `test.csv` (3,080 rows) | same commit, `banking_data/test.csv` | `d12d6e3bc4c3103966ae786dc435913c0c563dfa328f5a3646d0e62cfeeb474d` |

Banking77 (Casanueva et al., 2020), CC BY 4.0. The data is downloaded and verified at runtime, not committed. Message texts appear in committed run records and decision records with attribution.

### 2.2 Items

- Item ID: `train-<row>` or `test-<row>`, 0-based row index after the CSV header.
- Ground truth: the Banking77 `category`.
- In scope: the 50 intents of Banking77-OOS (Zhang et al., NLP4ConvAI 2022; list from `github.com/jianguoz/Few-Shot-Intent-Detection` @ `fa9553312b1dba54b1be0aae2d30b13171f898e5`, `Datasets/BANKING77-OOS/train/label`). The other 27 intents are **out of scope** (OOS): the feature does not know them and must escalate their messages. Both lists are in `config/intent-groups.yaml`.

### 2.3 Splits

- **`dev`**: from `train.csv`, per intent (all 77), the 20 rows with the smallest `sha256("model-swap-check-v1:" + item_id + ":" + text)` hex digest. 1,540 items, 540 of them OOS.
- **`cert`**: all other `train.csv` rows plus all `test.csv` rows. 11,543 items.
- **`pilot`**: the 100 `dev` items with the smallest digests.
- **`aa`**: the 3,080 `test-*` items of `cert` (second incumbent run for the noise floor).

`cert` slice sizes, asserted by M0 tests:

| cards | card_payments | cash | transfers | top_ups | account_other | out_of_scope | total |
|---|---|---|---|---|---|---|---|
| 1,682 | 1,698 | 1,116 | 1,553 | 994 | 1,368 | 3,132 | 11,543 |

### 2.4 Slices

Seven slices: the six in-scope groups in `config/intent-groups.yaml` (assigned from intent names by handling team, before any model call) and `out_of_scope`.

### 2.5 Leakage rule

Prompt text (descriptions, examples) may be derived only from `dev` messages. No `cert` message may be read by a person or model during prompt work.

## 3. The feature

### 3.1 Prompt

- **Developer/system message (stable prefix):** routing instructions, then the catalog: 50 lines `<intent_id>: <one-line description>`. Instructions say: choose exactly one catalog intent, or `out_of_scope` if none fits; `confidence` is the probability the chosen value is correct.
- **User message:** the customer message only, unchanged.
- Descriptions are written once from each intent's `dev` messages, with LLM assistance by the build agent, reviewed and committed before any model call (`prompts/incumbent-v1.md`).
- The stable prefix must be ≥ 1,100 `o200k_base` tokens so it is cacheable on every configuration (OpenAI minimum 1,024; Haiku 5.5 minimum 512). Reached through description detail, never through padding.

### 3.2 Output schema

`{"intent": <enum: 50 catalog IDs + "out_of_scope">, "confidence": <number>}`, both required, `additionalProperties: false`. Sent through each provider's native structured-output mechanism. Claude's API supports no numeric bounds, so `0 ≤ confidence ≤ 1` is checked by our parser for every provider. Enum values are matched case-insensitively (Claude's documented casing caveat); a case-normalized match is counted per run.

### 3.3 Routing policy with threshold τ

```
invalid output or API error   -> escalate
intent == "out_of_scope"      -> escalate
confidence >= tau             -> auto-route to intent
otherwise                     -> escalate
```

### 3.4 Incumbent competence check

On the 1,000 in-scope `dev` items, the incumbent's top-1 accuracy must exceed a leave-one-out TF-IDF nearest-centroid baseline built from the same `dev` messages. Otherwise the incumbent prompt is revised on `dev` (at most 2 revisions, each logged) before anything else runs. Prevents a strawman incumbent.

## 4. Configurations

| ID | API | Model | Reasoning / thinking | Temperature | Max output tokens | Caching |
|---|---|---|---|---|---|---|
| `inc` | OpenAI Responses | `gpt-4o-mini-2024-07-18` | n/a | 0 | 100 | implicit (automatic); `prompt_cache_key` = `msc-<sha256(item_id) mod 16>` |
| `luna-none` | OpenAI Responses | `gpt-6-luna` | `reasoning.effort: none` | 0 if accepted, else omitted *(pilot)* | 200 | `prompt_cache_options.mode: explicit`, one breakpoint at the end of the developer message, TTL `30m` |
| `luna-low` | same | `gpt-6-luna` | `reasoning.effort: low` | same | 4,000 | same |
| `haiku55-off` | Anthropic Messages | `claude-haiku-5-5` | `thinking: disabled`, `output_config.effort: low` | omitted (rejected by API) | 200 | `cache_control: ephemeral` on the system block (not top-level automatic caching) |
| `haiku55-low` | same | `claude-haiku-5-5` | adaptive thinking, `output_config.effort: low` | omitted | 4,000 | same |
| `luna-none-x` | as `luna-none` | | | | | with the adapted prompt (§8) |

Every run starts with one warm-up request and then runs at concurrency 16. Model IDs returned by the API are recorded per item.

## 5. Outcomes and metrics

Per item: `correct_auto` (auto-routed, intent = truth), `wrong_auto` (auto-routed, intent ≠ truth, including any auto-routed OOS message), `escalated`; `status` is `ok`, `invalid_output` or `api_error`.

For a run over n items (or a slice):

| Metric | Definition | Use |
|---|---|---|
| wrong-auto rate W | #`wrong_auto` / n | primary safety metric; gates G1, G2 |
| automation rate A | (#`correct_auto` + #`wrong_auto`) / n | gate G3 |
| valid-output rate V | #`ok` / (#`ok` + #`invalid_output`) | gate G4 |
| top-1 accuracy | intent = truth, in-scope items, τ ignored | diagnostic |
| OOS escalation recall | 1 − W on the `out_of_scope` slice | reported; gated through G2 |
| API error rate | #`api_error` / n | run validity (§9.3) |

## 6. Threshold calibration

- `τ` per configuration on `dev`: the smallest observed confidence value (or 0) such that W on `dev` ≤ 2.0%. If none reaches 2.0%, `τ` = 1.01 (nothing auto-routed) and the configuration is reported as unable to meet the target.
- Each candidate is judged under two policies:
  - **naive:** `τ_inc` (the model ID is swapped and nothing else changes);
  - **recalibrated:** its own `τ`.
- All `τ` values are written into the contract before `cert`.

## 7. Acceptance contract

### 7.1 Gates (candidate minus incumbent, paired on the same items)

| Gate | Metric | Pass rule |
|---|---|---|
| G1 | W, all `cert` items | upper one-sided 95% bound < δ_W |
| G2 | W, each of the 7 slices | upper bound < δ_S in every slice |
| G3 | A, all `cert` items | lower one-sided 95% bound > −3.0 pp |
| G4 | V of the candidate | observed ≥ 99.5% |

Gate status for G1–G3: **PASS** if the bound clears the margin; **FAIL** if the opposite one-sided 95% bound is beyond the margin (harm shown); **UNRESOLVED** otherwise. G4 is PASS or FAIL.

### 7.2 Verdicts

A policy is PASS if all gates pass, FAIL if any gate fails, else UNRESOLVED.

| Verdict | Rule |
|---|---|
| SHIP | naive policy PASS |
| SHIP WITH CONDITIONS | naive not PASS, recalibrated PASS (condition: use the candidate's τ); for D-X: PASS (condition: adapted prompt and its τ) |
| BLOCK | naive not PASS and recalibrated FAIL |
| INCONCLUSIVE | otherwise; each UNRESOLVED gate reports the sample size needed (§7.4) |

Cost and latency are reported, not gated (§11, §9.4): all candidates are in one price tier, and latency is measured client-side from a phone. Flags without effect on the verdict: `COST` if steady-traffic cost > 1.5× incumbent, `LATENCY` if p95 > 2× incumbent.

### 7.3 Margins *(M4)*

- δ_W ∈ {0.50, 0.75, 1.00} pp; δ_S ∈ {1.5, 2.0, 2.5, 3.0} pp. Business meaning: 0.5 pp = 5 more misrouted messages per 1,000.
- Selection: run `analysis/power.py --pdisc-json` with the worst `dev` discordance per slice across the four candidates (both policies). Choose the strictest pair (smallest δ_W, then smallest δ_S) whose joint power for an equally good candidate is ≥ 80%.
- If none reaches 80%, use (1.00, 3.0) and state the expected power in the contract.
- Planning estimate (assumed discordance 3–8%, OOS slice double): see `python analysis/power.py`.

### 7.4 Statistics

- Paired bootstrap over items, 10,000 resamples, seed 20261021, stratified by slice for G1 and G3; percentile one-sided 95% bounds.
- Cross-check: the normal-approximation bound of `analysis/power.py` and an exact McNemar test on G1 discordant pairs, both reported.
- Sensitivity: cluster bootstrap by intent; any gate whose status changes is reported in the decision record.
- Sample size for UNRESOLVED: n = ⌈p̂_disc·(z₀.₉₅ + z₀.₈₀)² / (δ − d̂)²⌉ if d̂ < δ, else "not reachable at this point estimate".
- Multiplicity: within a decision all gates must pass (intersection–union), so no per-slice correction. The five decisions are separate questions and are not corrected across.
- Noise floor: the `aa` run against the first incumbent run on the same 3,080 items gives the outcome flip rate and the W difference with its bound. Reported in every decision record.

### 7.5 Freeze

`contracts/contract-v1.yaml` holds: configurations (with hashes of prompt and schema), τ values, margins, slices, seeds, analysis version. It is committed and tagged `contract-v1` before the first `cert` call. A changed margin, slice or τ after that is a new contract version with a written reason, never an edit.

## 8. Prompt adaptation (D-X)

- **Target:** `luna-none`.
- **Allowed changes:** instruction wording, description wording, at most 2 examples per intent taken from `dev`.
- **Budget:** at most 3 iterations, evaluated on `dev` only. Selected version: lowest `dev` W at its own τ, ties broken by fewer changes.
- Every iteration is logged with its `dev` metrics. The selected prompt is frozen in the contract.

## 9. Runs

### 9.1 Plan

| Phase | Split | Configurations |
|---|---|---|
| Pilot (M3) | `pilot` | all five, plus `luna-none` in implicit cache mode for the caching comparison |
| Dev (M4) | `dev` | `inc`, `luna-none`, `luna-low`, `haiku55-off`, `haiku55-low`, X iterations |
| Cert (M5) | `cert` | the same five plus `luna-none-x`; `inc` again on `aa` |

### 9.2 Errors and retries

- Retried: connection errors, timeouts (60 s), HTTP 408, 409, 429, 500, 502, 503, 504, 529. Exponential backoff from 1 s, ×2 per attempt, full jitter, honouring `retry-after`, at most 6 attempts.
- Not retried: 400, 401, 403, 404, 422 → `api_error`.
- `invalid_output`: refusal stop reason, truncation at max tokens, unparseable JSON, intent not in the enum after case-insensitive matching, confidence missing or outside [0, 1].
- `decide` refuses a run with API error rate > 0.5%. One `--retry-errors` pass per run is allowed and recorded.

### 9.3 Resume and caching of responses

A run is identified by `run_id`. Resuming a `run_id` skips items already in its `items.jsonl`; a new `run_id` always calls the API again, so the `aa` run is a genuine repeat.

### 9.4 Latency

Monotonic wall-clock time around the final successful attempt, non-streamed, at concurrency 16, measured from this machine. Reported as p50 and p95, overall and split into calls with and without cache reads. Provider timing headers are stored where available. Indicative only.

### 9.5 Guards

- **Budget:** `config/budget.yaml` caps at $10 per provider. Before a run, spent (sum of billed cost in all run records for that provider) plus projected (remaining items × mean per-item cost from the pilot for that configuration, or the price-table estimate × 1.5 before a pilot exists) must stay under the cap, or the run does not start.
- **Freeze:** a `cert` or `aa` run starts only if tag `contract-v1` exists, the contract file is unchanged since the tag, and the working tree is clean. `run.json` records the tag's commit.

## 10. Records

- `runs/<run_id>/run.json`:
  - identity: run ID, configuration ID and hash, split, hash of the item-ID list, prompt hash, schema hash;
  - environment: requested model, set of returned model IDs, SDK versions, git commit, contract tag commit (if any);
  - timing: start and end times;
  - totals: counts by status, tokens by class, billed cost.
- `runs/<run_id>/items.jsonl.gz`, one row per item:
  - identity and timing: `item_id`, `run_id`, `attempts`, `started_at`, `latency_ms`, `request_id`, `model_id`;
  - outcome: `status`, `error_code`, `stop_reason`, `raw_output` (≤ 2,000 chars), `intent`, `confidence`, `case_normalized`;
  - usage: input uncached, cache read, cache write, output, reasoning/thinking tokens.

  Ground truth is not stored in run records; `decide` joins it from the split.
- `config/prices.yaml`: per model and token class, with source URL and retrieval date. Cost is always computed from it.
- `decisions/<decision_id>.md`, generated:
  - verdict, and the policy table;
  - gate table with estimate, bound, margin and status;
  - slice table;
  - up to 20 messages that became `wrong_auto` under the candidate;
  - cost and latency;
  - noise floor and sensitivity results;
  - what was not tested.

## 11. Cost reporting

Per configuration, cost per 1,000 messages:

- **billed:** what was actually paid;
- **steady traffic:** the shared prefix is read from cache on every call;
- **sparse traffic:** nothing is cached.

All three are computed from measured token counts and `config/prices.yaml`.

## 12. Repository and workflow

- Python ≥ 3.12, `pyproject.toml` with pinned dependencies (`openai`, `anthropic`, `numpy`, `pyyaml`, `pydantic`; dev: `pytest`, `ruff`, `mypy`), `argparse` CLI `swapcheck` with subcommands `data`, `run`, `decide`, `report`.
- CI on every PR: ruff, mypy, pytest, gitleaks, golden replay of committed decisions.
- One PR per milestone, squash-merged; branches deleted after merge. Secrets only in `.env` (git-ignored).

## 13. Milestones and acceptance

| Milestone | Done when |
|---|---|
| M0 scaffold and data | data download verifies both SHA-256 values; split counts and slice sizes match §2.3 exactly; intent groups cover the 50 in-scope intents once each and the OOS list has 27; CI green |
| M1 providers, runner, records | every request-shape, parser, retry, resume, budget and freeze test in the test plan passes offline; no API key needed |
| M2 analysis | metrics, τ, statistics, verdicts, cost and report tests pass; simulation tests show false release ≤ 5.5% at the margin and power within ±3 pp of `analysis/power.py`; golden replay reproduces byte-identical records from fixtures |
| M3 pilot | each criterion in test plan §5 met or explained; open items in §14 resolved; cost model updated with measured tokens |
| M4 dev and freeze | incumbent passes §3.4; τ, margins and X selected by the stated rules; `contract-v1` tagged |
| M5 certification | all `cert` and `aa` runs complete within the API-error limit; decision records generated; CI replay reproduces them |
| M6 write-up | README case study, `WALKTHROUGH.md` (reading path and likely interview questions), site case-study draft and post drafts ready for review |
| M7 publication | Stefan's review done; gitleaks over full history clean; repository public |

## 14. Open items

| Item | Resolved at |
|---|---|
| `gpt-6-luna` accepts `temperature` with `reasoning.effort: none`? | pilot |
| structured outputs with a 51-value enum on all configurations (OpenAI strict mode; Claude `output_config.format` on Haiku 5.5) | pilot |
| `gpt-4o-mini` callable from this API account | first pilot call |
| Luna explicit vs implicit cache mode: reads, writes, billed cost on the same 100 items | pilot |
| token overhead of Claude's injected structured-output instructions | pilot (`count_tokens` and usage) |
| OpenAI server timing header availability through the SDK | pilot |
