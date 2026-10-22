# Specification v4

**Status:** draft for review, 2026-10-21. v2 incorporated an independent review of v1. v3 adds the reasoning-effort sweep and TypeSafe Jev. v4 adds OpenAI's Decisions API (D-O). Binding for M0–M7 once merged. Values marked *(M4)* are fixed from `dev` data before the contract is frozen. Values marked *(pilot)* are resolved by the M3 pilot.

**Question.** A production support-message router built on `gpt-4o-mini` has to move: OpenAI removes `gpt-4o-mini` from its API on 2027-01-14. There are four ways out:

- OpenAI's named successor, `gpt-6-luna`;
- a rival LLM, `claude-haiku-5-5`;
- a new class of model: TypeSafe's Jev, a "System One" decision model launched on 2026-09-15 that returns calibrated probabilities instead of text;
- OpenAI's answer to that class: the Decisions API (public beta since 2026-10-06), which puts `gpt-6-luna` behind a decision interface (questions with fixed options in, per-option probabilities and a confidence out). Comparing it with `luna-none` isolates the interface (same model family); comparing it with Jev isolates the model type (an LLM serving decisions vs a purpose-built decision model). How OpenAI runs Luna behind this endpoint is not documented.

Which of them can take over without routing more messages wrongly, and at which setting? Every model is scored against Banking77's ground-truth labels. The old model sets the bar to clear, not the answer to copy. Each candidate gets one pre-registered, replayable verdict, and settings are chosen on `dev` data, not guessed.

**Scope (budget scenario S3):** large certification set, prompt caching on, Claude Haiku 4.5 and `gpt-4.1-mini` deferred (a later `contract-v2` may add either without code changes).

## 1. Decisions under test

| ID | Incumbent → candidate | Question |
|---|---|---|
| D-A1 | `inc` → `luna-none` | OpenAI's named successor, no reasoning |
| D-A2 | `inc` → `luna-R` | same model at the reasoning effort selected on `dev` (§8.1); not run if `dev` shows no gain |
| D-B1 | `inc` → `haiku55-off` | rival LLM, thinking disabled |
| D-B2 | `inc` → `haiku55-R` | rival LLM at the effort selected on `dev` (§8.1); not run if `dev` shows no gain |
| D-J | `inc` → `jev-D` | decision model, request design selected on `dev` (§8.2) |
| D-O | `inc` → `luna-dec` | OpenAI's Decisions API on `gpt-6-luna` (§4.2) |
| D-X | `inc` → `luna-none-x` | OpenAI's successor with a prompt adapted on `dev` (§8) |

A migration here always includes recalibrating the confidence threshold on `dev` (§6); that is part of each candidate. Swapping only the model ID is reported descriptively (§7.5), without a verdict. Candidates are compared with the incumbent at its production setting, whatever their own reasoning level: `gpt-4o-mini` has no reasoning setting.

**Deployment assumption:** the router triages support messages into team queues (asynchronous, as with Banking77's single-turn app support queries). A second of model time does not affect the customer there, so latency is reported and flagged, never gated. A live-chat or voice entry point would need a latency limit; this project does not test that use, because latency measured from a phone over a mobile network cannot carry a hard limit.

**Not tested:** reasoning efforts above `medium`; Claude Haiku 4.5; `gpt-4.1-mini` (same shutdown date and named successor as `gpt-4o-mini`); Jev 1.14 (`jev-preview`) and other decision models (Laya, Kev); live-chat latency limits; multi-turn conversations; languages other than English; streaming; real production traffic.

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

- **Developer/system message (stable prefix):** routing instructions, then the 50 catalog entries. Each entry has `<intent_id>`, a one-line description written from that intent's `examples` messages, and one example message (the intent's smallest-digest `examples` item).
  - **Catalog order** (every configuration, every enum, every Jev option list): `sorted(ids, key=lambda s: (s.casefold(), s))`, with `out_of_scope`, where it exists, always last.
  - **Instructions:** three marked parts, so the Jev translation can reuse them exactly. `routing_instruction`: choose exactly one catalog intent for the customer message. `oos_clause`: answer `out_of_scope` if none fits. `output_clause`: the JSON fields, and `confidence` as the probability that the chosen value is correct.
  - No OOS intent name appears in the prompt.
- **User message:** the customer message, unchanged.
- **Jev translation (`prompts/jev-v1.yaml`):** generated from the incumbent prompt by the fixed transformation in §4.1, never edited by hand.
- **Prefix length:** the stable prefix must be ≥ 1,100 `o200k_base` tokens, so it can be cached on every configuration (OpenAI minimum 1,024; Haiku 5.5 minimum 512). Reached through content, never padding.

