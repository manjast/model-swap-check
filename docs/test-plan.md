# Test plan v4

Every test traces to a section of [`spec.md`](spec.md). Offline tests (§1–§4, §6) run in CI without API keys. The pilot (§5) is the only live check before `dev` runs. Tests that only show that a value was passed through, or that a mock echoed its input, do not belong here.

## 1. Data and feature definition (M0)

| ID | Test | Spec |
|---|---|---|
| T-D1 | Download verifies both SHA-256 values; a corrupted file fails with a clear error | §2.1 |
| T-D2 | Splits reproduce exactly: 250 `examples`, 3,075 `dev` (1,075 OOS), 9,758 `cert`, 3,080 `aa` ⊂ `cert`. `pilot` ⊂ `dev` has 100 items: one per in-scope intent plus 50 OOS. `examples`, `dev` and `cert` are pairwise disjoint and together cover all 13,083 rows | §2.3 |
| T-D3 | `cert` slice sizes equal the §2.3 table and `analysis/power.py` `CERT_SLICES` | §2.3, §2.4 |
| T-D4 | Intent groups: 50 in-scope intents, each in exactly one group; 27 OOS; union = the 77 Banking77 intents | §2.2, §2.4 |
| T-D5 | Prompt: the catalog has exactly the 50 in-scope IDs in the order `sorted(ids, key=lambda s: (s.casefold(), s))`, asserted as an exact sequence, and the LLM enum is that sequence plus `out_of_scope` last. No OOS name occurs anywhere as a whole token, matched with `(?<![A-Za-z0-9_?])name(?![A-Za-z0-9_?])`, so `exchange_rate` inside `card_payment_wrong_exchange_rate` is not a hit. The instruction text also contains no OOS name in its space-separated form; descriptions and examples are exempt from that check because in-scope intents legitimately talk about "exchange rate". The three instruction parts of §3.1 are present and marked. Stable prefix ≥ 1,100 `o200k_base` tokens | §3.1 |
| T-D7 | Jev translation: applying the §4.1 transformation to `prompts/incumbent-v1.md` reproduces `prompts/jev-v1.yaml` exactly for both designs (same criteria text and order; `jev-c51` with `routing_instruction` + `oos_clause` and the fixed `out_of_scope` criterion last; `jev-noul` with `routing_instruction` only and the fixed Noul instruction object); `output_clause` appears in neither | §3.1, §4.1 |
| T-D8 | Decisions translation: applying the §4.2 transformation to `prompts/incumbent-v1.md` reproduces `prompts/decisions-v1.yaml` exactly: one `choice` question named `intent`, `instructions` = `routing_instruction` + " " + `oos_clause`, the 50 choices in catalog order with description + " Example: " + example, `out_of_scope` last with the fixed description; `output_clause` absent | §4.2 |
| T-D6 | Leakage: no casefolded, whitespace-collapsed `cert` or `dev` text equals any prompt sentence or example. Every example comes from `examples`. Short accidental phrase hits need an allowlist entry with a reason | §2.5 |

## 2. Parsing, outcomes, metrics, thresholds, cost (M1–M2)

