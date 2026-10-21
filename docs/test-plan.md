# Test plan v1

Every test traces to a section of [`spec.md`](spec.md). Offline tests (§1–§4, §6) run in CI without API keys. The pilot (§5) is the only live check before `dev` runs. A test that only proves a value was passed through or a mock was echoed does not belong here.

## 1. Data and feature definition (M0)

| ID | Test | Spec |
|---|---|---|
| T-D1 | Download verifies both SHA-256 values; a corrupted file fails with a clear error | §2.1 |
| T-D2 | Split rule reproduces exactly: 1,540 `dev` (540 OOS), 11,543 `cert`, 100 `pilot`, 3,080 `aa`; `dev` ∩ `cert` = ∅ and `dev` ∪ `cert` = all rows | §2.3 |
| T-D3 | `cert` slice sizes equal the §2.3 table | §2.3, §2.4 |
| T-D4 | Intent groups: 50 in-scope intents, each in exactly one group; 27 OOS; union = the 77 Banking77 intents | §2.2, §2.4 |
| T-D5 | Prompt build: catalog lists exactly the 50 in-scope intents, no OOS name appears anywhere in the prompt; stable prefix ≥ 1,100 `o200k_base` tokens; the user message is the raw customer text | §3.1 |
| T-D6 | Leakage: no `cert` message text occurs as a substring of any prompt file | §2.5 |

## 2. Parsing, outcomes, metrics, threshold, cost (M1–M2)

| ID | Test | Spec |
|---|---|---|
| T-P1 | Parser: valid output → `ok` with intent and confidence | §3.2 |
| T-P2 | Parser: malformed JSON, missing field, unknown intent, confidence < 0, > 1 or non-numeric, refusal, truncation → `invalid_output` with the right `error_code` | §3.2, §9.2 |
| T-P3 | Parser: intent differing only in case (`refund_not_showing_up`) → matched, `case_normalized = true` | §3.2 |
| T-O1 | Routing table: every combination of status × intent (catalog / `out_of_scope`) × confidence vs τ (below / equal / above) × truth (in-scope same / in-scope other / OOS) gives the outcome in §3.3 and §5 | §3.3, §5 |
| T-M1 | Metrics on a hand-built run of 20 items equal hand-computed W, A, V, top-1, OOS recall, API error rate, overall and per slice | §5 |
| T-C1 | τ calibration on constructed data: picks the smallest τ with W ≤ 2%; returns 0 when already met; returns 1.01 when unreachable; never reads `cert` items (raises if given any) | §6 |
| T-K1 | Cost: billed, steady and sparse cost per 1,000 messages from hand-built usage rows (uncached, cache read, cache write, output, reasoning) match hand computation for both providers | §11 |

## 3. Statistics and verdicts (M2)

| ID | Test | Spec |
|---|---|---|
| T-S1 | Paired bootstrap bound on a constructed sample agrees with the normal approximation within 0.1 pp at n ≥ 1,000 | §7.4 |
| T-S2 | Exact McNemar p-value equals a hand-computed binomial value for small discordant counts | §7.4 |
| T-S3 | Simulation, true difference = margin: the gate certifies in ≤ 5.5% of 2,000 simulated runs (G1 and a single G2 slice) | §7.1 |
| T-S4 | Simulation, true difference = 0: certification rate within ±3 pp of `analysis/power.py` for the same inputs | §7.3 |
| T-S5 | Stratified bootstrap keeps slice composition in every resample | §7.4 |
| T-S6 | Sample-size estimate equals the closed form; "not reachable" when d̂ ≥ δ | §7.4 |
| T-V1 | Verdict truth table: constructed gate results produce each of SHIP, SHIP WITH CONDITIONS, BLOCK, INCONCLUSIVE, including the D-X variant | §7.2 |
| T-V2 | G3 direction: a candidate that automates more never fails G3; one that automates 5 pp less with a tight bound fails | §7.1 |
| T-V3 | COST and LATENCY flags appear at the stated ratios and never change the verdict | §7.2 |

## 4. Providers, runner, guards (M1)

| ID | Test | Spec |
|---|---|---|
| T-R1 | Request snapshots per configuration: model ID, reasoning/thinking settings, temperature present only where allowed, max tokens, identical JSON schema, cache settings (OpenAI explicit breakpoint at the end of the developer message; Anthropic `cache_control` on the system block and no top-level `cache_control`; `prompt_cache_key` mapping for `inc`) | §4, §3.2 |
| T-R2 | Response normalization from recorded real responses (added after the pilot) for each configuration: text, usage classes incl. cache read/write and reasoning tokens, stop reason, request ID, returned model ID | §10 |
| T-R3 | Retry policy with a fake transport: retryable codes retried with backoff up to 6 attempts and `retry-after` honoured; non-retryable codes not retried; final failure → `api_error` | §9.2 |
| T-R4 | Runner with a fake provider: concurrency never exceeds 16; warm-up request completes before the fan-out starts | §4 |
| T-R5 | Resume: kill a run mid-way, restart with the same `run_id`: no item is requested twice and `items.jsonl` has exactly one row per item; a new `run_id` requests every item again | §9.3 |
| T-R6 | Budget guard: refuses a run whose spent + projected cost exceeds the cap; allows it just under | §9.5 |
| T-R7 | Freeze guard: a `cert` run refuses without tag `contract-v1`, with a modified contract file, or with a dirty tree; starts when all three hold | §9.5 |
| T-R8 | `decide` refuses a run with API error rate > 0.5% and accepts it after one recorded `--retry-errors` pass | §9.2 |
| T-R9 | Records validate against the §10 field list; ground truth is absent from `items.jsonl` | §10 |

## 5. Pilot acceptance (M3, live, ≈ $0.15)

| ID | Criterion | Spec |
|---|---|---|
| T-L1 | Each configuration: V ≥ 99.5% on the 100 pilot items; no API errors after retries | §5, §9.2 |
| T-L2 | Cache: after warm-up, cache-read tokens > 0 on ≥ 90% of calls for `inc`, `luna-none`, `luna-low`, `haiku55-off`, `haiku55-low` | §4 |
| T-L3 | Luna explicit vs implicit mode on the same items: cache reads, writes and billed cost recorded; mode for `cert` confirmed or changed with a reason | §14 |
| T-L4 | Measured cost per item within ±25% of the cost model; the budget projection for `dev` and `cert` updated | §9.5 |
| T-L5 | Every §14 open item has a recorded answer in `docs/pilot.md` | §14 |
| T-L6 | Real responses saved as fixtures for T-R2 (keys and request IDs stripped) | §10 |

## 6. Replay and CI (M2, M5)

| ID | Test | Spec |
|---|---|---|
| T-G1 | Golden replay: `swapcheck decide` on committed fixture runs (M2) and on the real runs (M5) reproduces byte-identical decision records | §10 |
| T-G2 | CI runs ruff, mypy, pytest and gitleaks on every PR; a committed fake key fails the gitleaks job | §12 |