### 3.2 Output schema

- **LLMs:** `{"intent": <enum: 50 catalog IDs + "out_of_scope">, "confidence": <number>}`, both required, `additionalProperties: false`, through each provider's native structured-output mechanism. Claude's API supports no numeric bounds, so our parser checks `0 ≤ confidence ≤ 1` for every LLM. Enum values are matched case-insensitively (Claude's documented casing caveat); case-normalized matches are counted per run.
- **Jev:** typed by the API. The Choice answer's `choice` is the intent and its `confidence` the confidence. The `probabilities` and, for `jev-noul`, the Noul probability are stored per item (§10).
- **Decisions API:** typed by the API. The choice answer's `choice` is the intent and its `confidence` the confidence (undefined in OpenAI's docs; the pilot checks it against the probabilities, §14). The `probabilities` list is stored per item as a map. A `refusal` answer is `invalid_output`.

### 3.3 Routing policy with threshold τ

```
invalid output                -> escalate
intent == "out_of_scope"      -> escalate
confidence >= tau             -> auto-route to intent
otherwise                     -> escalate
```

For `jev-noul`, a match probability < 0.5 escalates before the threshold is checked (TypeSafe's documented "does anything fit?" pattern).

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
| `inc` | OpenAI Responses | `gpt-4o-mini-2024-07-18` | none (no reasoning model) | 0 | 100 | implicit (automatic); `prompt_cache_key` = `msc-<int(digest, 16) mod 16>` |
| `luna-none` | OpenAI Responses | `gpt-6-luna` | `reasoning.effort: none` | 0 (allowed only at effort `none`, per OpenAI's GPT-6 guide; confirmed in the pilot) | 200 | `prompt_cache_options: {mode: explicit, ttl: 30m}`, one `prompt_cache_breakpoint` on the developer message's text part |
| `luna-low` | same | `gpt-6-luna` | `reasoning.effort: low` | omitted (rejected when effort is not `none`) | 1,024 | same |
| `luna-medium` | same | `gpt-6-luna` | `reasoning.effort: medium` (the model's default) | omitted | 4,096 | same |
| `haiku55-off` | Anthropic Messages | `claude-haiku-5-5` | `thinking: disabled`, `output_config.effort: low` | omitted (rejected by API) | 200 | `cache_control: ephemeral` on the system block; no top-level `cache_control` |
| `haiku55-low` | same | `claude-haiku-5-5` | adaptive thinking, `output_config.effort: low` | omitted | 1,024 | same |
| `haiku55-medium` | same | `claude-haiku-5-5` | adaptive thinking, `output_config.effort: medium` (the model's default) | omitted | 4,096 | same |
| `jev-c51` | TypeSafe `POST /v1/systemone` | `jev-1.13.0` (what `jev-latest` resolves to on 2026-10-21) | n/a | n/a | n/a (output is typed) | n/a |
| `jev-noul` | same | `jev-1.13.0` | n/a | n/a | n/a | n/a |
| `luna-none-x` | as `luna-none` | | | | | adapted prompt (§8.3) |
| `luna-dec` | OpenAI `POST /v1/decisions` | `gpt-6-luna` (the only ID; no dated snapshot exists, so it cannot be pinned) | n/a (no setting) | n/a | n/a (output is typed) | none sent (OpenAI bills no cache reads or writes here) |

`luna-R`, `haiku55-R` and `jev-D` name whichever configuration §8.1 and §8.2 select. `luna-dec`'s returned model ID is recorded per item; a change during the project is reported.

- **Warm-up:** each LLM run first sends one warm-up request per cache key: 16 for `inc`, 1 for the other Responses and Messages configurations, none for Jev and `luna-dec`. Warm-ups use the fixed user message `Hello`, are recorded in `run.json` with their usage, and count as spent.
- **Throughput:** concurrency 16, under the rate limits of §9.4.
- **Recorded per item:** the model ID returned by the API.

### 4.1 Jev requests

The transformation from `prompts/incumbent-v1.md` is fixed; T-D7 checks that applying it reproduces `prompts/jev-v1.yaml` exactly.

- **Both designs:** `state` = the customer message string, unchanged. Choice `criteria` = the 50 catalog intents in catalog order, each mapped to `{"description": <description>, "example": <example message>}`, copied verbatim. `output_clause` is dropped: Jev's output is typed, and its confidence is computed by the API.
- **`jev-c51`:** Choice `instructions` = `routing_instruction` + " " + `oos_clause`, verbatim. One more criterion appended last: `"out_of_scope": "The customer message is about none of the other options."`
- **`jev-noul`:** Choice `instructions` = `routing_instruction` only, so it does not mention an option that does not exist. A Noul question in the same request: `instructions` = `{"question": "Does the customer message ask about any of the topics in catalog?", "catalog": {<intent>: <description>, … in catalog order}}`.
- **Model:** pinned by version ID, never by alias.
- **Option order:** TypeSafe documents a lean toward the first option, so the pilot reverses the 50 intents (keeping `out_of_scope` last) for both designs and reports order sensitivity per design (§14).

### 4.2 Decisions API requests (`luna-dec`)

Generated from `prompts/incumbent-v1.md` by a fixed transformation into `prompts/decisions-v1.yaml`, never edited by hand (T-D8). One design only: OpenAI's guide recommends a fallback option for inputs no category covers, which is the same pattern as the incumbent's `out_of_scope` enum value and as `jev-c51`.

- **Body:** `model` = `gpt-6-luna`; `input` = the customer message string, unchanged; `questions` = one `choice` question named `intent`.
- **`instructions`:** `routing_instruction` + " " + `oos_clause`, verbatim. `output_clause` is dropped (typed output).
- **`choices`:** the 50 catalog intents in catalog order, each `{"value": <intent>, "description": <description> + " Example: " + <example message>}` (the API has no example field, so the example travels in the description and both decision models receive the same information), then `{"value": "out_of_scope", "description": "The customer message is about none of the other options."}`.
- **Option order:** the pilot also runs the 50 intents reversed (`out_of_scope` kept last) and reports order sensitivity (§14), as for Jev.

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
| NOT RUN | the candidate never reached `cert`, with reason `no dev gain` (§8.1) or `budget` (§9.5). `decide` writes a short record with the `dev` numbers and no gate table; the manifest lists the decision as not run |

- **Release errors:** each verdict is a single intersection–union test at α = 5% one-sided. G1–G3 all have to pass, so no correction is needed within a decision.
- **Harm side:** corrected over the 7 slices (G2 FAIL rule).
- **Family-adjusted status:** each decision record also reports the gates at U and L for one-sided 1 − 0.05/7 (Bonferroni over the 7 decisions). This answers "is any of the options safe?", which is the question a reader picking the best option implicitly asks. Decisions not run do not reduce the divisor.
- **Noise floor rule:** if the A/A comparison (§7.6) is FAIL on G1 or G2, every verdict becomes INCONCLUSIVE with that reason. NOT RUN decisions stay NOT RUN.
- **Cost and latency** are reported, not gated (deployment assumption, §1). Two flags never change the verdict: `COST` if steady-traffic cost > 1.5× the incumbent's, `LATENCY` if p95 > 2× the incumbent's. Reasoning/thinking tokens per message are reported next to latency as a speed measure that does not depend on our network.

### 7.3 Margins *(M4)*

- **Grid:** δ_W ∈ {0.50, 0.75, 1.00} pp; δ_S ∈ {1.5, 2.0, 2.5, 3.0} pp. Business meaning: 0.5 pp = 5 more misrouted messages per 1,000.
- **Input:** `swapcheck report --pdisc-json PATH` writes, per slice, the worst `dev` discordance across the LLM candidate configurations in the final `cert` plan, taken after the §9.5 budget plan, each at its τ. Discordance is the unweighted share, after dropping items that are `api_error` in either arm, where exactly one of candidate and incumbent is `wrong_auto`. Values are floored at 1%. The two decision interfaces (Jev and `luna-dec`) are excluded from this input, so a structurally different output cannot loosen every LLM decision's margins; D-J and D-O use the same margins (one business tolerance for every candidate) and each record states its own power at them, computed the same way from its `dev` discordance (written next to PATH as `<stem>.D-J.json` and `<stem>.D-O.json` when planned).
- **Selection:** `analysis/power.py --pdisc-json` simulates G1 + G2 with the same Tango bound and the calibration noise of §6. It selects the first pair, ordered by δ_W then δ_S, whose joint power for an equally good candidate is ≥ 80%.
- **Fallback:** if none reaches 80%, use (1.00, 3.0) and write the power into the contract.
- **Planning estimate:** with assumed discordance 3–8% (doubled for OOS), joint power at (1.00, 3.0) is 65–95% (`python analysis/power.py`).

### 7.4 Statistics

- **Paired data:** an item that is `api_error` in either arm is dropped from both arms of that comparison, and the count is reported. `invalid_output` stays and counts as escalation.
- **Bounds:** Tango score bound per gate (§7.1), inverted by bisection to 1e-9. G1 and G3 use the pooled counts over all `cert` items; G2 uses each slice's counts.
- **Cross-check:** the Wald (normal-approximation) bound, reported next to each Tango bound.
- **Sensitivity:** a cluster bootstrap that resamples intents within each slice (10,000 resamples, `numpy.random.default_rng(SeedSequence([20261021, decision_index, gate_index]))`, slices in `config/intent-groups.yaml` order, percentile bounds). Any gate whose status would change under it is reported; it never changes the verdict.
- **Sample size needed:**
  - G1/G2: n = ⌈p̂·(z₀.₉₅ + z₀.₈₀)² / (δ − d̂)²⌉ when d̂ < δ.
  - G3: n = ⌈p̂_A·(z₀.₉₅ + z₀.₈₀)² / (d̂ + δ_A)²⌉ when d̂ > −δ_A, with p̂_A the automation discordance.
  - Otherwise: "not reachable at this point estimate"; with no discordant pairs (p̂ = 0, where the formula gives 0): "no discordant pairs observed".
- **Decision indices** (bootstrap seeds, record order): 1–7 = D-A1, D-A2, D-B1, D-B2, D-J, D-O, D-X, as in §1; gate_index 1–3 = G1–G3. G4 has no bound and is not resampled.
- **Output format:** decision files are rounded to 0.01 pp and contain no wall-clock fields.

### 7.5 Naive-swap analysis (descriptive)

Each LLM candidate is also scored at `τ_inc`: unweighted estimates and two-sided 95% Wilson score intervals for W and A, overall and per slice. No verdict. This shows what happens when only the model ID changes. D-J and D-O report "not applicable": their confidence comes from a decision interface on a different scale, and moving to either is not a model-ID swap.

### 7.6 Noise floor

- **Comparison:** the `aa` run against the first incumbent run on the same 3,080 test items, through G1 and G2 at the frozen margins.
- **Reported:** the outcome flip rate, next to the `dev` discordance used for the margins.
- **Consequence:** FAIL triggers the §7.2 rule; UNRESOLVED is reported with a warning.

### 7.7 Freeze

- **Contents of `contracts/contract-v1.yaml`:**
  - configurations, with hashes of prompt and schema;
  - τ values and the weighted `dev` W and A values;
  - the weights, as the `dev` and `cert` intent counts they are computed from;
  - margins, the `dev` discordance behind them and the power per decision;
  - the §8 selection records (reasoning level per vendor, Jev design, D-X iteration and prompt hash);
  - slices and seeds;
  - the analysis code version;
  - the budget plan: planned `cert` runs, drop order and NOT RUN decisions with reasons (§9.5);
  - the pilot's option-order sensitivity per decision interface, as changed and total items (§14).
- **Timing:** committed and tagged `contract-v1` before the first `cert` call.
- **Changes:** any change after that is a new contract version with a written reason, never an edit.

## 8. Selections made on `dev`

All three selections use weighted `dev` metrics at each configuration's own τ (§6), are logged with their numbers, and are frozen in the contract. In §8.2 and §8.3, A values are computed exactly with `fractions.Fraction` (the weights are ratios of counts) and compared exactly, so boundary cases do not depend on floating-point summation order.

### 8.1 Reasoning effort (D-A2, D-B2)

**Why this rule.** Reasoning at `medium` costs about $0.0005 per message, far less than the value of one more message routed without a person. So any real automation gain pays for itself, and the only thing the rule has to guard against is noise. That noise has two sources: which items happen to be in `dev`, and the thresholds τ, which are fitted on those same items. The test below resamples both, instead of using a fixed number of points.

**Items.** For a comparison of X with Y (same vendor), the `dev` items used are those present and not `api_error` in X, Y and `inc`. The §5 weights are renormalized over that set, and the dropped count is logged. `invalid_output` counts as not auto-routed (§3.3). A `dev` run that is incomplete (stopped at its §9.5 ceiling) is treated like a skipped one: its level is not in E.

**Gain test.** X *really gains* over Y iff both hold:

- **Recalibrating bootstrap:** in each of 2,000 resamples, draw `dev` items with replacement within each intent; recompute `τ_inc`, `τ_X` and `τ_Y` by §6 on the resample; compute d̄* = weighted A_X − weighted A_Y. The 10th percentile of d̄* (`numpy.quantile`, `method="lower"`) must be > 0. RNG: `numpy.random.default_rng(SeedSequence([20261021, 81, vendor_index, comparison_index]))`, with vendor_index 0 = OpenAI, 1 = Anthropic and comparison_index 0 = `low` vs `none/off`, 1 = `medium` vs `none/off`, 2 = `medium` vs `low`. Threshold comparisons are exact (integer weights scaled by the least common multiple of the `dev` intent counts). A resample in which `τ_inc` is unreachable does not void the experiment: there the incumbent takes τ = 1.01 (weighted W = 0), the candidates are matched to that, and the number of such resamples is logged.
- **Small-count guard:** an exact one-sided sign test on the unweighted discordant counts (X auto-routed and Y not, vs the reverse) gives p < 0.10. This stops a gain resting on a handful of items, for example when Y ends with τ = 1.01 and auto-routes nothing.

**Selection**, with `none/off` the no-reasoning configuration:

- **Qualifying levels:** E = the levels in {`low`, `medium`} that really gain over `none/off`.
- **Choice:** if E is empty, D-A2/D-B2 is NOT RUN (`no dev gain`), reported with the `dev` numbers. Otherwise `R` = `medium` if `medium` ∈ E and (`low` ∉ E or `medium` really gains over `low`); else `R` = `low`. The cheaper level wins unless the dearer one shows a real gain.
- **Error rate, stated:** with no true gain, up to three 90% tests per vendor make a reasoning level qualify by chance in roughly 15–20% of cases per vendor. That is accepted: the cost is one unneeded `cert` run, and release is still controlled by G1–G3.
- **Budget substitution:** if §9.5 would drop `R` = `medium` for budget and `low` ∈ E, `low` replaces it before anything is dropped; the substitution is recorded in the contract.
- **Always certified:** the no-reasoning configuration (`luna-none`, `haiku55-off`), the cheapest and fastest option.
- **Skipped `dev` runs:** a level whose `dev` run was skipped by the pre-`dev` budget gate (§9.5) is not in E.
- **Not peeking:** this rule is fixed before any `dev` run. Results seen early in the `dev` order (the incumbent, Jev) do not change it.

### 8.2 Jev request design (D-J)

`jev-D` = whichever of `jev-c51` and `jev-noul` has the higher A, ties going to `jev-c51` (the same contract as the LLMs). Only one Jev design goes to `cert`.

### 8.3 Prompt adaptation (D-X)

- **Target and starting point:** `luna-none`. Iteration 0 is the incumbent prompt and does not count toward the limit.
- **Allowed changes:** instruction wording and description wording. The catalog and its examples are unchanged.
- **Limit:** at most 3 iterations, each scored on `dev` with its own τ from §6.
- **Selection:** the iteration with the highest weighted `dev` A, ties broken by fewer changed lines. Every iteration is logged with its `dev` metrics.
- **Freeze:** the selected prompt is frozen in the contract.

## 9. Runs

### 9.1 Plan

| Phase | Split | Configurations |
|---|---|---|
| Pilot (M3) | `pilot` | all eleven configurations in §4 except `luna-none-x`; plus `luna-none` in implicit cache mode (caching comparison), and both Jev designs and `luna-dec` with reversed option order (order sensitivity) |
| Dev (M4) | `dev` | in this order: `inc` (§3.4 first); `jev-c51`, `jev-noul`, `luna-dec`; `luna-none`, `haiku55-off`; `luna-low`, `haiku55-low`; D-X iterations; `luna-medium`, `haiku55-medium` last (either may already have been skipped by the pre-`dev` gate, §9.5) |
| Cert (M5) | `cert` | in this order: OpenAI `inc`, `luna-none`, `aa` (`inc` on `aa`), `luna-dec`, `luna-none-x`, `luna-R`; Anthropic `haiku55-off`, `haiku55-R`; TypeSafe `jev-D`. `R` runs only if §8.1 certifies it. Exactly one run per configuration and split under a contract tag (§9.5) |

### 9.2 Errors and retries

- **Retried:** connection errors, timeouts (60 s), HTTP 408, 409, 429, 500, 502, 503, 504, 529. Exponential backoff from 1 s, ×2, full jitter, honouring `retry-after`, at most 6 attempts.
- **Not retried:** 400, 401, 403, 404, 422 → `api_error`; also a 429 whose body reports an exhausted quota or spend limit (OpenAI `insufficient_quota` and the spend/credit-limit codes), which retrying cannot fix.
- **`invalid_output` (LLMs):** refusal stop reason, truncation at max tokens, unparseable JSON, intent not in the enum after case-insensitive matching, confidence missing or outside [0, 1].
- **`invalid_output` (Jev):** a missing or extra answer key; a `choice` outside the criteria keys; `confidence` or Noul probability missing or outside [0, 1]; `probabilities` missing or summing outside 1 ± 0.01. A 400 (including `max_tokens_exceeded`) is `api_error`.
- **`invalid_output` (Decisions API):** not exactly one answer, or its `name` is not `intent`; a `refusal` answer; a `choice` outside the choice values; `confidence` missing or outside [0, 1]; `probabilities` missing, with values other than the choice values, or summing outside 1 ± 0.01.
- **Validity threshold:** a run is valid for `decide` only if its API error rate is ≤ 0.5%.
- **Retry pass:** one `--retry-errors` pass per run rewrites `api_error` rows in place and records the count in `run.json`. Rewritten rows keep their earlier attempts (still charged) and are journaled to `items.retry.jsonl` as they complete, with `retry_errors_in_progress` set in `run.json`, so a killed pass resumes instead of starting a second one. `decide` accepts the run only if the rate is ≤ 0.5% after that pass.

### 9.3 Run files and resume

- **During a run:** rows are appended to `runs/<run_id>/items.jsonl`, flushed and fsynced per line.
- **Resume:** the same `run_id` drops a trailing partial line and skips items already present. Each completed warm-up is written to `run.json` as it finishes.
- **Finalize:** writes `items.jsonl.gz` and `run.json` and removes the plain file.
- **New runs:** a new `run_id` always calls the API again, so `aa` is a genuine repeat.

### 9.4 Rate limits and latency

- **Limits file:** `config/limits.yaml` holds, per provider and model, request and token limits with an explicit unit (per minute or per second). Values are 80% of the account limits: OpenAI and Anthropic per minute, read from response headers in the pilot (`x-ratelimit-limit-*`, `anthropic-ratelimit-*`); TypeSafe per second, entered from its console because no header is documented.
- **Enforcement:** a sliding-window limiter per provider in the limit's own unit: a request starts only if the requests and estimated tokens of the last window (60 s or 1 s), plus its own, stay within the limit. So no limit is exceeded in any window. 429 responses are counted per run.
- **Latency:** monotonic wall-clock time of the final attempt, non-streamed, at concurrency 16, from this machine. Reported as p50/p95 overall and split by calls with and without cache reads. Each attempt stores the response's rate-limit and timing headers (§10). Indicative only.

### 9.5 Budget and freeze guards

- **Caps:** `config/budget.yaml` caps OpenAI at $15 (raised from $10 when D-O was added), Anthropic at $10 and TypeSafe at $5 (Stefan's TypeSafe budget).
- **Spent:** the cost of every attempt and warm-up across all run records, following provider billing (an Anthropic refusal before any output in an unbilled category — `cyber`, `general_harms` or none — costs $0; its reported counts are kept in `raw_output`). An attempt that timed out is charged as full uncached input plus max output tokens; "full input" is the whole request body the adapter sends, in `o200k_base` tokens, times a safety factor (1.0 OpenAI, 1.35 Anthropic and TypeSafe, for their own tokenizers and Claude's injected structured-output prompt; the pilot checks it).
- **Admission:** every HTTP attempt, including retries and warm-ups, starts only if spent + the reservations of attempts in flight + its own reservation stays within the run's ceiling, and is charged when it ends. A reservation is the full-input estimate at the provider's highest input price (cache write where it is dearer) plus max output tokens.
- **Pre-`dev` gate (after the pilot):** spent + every planned `dev` run + the mandatory `cert` runs (`inc`, `luna-none`, `aa` for OpenAI; `haiku55-off` for Anthropic), each × per-item p90 cost from the pilot, must stay ≤ cap − $0.50. If not, the `*-medium` `dev` run of that vendor is skipped, then `*-low`. Each `dev` run gets a spend ceiling that keeps the mandatory `cert` reserve; reaching it stops the run as incomplete without affecting later runs.
- **Projection before the freeze (M4):** spent + every remaining planned run × per-item p90 cost from that configuration's `dev` run (`luna-none-x` uses its selected iteration).
- **Drop order:** if the projection exceeds cap − $0.50 (the in-run stop level, so a plan that fits is never cut short), first apply the §8.1 substitution (`medium` → `low`), then drop planned `cert` runs in this order until it fits: `luna-R`, `haiku55-R`, `luna-none-x`, `luna-dec`, `aa`. If it still does not fit, M5 does not start for that provider. The resulting plan is written into the contract; dropped decisions are NOT RUN (`budget`); a missing `aa` leaves the verdicts standing with a "noise floor not measured" warning.
- **In-run stop:** a run stops when spent reaches cap − $0.50 (or its admission no longer fits) and is marked incomplete; later `cert`/`aa` runs for that provider do not start (the CLI refuses them). Decisions that need an incomplete run become INCONCLUSIVE (insufficient data). Every decision needs `inc`, which is therefore run first.
- **One run per configuration:** under a given contract tag the runner refuses a second new `run_id` for the same configuration and split; only resume and `--retry-errors` are allowed. Each `cert`/`aa` run is appended to `runs/manifest.yaml` by the runner when it starts.
- **Freeze guard:** a `cert` or `aa` run starts only if tag `contract-v1` exists and `src/`, `prompts/`, `config/`, `contracts/` and `analysis/` are byte-identical to the tagged commit. `runs/` may change. `run.json` records the tag's commit.

## 10. Records

### `runs/<run_id>/run.json`

- **Identity:** run ID, configuration ID and hash, split, item-list hash, prompt hash, schema hash.
- **Environment:** requested model, returned model IDs, versions (Python, `httpx`, `swapcheck`, the Anthropic API version header), git commit, contract tag commit.
- **Run log:** warm-ups with usage, start and end times, `--retry-errors` count, 429 count.
- **Totals:** counts by status, tokens by class, billed cost.

### `runs/<run_id>/items.jsonl.gz`, one row per item

- **Row fields:** `item_id`, `status`, `error_code`, `stop_reason`, `raw_output` (LLMs: ≤ 2,000 chars of model text, or for an unbilled refusal the reported `stop_details` and usage; Jev and `luna-dec`: the full response JSON, uncapped; `api_error`: the error body, ≤ 2,000 chars), `intent`, `confidence`, `probabilities` (Jev and `luna-dec`, else null), `match_probability` (`jev-noul` only, else null), `case_normalized`, `latency_ms`, `request_id`, `model_id`.
- **`attempts`:** a list with usage per attempt (uncached input, cache read, cache write, output, reasoning/thinking) and the response's rate-limit and timing headers (e.g. `openai-processing-ms`). Jev usage maps to uncached input and output (output priced at $0). `luna-dec` usage maps like the Responses API; its output is priced at $0.
- **Ground truth:** not stored; `decide` joins it from the split.

### `runs/manifest.yaml`

Written by the runner (§9.5), never by hand: for each configuration and split under the contract tag, its single run ID. `decide` refuses if a run's configuration, prompt, schema or item-list hash differs from the contract, if its contract tag commit is missing, or if a `cert`/`aa` run directory for that tag is absent from the manifest.

### Other files

- **`config/prices.yaml`:** price per price key and token class, with source URL and retrieval date. The price key is the model ID, except for `luna-dec`, priced as `gpt-6-luna@decisions` ($0.10 per million input tokens; no output charge; any reported cached tokens are priced as input, since OpenAI states that no cache-read discount applies). Cost is always computed from it.
- **`decisions/<decision_id>.md`** (generated):
  - verdict and conditions; for D-J and D-O, the option-order sensitivity of the certified interface, stated as a limitation when more than 5% of choices changed (compared exactly);
  - gate table (estimate, Tango bound, Wald bound, margin, status) and family-adjusted status;
  - slice table;
  - naive-swap table;
  - up to 20 messages that became `wrong_auto` under the candidate, in digest order;
  - cost, latency, and reasoning/thinking tokens per message (mean and p95);
  - noise floor and sensitivity;
  - what was not tested.

## 11. Cost model and reporting

- **Cost model:** per configuration, the mean and p90 token counts per class (uncached input, cache read, cache write, output, reasoning) per item, summed over the item's attempts (so retries and timeout charges count), measured in the pilot and then in `dev`, multiplied by `config/prices.yaml`. Percentiles use `numpy.quantile(method="higher")`. It drives the budget guard and test T-L4.
- **Reported per configuration**, as cost per 1,000 messages:
  - billed, from all attempts;
  - steady traffic, with the shared prefix read from cache on every call;
  - sparse traffic, with nothing cached.

**Planning estimate** from the pilot's per-item p90 cost (`python analysis/pilot.py`; [`pilot.md`](pilot.md)), every planned run included, before any reasoning variant is certified:

| Provider | Pilot + `dev` + `cert` without a reasoning variant | + `R` = `low` in `cert` | + `R` = `medium` in `cert` |
|---|---|---|---|
| OpenAI | ≈ $9.05 (of which `luna-dec` ≈ $3.00) | + ≈ $0.70 | + ≈ $1.20 |
| Anthropic | ≈ $1.95 | + ≈ $1.70 | + ≈ $1.90 |
| TypeSafe | ≈ $3.10 (both designs on `dev`) | — | — |

Every plan fits its cap − $0.50, `medium` included. Measured reasoning/thinking tokens per message (mean / p90): `luna-low` 8 / 42, `luna-medium` 73 / 168, `haiku55-low` 73 / 220, `haiku55-medium` 114 / 269, against the earlier assumption of 300 at `low` and 1,000 at `medium`.

## 12. Repository and workflow

- **Language and packaging:** Python ≥ 3.12, `pyproject.toml` with pinned dependencies (`httpx`, `numpy`, `pyyaml`, `pydantic`, `tiktoken`; dev: `pytest`, `ruff`, `mypy`). The four APIs (OpenAI Responses and Decisions, Anthropic Messages, TypeSafe System One) are called over plain HTTP, not through vendor SDKs: one retry policy for all providers (SDKs retry on their own), request bodies that tests can snapshot exactly, and raw response JSON for the records.
- **CLI:** `swapcheck`, with subcommands `data`, `prompt` (prompt size and hash; generates the Jev and Decisions translations, `--check` in CI), `run` (`--run-id`, `--retry-errors`, `--ceiling-usd`; `--capture-dir` also saves every 2xx response in the fixture format, used by the pilot), `decide` (`--runs-dir`, `--contract`, `--output-dir`; writes `decisions/*.md`, exits non-zero listing the problems when it refuses), `report` (`--pdisc-json PATH` for §7.3).
- **CI on every PR:** ruff, mypy, pytest, gitleaks, and golden replay of committed decisions.
- **Workflow:** one PR per milestone, squash-merged, with branches deleted after merge. Secrets live only in `.env` (git-ignored).

## 13. Milestones and acceptance

| Milestone | Done when |
|---|---|
| M0 scaffold, data, prompt | data download verifies both SHA-256; split and slice counts match §2.3; intent groups pass T-D4; `prompts/incumbent-v1.md` written from `examples` only and passes T-D5/T-D6; CI green |
| M1 providers, runner, records | all §4 tests of the test plan pass offline; no API key needed |
| M2 analysis | all §2, §3 and §6 tests of the test plan pass, including the simulations and golden replay on fixtures |
| M3 pilot | test plan §5 criteria met or explained in `docs/pilot.md`; §14 items answered; `config/limits.yaml` and the cost model updated |
| M4 dev and freeze | §3.4 passed; τ, reasoning levels (§8.1), Jev design (§8.2), D-X (§8.3), margins and budget plan set by the stated rules; `contract-v1` tagged |
| M5 certification | planned `cert` and `aa` runs valid (§9.2); `runs/manifest.yaml` written; decision records generated; CI replay reproduces them |
| M6 write-up | README case study, `WALKTHROUGH.md` (reading path and likely interview questions), site case-study draft and post drafts ready for review |
| M7 publication | Stefan's review done; gitleaks over the full history clean; repository public |

## 14. Open items

Answered by the M3 pilot on 2026-10-22, with evidence, in [`pilot.md`](pilot.md); the TypeSafe account limit was read from its console.

| Item | Resolved at |
|---|---|
| `gpt-6-luna` accepts `temperature: 0` at effort `none` (documented; confirmed on the first call) | pilot |
| structured outputs with a 51-value enum on all configurations | pilot |
| `gpt-4o-mini` callable from this API account | first pilot call |
| Luna explicit vs implicit cache mode: reads, writes, billed cost on the same 100 items | pilot |
| token overhead of Claude's injected structured-output instructions | pilot |
| reasoning/thinking tokens per item at `low` and `medium` (drives the budget) | pilot |
| account rate limits per provider (OpenAI, Anthropic per minute; TypeSafe per second) | pilot (response headers and console) |
| OpenAI server timing header (`openai-processing-ms`, documented) present on Responses calls | pilot |
| Jev option-order sensitivity, per design: share of pilot items whose choice changes when the 50 intents are reversed (`out_of_scope` kept last) | pilot (reported; a share > 5% for the selected design is stated as a limitation in the D-J record) |
| Jev latency from this machine (TypeSafe's docs: "most queries complete in about 100 ms", measured at its own location) | pilot |
| `luna-dec` option-order sensitivity (as for Jev) | pilot (reported; a share > 5% is stated as a limitation in the D-O record) |
| Decisions API `confidence`: which function of the probabilities it is (OpenAI does not define it; the documented examples fit `(p_max − 1/n) / (1 − 1/n)`, as for Jev) | pilot |
| Decisions API: reported `cached_tokens`, `x-request-id` and rate-limit headers present; returned model ID | pilot |
| `luna-dec` latency from this machine (OpenAI: "up to 10x faster than GPT-6 Luna through the Responses API") | pilot |