| ID | Test | Spec |
|---|---|---|
| T-P1 | Parser: valid output → `ok` with intent and confidence | §3.2 |
| T-P2 | Parser, LLMs: malformed JSON, missing field, unknown intent, confidence < 0, > 1 or non-numeric, refusal, truncation → `invalid_output` with the matching `error_code`. Parser, Jev: missing or extra answer key, choice outside the criteria, confidence or Noul probability outside [0, 1], probabilities missing or summing outside 1 ± 0.01 → `invalid_output`. Parser, Decisions API: no answer or two answers, wrong name, `refusal` answer, choice outside the values, confidence outside [0, 1], probabilities missing, with other values, or summing outside 1 ± 0.01 → `invalid_output`; HTTP 400 → `api_error` | §3.2, §9.2 |
| T-P3 | Parser: `refund_not_showing_up` → matches `Refund_not_showing_up`, `case_normalized = true`, counted in the run totals | §3.2 |
| T-O1 | Routing table: every combination of status × intent (catalog / `out_of_scope`) × confidence vs τ (below / equal / above) × truth (same in-scope / other in-scope / OOS) gives the §3.3/§5 outcome; for `jev-noul`, a match probability below 0.5 escalates regardless of confidence and 0.5 itself does not | §3.3, §5 |
| T-M1 | Metrics on a hand-built run of 20 items equal hand-computed W, A, V, top-1, OOS recall and API error rate, overall and per slice; weighted `dev` W equals a hand computation with the §5 weights | §5 |
| T-M3 | Paired comparison drops items that are `api_error` in either arm and reports the count; `invalid_output` stays as escalation | §7.4 |
| T-C1 | τ on constructed data: `τ_inc` is the smallest qualifying value in T(inc); 0 when everything auto-routed already meets 2%; `out_of_scope` and invalid predictions are excluded from T; void-experiment signal when unreachable; `τ_c` is matched to the incumbent's weighted W; `τ_c` = 1.01 when unreachable; raises if given any `cert` item | §6 |
| T-B1 | Competence baseline on a hand-computed corpus of 6 documents and 2 intents: IDF refit per fold, L2 normalization and leave-one-out predictions equal the hand values | §3.4 |
| T-X1 | D-X selection on fixture iteration results: highest weighted A wins, ties go to fewer changed lines, iteration 0 is never counted toward the limit of 3 | §8.3 |
| T-X2 | Reasoning selection, through the real weighting and τ code. Gain test on constructed `dev` runs where every confidence is 1.0, so τ cannot move: n = 3,075, n10 = 62, n01 = 31 (+1.01 pp) qualifies; n10 = 500, n01 = 469 (+1.01 pp, much noisier) fails; the bootstrap 10th percentile agrees with the fixed-τ normal bound within 0.1 pp in both. A fixture whose wrong items sit near τ yields a wider interval than the fixed-τ normal bound (recalibration noise is included). The batched resample fit equals the exact `Fraction` fit, including rational ties at the limit; a resample with unreachable `τ_inc` takes 1.01, matches the candidates to W = 0 and is counted. Small-count guard: n10 = 2, n01 = 0 with a strong weighted bound fails the sign test. Items: `api_error` in any of X, Y, `inc` is dropped with weights renormalized; an incomplete run is excluded from E. Selection: E empty → NOT RUN (`no dev gain`); `low` and `medium` both gain but `medium` does not really gain over `low` → `R` = `low`; `medium` gains over `none` while `low` does not → `R` = `medium`; a skipped level is not in E; budget substitution `medium` → `low` when `low` ∈ E. Same seed → same result | §8, §8.1 |
| T-X3 | Jev design selection on fixture results: higher A wins, a tie goes to `jev-c51` | §8.2 |
| T-X4 | D-X prompts: every `prompts/dx/iteration-<n>.md` and the frozen `prompts/luna-none-x.md` keeps the catalog intents and their examples, and passes the T-D5 out-of-scope name and T-D6 leakage checks. Changed lines (the §8.3 tie-break) count the replaced, removed and added lines of the rendered developer message | §2.5, §8.3 |
| T-K1 | Cost from hand-built attempt rows for all three providers: billed (all attempts, warm-ups, a timed-out attempt charged as full input + max output; TypeSafe input-only), steady and sparse per 1,000 messages; mean and p90 per class | §9.5, §11 |

## 3. Statistics and verdicts (M2)

