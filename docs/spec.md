# Specification v2

**Status:** draft for review, 2026-10-21. v2 incorporates an independent review of v1. Binding for M0–M7 once merged. Values marked *(M4)* are fixed from `dev` data before the contract is frozen. Values marked *(pilot)* are resolved by the M3 pilot.

**Question.** Can a production LLM routing feature built on `gpt-4o-mini` move to a current model before OpenAI removes `gpt-4o-mini` from its API on 2027-01-14? Each candidate gets one pre-registered, replayable verdict.

**Scope (budget scenario S3):** large certification set, prompt caching on, Claude Haiku 4.5 deferred (a later `contract-v2` may add it without code changes).

## 1. Decisions under test

| ID | Incumbent → candidate | Question |
|---|---|---|
| D-A1 | `inc` → `luna-none` | OpenAI's recommended replacement, no reasoning |
| D-A2 | `inc` → `luna-low` | same model, low reasoning effort |
| D-B1 | `inc` → `haiku55-off` | cross-provider, thinking disabled |
| D-B2 | `inc` → `haiku55-low` | cross-provider, adaptive thinking at low effort |
| D-X | `inc` → `luna-none-x` | OpenAI's replacement with a prompt adapted on `dev` (§8) |

A migration here always includes recalibrating the confidence threshold on `dev` (§6); that is part of each candidate. Swapping only the model ID is reported descriptively (§7.5), without a verdict.

**Not tested:** default reasoning effort (`medium`) on either new model; Claude Haiku 4.5; multi-turn conversations; languages other than English; streaming; real production traffic.

## 2. Data

### 2.1 Sources (pinned)

| File | Source | SHA-256 |
|---|---|---|
| `train.csv` (10,003 rows) | `github.com/PolyAI-LDN/task-specific-datasets` @ `57ec275d8078af65b7731c2a98be812d844a6d6b`, `banking_data/train.csv` | `b06e26ac675513959a63135f11b94ea7786ed02da65db93a5650d8838cbc664b` |
| `test.csv` (3,080 rows) | same commit, `banking_data/test.csv` | `d12d6e3bc4c3103966ae786dc435913c0c563dfa328f5a3646d0e62cfeeb474d` |

Banking77 (Casanueva et al., 2020), CC BY 4.0. Downloaded and verified at runtime, not committed. Message texts appear in committed run records and decision records with attribution.

### 2.2 Items and scope

- **Item ID:** `train-<row>` or `test-<row>` (0-based row after the header).
- **Ground truth:** the `category` column.
- **Digest:** `sha256("model-swap-check-v1:" + item_id + ":" + text)`, hex. Used for every selection and ordering below.
- **In scope:** the 50 intents of Banking77-OOS (Zhang et al., NLP4ConvAI 2022; `github.com/jianguoz/Few-Shot-Intent-Detection` @ `fa9553312b1dba54b1be0aae2d30b13171f898e5`, `Datasets/BANKING77-OOS/train/label`).
- **Out of scope (OOS):** the other 27 intents. The feature does not know them and must escalate their messages.

Both lists, and the slice groups, are in `config/intent-groups.yaml`.

### 2.3 Splits

All selections come from `train.csv`, per intent, in ascending digest order:

- **`examples`**: the first 5 rows of each in-scope intent; 250 items. The only messages that prompt authoring may read (§3.1).
- **`dev`**: the next 40 rows of every intent, or all remaining rows if fewer (`contactless_not_working` has 35). 3,075 items, 1,075 of them OOS.
- **`cert`**: every other `train.csv` row plus all of `test.csv`. 9,758 items, 26.6% OOS.
- **`pilot`**: 100 `dev` items: for each of the 50 in-scope intents, the item with the smallest pilot digest `sha256("model-swap-check-pilot:" + item_id + ":" + text)`, plus the 50 OOS `dev` items with the smallest pilot digests.
- **`aa`**: the 3,080 `test-*` items. The second incumbent run, used for the noise floor.

`cert` slice sizes (test T-D3):

| cards | card_payments | cash | transfers | top_ups | account_other | out_of_scope | total |
|---|---|---|---|---|---|---|---|
| 1,407 | 1,473 | 966 | 1,328 | 844 | 1,143 | 2,597 | 9,758 |

### 2.4 Slices