| ID | Test | Spec |
|---|---|---|
| T-S1 | Tango score: the statistic is 0 at d = (n10 − n01)/n; the restricted MLE solves its likelihood equation within 1e-9; the inverted bound satisfies T(bound) = −z within 1e-9; at n ≥ 5,000 the Tango and Wald bounds agree within 0.05 pp | §7.1, §7.4 |
| T-S2 | Edge cases: zero discordant pairs, all discordant pairs on one side, n10 = n01; the bound stays finite and the gate status is defined | §7.1 |
| T-S3 | False release: true difference = margin, p_disc ∈ {0.03, 0.08}, the §2.3 slice sizes, δ_W = 0.50 pp and δ_S = 2.0 pp. G1 alone and every G2 slice alone each certify in ≤ 5% + 2 Monte Carlo SE of 16,000 simulated runs | §7.1 |
| T-S4 | Power: true difference = 0, same inputs; the gate code's certification rate equals `analysis/power.py` without calibration noise within ±1.5 pp (both use the Tango test) | §7.3 |
| T-S6 | Sample size: G1/G2 and G3 formulas equal the closed forms, with the correct direction for G3; "not reachable" on the wrong side of the margin; "no discordant pairs observed" instead of n = 0 | §7.4 |
| T-S7 | On constructed runs, the cluster bootstrap reports a status change when intents are heterogeneous; the A/A comparison flags FAIL on a constructed unstable incumbent | §7.4, §7.6 |
| T-M2 | Margin selection from a fixture `dev.json`: `power.py` selects the first pair meeting 80% in δ_W-then-δ_S order, applies the 1% floor, and exits 2 with the fallback when none qualifies; `report --pdisc-json` takes the worst discordance over LLM configurations in the final `cert` plan only, ignoring Jev, `luna-dec` and dropped runs; the D-J and D-O records state their own power at the selected margins | §7.3 |
| T-V1 | Verdict table on constructed gate results: SHIP, BLOCK, INCONCLUSIVE (with sample sizes), NOT RUN with both reasons (short record, no gate table), the D-X conditions, the family-adjusted column (1 − 0.05/7), the A/A downgrade, the G2 composite rules (one slice FAIL vs some UNRESOLVED), `τ_c` = 1.01 → G3 FAIL → BLOCK, the naive-swap sections of D-J and D-O reading "not applicable", and their option-order line with the limitation above 5% only (5/100 is not one) | §7.1, §7.2, §7.5, §14 |
| T-V2 | Byte-identical decision record from the same inputs and seeds; no wall-clock fields; values rounded to 0.01 pp | §7.4 |
| T-V3 | COST and LATENCY flags appear at the stated ratios and never change the verdict; decision records list reasoning/thinking tokens per message (mean, p95) for every configuration | §7.2, §10 |
| T-V4 | Policy analysis (amendment 1): on constructed runs, each configuration's `τ_2%` is the smallest supported τ with its own weighted `dev` W ≤ 2% (1.01 when none); the `cert` section reports W and A at `τ_2%` with hand-checked Wilson intervals and the paired A difference against the incumbent with its Tango bounds; the G3 limitation line appears exactly when the incumbent's `dev` A at `τ_inc` is below 3.0 pp; verdicts are identical with and without the section | §7.8 |
| T-V5 | Jev at its top confidence (amendment 2): on constructed runs, `τ_J2` is the smallest supported τ of the gated signal with weighted `dev` W ≤ 2% (1.01 when none), and s ignores the match probability whenever the Choice confidence is below 1.00; the report refuses when the `jev-noul` run under `contract-v2` is missing or when `contract-v2`'s `inc` or `jev-c51` hashes differ from `contract-v1`'s; it reports J1 and J2 with hand-checked counts | §7.9 |
| T-V6 | Risk-limit sensitivity (amendment 3): on constructed runs, each configuration's W and A at its frozen τ_L match hand counts on the items paired with the incumbent (an API error in either arm dropped), `jev-noul` routes on the J2 signal, and the A difference against the incumbent at the same limit matches; the report refuses a run contract other than `contract-v1` or `contract-v2`, a configuration hash that differs from the run's contract, and a threshold list that does not match the limits | §7.10 |

## 4. Providers, runner, guards (M1)