Seven slices: the six in-scope groups (assigned from intent names by the team a bank would route to, before any model call) and `out_of_scope`.

### 2.5 Leakage rules

- Prompt authoring reads only `examples` messages and intent names.
- During D-X adaptation and the incumbent revisions of §3.4, `dev` metrics and `dev` errors may be inspected.
- No `cert` message is read by a person or model before the M5 decisions are generated.
- Texts are compared casefolded and whitespace-collapsed. No `examples` item may equal a `cert` text (none does at the pinned commit).

## 3. The feature

### 3.1 Prompt (`prompts/incumbent-v1.md`, committed before any model call)

- **Developer/system message (stable prefix):** routing instructions, then 50 catalog entries. Each entry has `<intent_id>`, a one-line description written from that intent's `examples` messages, and one example message (the intent's smallest-digest `examples` item).
  - Instructions: choose exactly one catalog intent, or `out_of_scope` if none fits. `confidence` is the probability that the chosen value is correct.
  - No OOS intent name appears in the prompt.
- **User message:** the customer message, unchanged.
- **Prefix length:** the stable prefix must be ≥ 1,100 `o200k_base` tokens, so it can be cached on every configuration (OpenAI minimum 1,024; Haiku 5.5 minimum 512). Reached through content, never padding.

### 3.2 Output schema