| ID | Test | Spec |
|---|---|---|
| T-R1 | Request snapshots per configuration: model ID, reasoning/thinking settings, temperature only where allowed, max tokens, identical JSON schema for the LLMs, and the user message (Jev: `state`; `luna-dec`: `input`) equal to the raw customer text. Cache settings: OpenAI explicit breakpoint at the end of the developer message; Anthropic `cache_control` on the system block and none at top level; `prompt_cache_key` mapping for `inc`. Jev: pinned version ID (never an alias), state and question shapes per §4.1, reversed option order only in the pilot order-sensitivity run. `luna-dec`: `POST /v1/decisions`, body per §4.2 with no cache, reasoning, temperature or max-token parameters, reversed option order only in the pilot order-sensitivity run | §4, §4.1, §4.2, §3.1, §3.2 |
| T-R2 | Response normalization from recorded real responses (pilot fixtures, including one `jev-c51`, one `jev-noul` and one `luna-dec` response): text, usage classes incl. cache read/write and reasoning tokens, stop reason, request ID, returned model ID; Jev and Decisions probabilities, Noul probability and the full response JSON; `luna-dec` costs input only | §10 |
| T-R3 | Retry policy with a fake transport: retryable codes are retried with backoff up to 6 attempts and `retry-after` is honoured; non-retryable codes are not retried; final failure → `api_error`; every attempt's usage, request ID and rate-limit headers are kept | §9.2, §9.4, §10 |
| T-R4 | Runner with a fake provider: concurrency ≤ 16; a per-minute limit is never exceeded in any 60 s window and a per-second limit (TypeSafe) in any 1 s window; warm-ups (16 for `inc`) complete before the fan-out | §4, §9.4 |
| T-R5 | Resume: a killed run with a partial last line resumes with the same `run_id`; no item is requested twice and the finalized file has exactly one row per item. A new `run_id` requests every item | §9.3 |
| T-R6 | Budget: the pre-`dev` gate skips `*-medium` then `*-low` `dev` runs when the mandatory `cert` reserve would not fit, and a `dev` run stops at its own ceiling without blocking later runs; the pre-freeze projection over all planned runs applies the substitution and then the drop order; a run that is not affordable does not start; a `cert` run stops at cap − $0.50 and is marked incomplete | §9.5 |
| T-R7 | Freeze guard: a `cert` run refuses without the tag or with a modified file under `src/`, `prompts/`, `config/`, `contracts/` or `analysis/`. It starts when only `runs/` changed, including with an earlier run directory present and when resuming a partial run. A second new `run_id` for the same configuration and split under the tag is refused; resume and `--retry-errors` are allowed | §9.5 |
| T-R8 | `decide` refuses a run whose API error rate is > 0.5%; after one `--retry-errors` pass it accepts only if the rate is ≤ 0.5% | §9.2 |
| T-R9 | Records validate against the §10 field lists, including `probabilities` and `match_probability` (null where not applicable) and uncapped Jev `raw_output`; ground truth is absent from item rows | §10 |
| T-R10 | The runner appends each `cert`/`aa` run to `runs/manifest.yaml` at start, and NOT RUN decisions are listed with their reason. `decide` refuses a manifest entry whose configuration, prompt, schema or item-list hash, or contract tag commit, does not match the contract, and refuses when a run directory under the tag is missing from the manifest | §7.2, §9.5, §10 |
| T-R11 | `cert` run order and drop order: the planner orders runs as §9.1, skips `luna-R`/`haiku55-R` when §8.1 does not certify them, substitutes `low` for a dropped `medium` when `low` qualifies, drops `luna-R`, `haiku55-R`, `luna-none-x`, `luna-dec`, `aa` in that order, and stops a provider's M5 when the projection still exceeds its cap; after an in-run stop no later run for that provider starts | §8.1, §9.1, §9.5 |
| T-R12 | Latency study with mocked HTTP: rotated sequential schedule, frozen hashes, shared-provider per-attempt budget stop and incomplete-report refusal, hand-computed timing quantiles and connection counts, spend inclusion, and decision replay unchanged by study records | §9.6 |

## 5. Pilot acceptance (M3, live, ≈ $0.30)

| ID | Criterion | Spec |
|---|---|---|
| T-L1 | Smoke: each configuration has ≤ 1 invalid output in 100 and no API errors after retries | §5, §9.2 |
| T-L2 | Cache: after warm-up, share of calls with cache reads measured and reported for every LLM configuration; ≥ 90% expected for the Luna and Haiku 5.5 configurations; `inc` measured only (implicit, best-effort) | §4 |
| T-L3 | Luna explicit vs implicit cache mode on the same items: reads, writes and billed cost recorded; the `cert` mode confirmed or changed with a reason | §14 |
| T-L4 | Cost model built from measured token counts (§11); budget projection for `dev` and `cert` updated | §11 |
| T-L5 | Every §14 open item has a recorded answer in `docs/pilot.md` | §14 |
| T-L6 | Real responses saved as fixtures for T-R2, with request IDs kept and no secrets | §10 |
| T-L7 | Latency p50/p95, overall and split by cache read, computed from the pilot records, for every configuration including Jev | §9.4 |
| T-L8 | Option-order sensitivity per decision interface (both Jev designs, `luna-dec`): share of pilot items whose choice changes between normal and reversed order of the 50 intents (`out_of_scope` kept last), reported | §14 |
| T-L9 | Reasoning tokens per item at `low` and `medium` for both vendors measured; the §11 estimate and the §9.5 projection updated before any `dev` run | §11 |

## 6. Replay and CI (M2, M5)

| ID | Test | Spec |
|---|---|---|
| T-G1 | Golden replay: `swapcheck decide` on committed fixture runs (M2: `tests/test_golden.py`, a synthetic 210-item split over all 7 slices with `inc`, `aa` and candidate runs incl. NOT RUN decisions; run by CI's pytest) and on the real runs (M5) reproduces byte-identical decision records; a changed input changes the affected record only | §10 |
| T-G2 | CI runs ruff, mypy, pytest and gitleaks on every PR. A CI step writes a generated fake key to a temporary file outside the repository and asserts that gitleaks fails on it; nothing secret-shaped is ever committed | §12 |