- Shape: `{"intent": <enum: 50 catalog IDs + "out_of_scope">, "confidence": <number>}`. Both fields required; `additionalProperties: false`.
- Delivery: sent through each provider's native structured-output mechanism.
- Confidence: Claude's API supports no numeric bounds, so our parser checks `0 ≤ confidence ≤ 1` for every provider.
- Enum matching: case-insensitive (Claude's documented casing caveat). Case-normalized matches are counted per run.

### 3.3 Routing policy with threshold τ

```
invalid output                -> escalate
intent == "out_of_scope"      -> escalate
confidence >= tau             -> auto-route to intent
otherwise                     -> escalate
```

API errors are handled in §7.4, not by this policy.

### 3.4 Incumbent competence check (before any candidate `dev` run)

**Baseline.** A leave-one-out nearest-centroid classifier over the 2,000 in-scope `dev` items:

- 50 centroids, one per in-scope intent;
- tokens are lowercase `[a-z0-9']+` words, with unigrams and bigrams as features;
- TF-IDF with smooth IDF `ln((1+N)/(1+df)) + 1`, refit per fold;
- vectors L2-normalized, cosine similarity.

**Check.** The incumbent's top-1 accuracy on the same 2,000 items must exceed the baseline's. A prediction of `out_of_scope` on an in-scope item counts as wrong.

**If it fails.** At most 2 logged prompt revisions, using `dev` only, then re-check. If it still fails, the project stops and the result is recorded. A revision changes the prompt hash, so the check runs on the incumbent alone, before any candidate `dev` run.

## 4. Configurations

| ID | API | Model | Reasoning / thinking | Temperature | Max output tokens | Caching |
|---|---|---|---|---|---|---|
| `inc` | OpenAI Responses | `gpt-4o-mini-2024-07-18` | n/a | 0 | 100 | implicit (automatic); `prompt_cache_key` = `msc-<int(digest, 16) mod 16>` |
| `luna-none` | OpenAI Responses | `gpt-6-luna` | `reasoning.effort: none` | 0 if accepted, else omitted *(pilot)* | 200 | `prompt_cache_options.mode: explicit`, one breakpoint at the end of the developer message, TTL `30m` |
| `luna-low` | same | `gpt-6-luna` | `reasoning.effort: low` | as accepted at this effort *(pilot)* | 1,024 | same |
| `haiku55-off` | Anthropic Messages | `claude-haiku-5-5` | `thinking: disabled`, `output_config.effort: low` | omitted (rejected by API) | 200 | `cache_control: ephemeral` on the system block; no top-level `cache_control` |
| `haiku55-low` | same | `claude-haiku-5-5` | adaptive thinking, `output_config.effort: low` | omitted | 1,024 | same |
| `luna-none-x` | as `luna-none` | | | | | adapted prompt (§8) |

- **Warm-up:** each run first sends one warm-up request per cache key: 16 for `inc`, 1 for the others. Warm-ups use the fixed user message `Hello`, are recorded in `run.json` with their usage, and count as spent.
- **Throughput:** concurrency 16, under the rate limits of §9.4.
- **Recorded per item:** the model ID returned by the API.

## 5. Outcomes and metrics

**Per item:** `correct_auto` (auto-routed, intent = truth), `wrong_auto` (auto-routed, intent ≠ truth, including any auto-routed OOS message) or `escalated`. Status is `ok`, `invalid_output` or `api_error`.

| Metric | Definition | Use |
|---|---|---|
| wrong-auto rate W | #`wrong_auto` / n | safety; gates G1, G2 |
| automation rate A | (#`correct_auto` + #`wrong_auto`) / n | value; gate G3 |
| valid-output rate V | #`ok` / (#`ok` + #`invalid_output`) | gate G4 |
| top-1 accuracy | intent = truth, in-scope items, τ ignored | diagnostic, §3.4 |
| OOS escalation recall | 1 − W on the `out_of_scope` slice | reported; gated through G2 |
| API error rate | #`api_error` / n | run validity, §7.4 |

**Weighted `dev` metrics** (§6) give each `dev` item the weight `cert_count(intent) / dev_count(intent)`, normalized to sum to 1, so `dev` estimates refer to the `cert` population.

## 6. Threshold calibration

- **Candidate thresholds T(config):** {0} ∪ {confidence of every `ok`, non-`out_of_scope` `dev` prediction of that configuration}.
- **Incumbent:** `τ_inc` = the smallest τ ∈ T(inc) with weighted `dev` W(τ) ≤ 2.0%. If none exists, the experiment is void: stop at M4 and record why.
- **Candidate:** `τ_c` = the smallest τ ∈ T(c) with weighted `dev` W_c(τ) ≤ weighted `dev` W_inc(τ_inc). The candidate is matched to the incumbent's operating risk; G3 then measures what it automates at that risk. If none exists, `τ_c` = 1.01 (nothing auto-routed).
- **Recording:** `τ` values, both weighted `dev` W values and the weights go into the contract.

## 7. Acceptance contract

### 7.1 Gates (candidate minus incumbent, paired on the same items, each at its own τ)

Bounds are one-sided Tango (1998) score bounds for a difference of paired proportions, computed from the discordant counts. They are deterministic (no resampling). For a confidence level q, `U_q` is the upper bound and `L_q` the lower bound. Simulated at the §2.3 slice sizes, the 95% upper bound releases a candidate that is exactly at the margin in 4.5–5.3% of runs, within Monte Carlo error of 5%. A percentile bootstrap and the normal approximation gave 5.6–6.6% and were rejected.

| Gate | Metric | PASS | FAIL | otherwise |
|---|---|---|---|---|
| G1 | W, all `cert` items | U₉₅ < δ_W | L₉₅ ≥ δ_W | UNRESOLVED |
| G2 | W, each of the 7 slices | U₉₅ < δ_S in every slice | some slice with L at 1 − 0.05/7 (Bonferroni over 7 slices) ≥ δ_S | UNRESOLVED |
| G3 | A, all `cert` items | L₉₅ > −3.0 pp | U₉₅ ≤ −3.0 pp | UNRESOLVED |
| G4 | V of the candidate | ≥ 99.5% | < 99.5% | — |

### 7.2 Verdicts

| Verdict | Rule |
|---|---|
| SHIP | all four gates PASS. Conditions always stated: the candidate's τ, and for D-X the adapted prompt |
| BLOCK | any gate FAIL |
| INCONCLUSIVE | otherwise; every UNRESOLVED gate reports the sample size needed (§7.4) |

- **Release errors:** each verdict is a single intersection–union test at α = 5% one-sided. G1–G3 all have to pass, so no correction is needed within a decision.
- **Harm side:** corrected over the 7 slices (G2 FAIL rule).
- **Family-adjusted status:** each decision record also reports the gates at U₉₉/L₉₉ (Bonferroni over the 5 decisions). This answers "is any of the five options safe?", which is the question a reader picking the best option implicitly asks.
- **Noise floor rule:** if the A/A comparison (§7.6) is FAIL on G1 or G2, every verdict becomes INCONCLUSIVE with that reason.
- **Cost and latency** are reported, not gated: all candidates are in one price tier, and latency is measured client-side from a phone. Two flags never change the verdict: `COST` if steady-traffic cost > 1.5× the incumbent's, `LATENCY` if p95 > 2× the incumbent's.

### 7.3 Margins *(M4)*

- **Grid:** δ_W ∈ {0.50, 0.75, 1.00} pp; δ_S ∈ {1.5, 2.0, 2.5, 3.0} pp. Business meaning: 0.5 pp = 5 more misrouted messages per 1,000.
- **Input:** `swapcheck report --pdisc-json` writes, per slice, the worst `dev` discordance across all five candidates at their τ. Discordance is the share where exactly one of candidate and incumbent is `wrong_auto`. Values are floored at 1%.
- **Selection:** `analysis/power.py --pdisc-json` simulates G1 + G2 with the same Tango bound and the calibration noise of §6. It selects the first pair, ordered by δ_W then δ_S, whose joint power for an equally good candidate is ≥ 80%.
- **Fallback:** if none reaches 80%, use (1.00, 3.0) and write the power into the contract.
- **Planning estimate:** with assumed discordance 3–8% (doubled for OOS), joint power at (1.00, 3.0) is 66–95% (`python analysis/power.py`).

### 7.4 Statistics

- **Paired data:** an item that is `api_error` in either arm is dropped from both arms of that comparison, and the count is reported. `invalid_output` stays and counts as escalation.
- **Bounds:** Tango score bound per gate (§7.1), inverted by bisection to 1e-9. G1 and G3 use the pooled counts over all `cert` items; G2 uses each slice's counts.
- **Cross-check:** the Wald (normal-approximation) bound, reported next to each Tango bound.
- **Sensitivity:** a cluster bootstrap that resamples intents within each slice (10,000 resamples, `numpy.random.default_rng(SeedSequence([20261021, decision_index, gate_index]))`, slices in `config/intent-groups.yaml` order, percentile bounds). Any gate whose status would change under it is reported; it never changes the verdict.
- **Sample size needed:**
  - G1/G2: n = ⌈p̂·(z₀.₉₅ + z₀.₈₀)² / (δ − d̂)²⌉ when d̂ < δ.
  - G3: n = ⌈p̂_A·(z₀.₉₅ + z₀.₈₀)² / (d̂ + δ_A)²⌉ when d̂ > −δ_A, with p̂_A the automation discordance.
  - Otherwise: "not reachable at this point estimate".
- **Output format:** decision files are rounded to 0.01 pp and contain no wall-clock fields.

### 7.5 Naive-swap analysis (descriptive)

Each candidate is also scored at `τ_inc`: estimates and two-sided 95% intervals for W and A, overall and per slice. No verdict. This shows what happens when only the model ID changes.

### 7.6 Noise floor

- **Comparison:** the `aa` run against the first incumbent run on the same 3,080 test items, through G1 and G2 at the frozen margins.
- **Reported:** the outcome flip rate, next to the `dev` discordance used for the margins.
- **Consequence:** FAIL triggers the §7.2 rule; UNRESOLVED is reported with a warning.

### 7.7 Freeze

- **Contents of `contracts/contract-v1.yaml`:**
  - configurations, with hashes of prompt and schema;
  - τ values and the weighted `dev` W values;
  - the weights;
  - margins and the power behind them;
  - slices and seeds;
  - the analysis code version;
  - the budget drop order (§9.5).
- **Timing:** committed and tagged `contract-v1` before the first `cert` call.
- **Changes:** any change after that is a new contract version with a written reason, never an edit.

## 8. Prompt adaptation (D-X)

- **Target and starting point:** `luna-none`. Iteration 0 is the incumbent prompt and does not count toward the limit.
- **Allowed changes:** instruction wording and description wording. The catalog and its examples are unchanged.
- **Limit:** at most 3 iterations, each scored on `dev` with its own τ from §6.
- **Selection:** the iteration with the highest weighted `dev` A, ties broken by fewer changed lines. Every iteration is logged with its `dev` metrics.
- **Freeze:** the selected prompt is frozen in the contract. Its `dev` run is included in the §7.3 margin input.

## 9. Runs

### 9.1 Plan

| Phase | Split | Configurations |
|---|---|---|
| Pilot (M3) | `pilot` | all five, plus `luna-none` in implicit cache mode for the caching comparison |
| Dev (M4) | `dev` | `inc` first (§3.4); then `luna-none`, `luna-low`, `haiku55-off`, `haiku55-low`; then D-X iterations |
| Cert (M5) | `cert` | in this order: OpenAI `inc`, `luna-none`, `aa` (`inc` on `aa`), `luna-none-x`, `luna-low`; Anthropic `haiku55-off`, `haiku55-low`. Exactly one run per configuration and split under a contract tag (§9.5) |

### 9.2 Errors and retries

- **Retried:** connection errors, timeouts (60 s), HTTP 408, 409, 429, 500, 502, 503, 504, 529. Exponential backoff from 1 s, ×2, full jitter, honouring `retry-after`, at most 6 attempts.
- **Not retried:** 400, 401, 403, 404, 422 → `api_error`.
- **`invalid_output`:** refusal stop reason, truncation at max tokens, unparseable JSON, intent not in the enum after case-insensitive matching, confidence missing or outside [0, 1].
- **Validity threshold:** a run is valid for `decide` only if its API error rate is ≤ 0.5%.
- **Retry pass:** one `--retry-errors` pass per run rewrites `api_error` rows in place and records the count in `run.json`. `decide` accepts the run only if the rate is ≤ 0.5% after that pass.

### 9.3 Run files and resume

- **During a run:** rows are appended to `runs/<run_id>/items.jsonl`, flushed and fsynced per line.
- **Resume:** the same `run_id` drops a trailing partial line and skips items already present.
- **Finalize:** writes `items.jsonl.gz` and `run.json` and removes the plain file.
- **New runs:** a new `run_id` always calls the API again, so `aa` is a genuine repeat.

### 9.4 Rate limits and latency

- **Limits file:** `config/limits.yaml` holds RPM and TPM per provider and model. Values are 80% of the account limits read from response headers in the pilot (OpenAI `x-ratelimit-limit-*`, Anthropic `anthropic-ratelimit-*`).
- **Enforcement:** a token bucket in the runner. 429 responses are counted per run.
- **Latency:** monotonic wall-clock time of the final attempt, non-streamed, at concurrency 16, from this machine. Reported as p50/p95 overall and split by calls with and without cache reads. Provider timing headers are stored where available. Indicative only.

### 9.5 Budget and freeze guards

- **Caps:** `config/budget.yaml` caps each provider at $10.
- **Spent:** the cost of every attempt and warm-up across all run records. An attempt that timed out is charged as full uncached input plus max output tokens.
- **Projection before the freeze (M4):** spent + every remaining planned run × per-item p90 cost from that configuration's `dev` run (`luna-none-x` uses its selected iteration).
- **Drop order:** if the projection exceeds a cap, planned `cert` runs are dropped in this order until it fits: `luna-low`, `haiku55-low`, `luna-none-x`, `aa`. If it still does not fit, M5 does not start for that provider. The resulting plan is written into the contract; dropped decisions are reported as "not run (budget)"; a missing `aa` leaves the verdicts standing with a "noise floor not measured" warning.
- **In-run stop:** a run stops when spent reaches cap − $0.50 and is marked incomplete; later runs for that provider do not start. Decisions that need an incomplete run become INCONCLUSIVE (insufficient data). Every decision needs `inc`, which is therefore run first.
- **One run per configuration:** under a given contract tag the runner refuses a second new `run_id` for the same configuration and split; only resume and `--retry-errors` are allowed. Each `cert`/`aa` run is appended to `runs/manifest.yaml` by the runner when it starts.
- **Freeze guard:** a `cert` or `aa` run starts only if tag `contract-v1` exists and `src/`, `prompts/`, `config/`, `contracts/` and `analysis/` are byte-identical to the tagged commit. `runs/` may change. `run.json` records the tag's commit.

## 10. Records

### `runs/<run_id>/run.json`

- **Identity:** run ID, configuration ID and hash, split, item-list hash, prompt hash, schema hash.
- **Environment:** requested model, returned model IDs, SDK versions, git commit, contract tag commit.
- **Run log:** warm-ups with usage, start and end times, `--retry-errors` count, 429 count.
- **Totals:** counts by status, tokens by class, billed cost.

### `runs/<run_id>/items.jsonl.gz`, one row per item

- **Row fields:** `item_id`, `status`, `error_code`, `stop_reason`, `raw_output` (≤ 2,000 chars), `intent`, `confidence`, `case_normalized`, `latency_ms`, `request_id`, `model_id`.
- **`attempts`:** a list with usage per attempt (uncached input, cache read, cache write, output, reasoning/thinking).
- **Ground truth:** not stored; `decide` joins it from the split.

### `runs/manifest.yaml`

Written by the runner (§9.5), never by hand: for each configuration and split under the contract tag, its single run ID. `decide` refuses if a run's configuration, prompt, schema or item-list hash differs from the contract, if its contract tag commit is missing, or if a `cert`/`aa` run directory for that tag is absent from the manifest.

### Other files

- **`config/prices.yaml`:** price per model and token class, with source URL and retrieval date. Cost is always computed from it.
- **`decisions/<decision_id>.md`** (generated):
  - verdict and conditions;
  - gate table (estimate, Tango bound, Wald bound, margin, status) and family-adjusted status;
  - slice table;
  - naive-swap table;
  - up to 20 messages that became `wrong_auto` under the candidate, in digest order;
  - cost and latency;
  - noise floor and sensitivity;
  - what was not tested.

## 11. Cost model and reporting

- **Cost model:** per configuration, the mean and p90 token counts per class (uncached input, cache read, cache write, output, reasoning) measured in the pilot, and then in `dev`, multiplied by `config/prices.yaml`. It drives the budget guard and test T-L4.
- **Reported per configuration**, as cost per 1,000 messages:
  - billed, from all attempts;
  - steady traffic, with the shared prefix read from cache on every call;
  - sparse traffic, with nothing cached.

**Planning estimate** (prefix ≈ 2,000 tokens, 300 reasoning tokens on `low` configurations, 90% cache hits): ≈ $6.90 OpenAI + ≈ $3.75 Anthropic = **≈ $10.70**. At 1,000 reasoning tokens it is ≈ $19.70. The caps and drop order keep actual spend within $10 per provider.

## 12. Repository and workflow

- **Language and packaging:** Python ≥ 3.12, `pyproject.toml` with pinned dependencies (`openai`, `anthropic`, `numpy`, `pyyaml`, `pydantic`, `tiktoken`; dev: `pytest`, `ruff`, `mypy`).
- **CLI:** `swapcheck`, with subcommands `data`, `run`, `decide`, `report`.
- **CI on every PR:** ruff, mypy, pytest, gitleaks, and golden replay of committed decisions.
- **Workflow:** one PR per milestone, squash-merged, with branches deleted after merge. Secrets live only in `.env` (git-ignored).

## 13. Milestones and acceptance

| Milestone | Done when |
|---|---|
| M0 scaffold, data, prompt | data download verifies both SHA-256; split and slice counts match §2.3; intent groups pass T-D4; `prompts/incumbent-v1.md` written from `examples` only and passes T-D5/T-D6; CI green |
| M1 providers, runner, records | all §4 tests of the test plan pass offline; no API key needed |
| M2 analysis | all §2, §3 and §6 tests of the test plan pass, including the simulations and golden replay on fixtures |
| M3 pilot | test plan §5 criteria met or explained in `docs/pilot.md`; §14 items answered; `config/limits.yaml` and the cost model updated |
| M4 dev and freeze | §3.4 passed; τ, margins, D-X and budget plan set by the stated rules; `contract-v1` tagged |
| M5 certification | planned `cert` and `aa` runs valid (§9.2); `runs/manifest.yaml` written; decision records generated; CI replay reproduces them |
| M6 write-up | README case study, `WALKTHROUGH.md` (reading path and likely interview questions), site case-study draft and post drafts ready for review |
| M7 publication | Stefan's review done; gitleaks over the full history clean; repository public |

## 14. Open items

| Item | Resolved at |
|---|---|
| `gpt-6-luna` accepts `temperature` at effort `none` and at `low`? | pilot |
| structured outputs with a 51-value enum on all configurations | pilot |
| `gpt-4o-mini` callable from this API account | first pilot call |
| Luna explicit vs implicit cache mode: reads, writes, billed cost on the same 100 items | pilot |
| token overhead of Claude's injected structured-output instructions | pilot |
| reasoning/thinking tokens per item at `low` (drives the budget) | pilot |
| account rate limits per provider | pilot (response headers) |
| OpenAI server timing header available through the SDK | pilot |
