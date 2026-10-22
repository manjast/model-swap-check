# Certification runs and decisions (M5)

**Date:** 2026-10-22, 12:39–14:31 UTC, under tag `contract-v1` (commit `8e10a4c`). Seven runs, one per configuration and split as planned in the contract, in the spec §9.1 order within each provider (OpenAI `inc`, `luna-none`, `aa`, `luna-dec`, `luna-none-x`; Anthropic `haiku55-off`; TypeSafe `jev-c51`), one process per provider. Every run passed the freeze guard and is listed in [`runs/manifest.yaml`](../runs/manifest.yaml). The records in [`decisions/`](../decisions/) are written by `swapcheck decide`, and CI replays them from the committed runs and fails on any byte difference.

## Runs

| Run | Items | Invalid | API errors | Billed |
|---|---:|---:|---:|---:|
| `inc-cert-20261022T123919Z` | 9,758 | 2 | 0 | $2.32 |
| `luna-none-cert-20261022T131547Z` | 9,758 | 0 | 12 → 0 after the retry pass | $0.40 |
| `inc-aa-20261022T134215Z` | 3,080 | 0 | 0 | $0.73 |
| `luna-dec-cert-20261022T134855Z` | 9,758 | 0 | 0 | $2.26 |
| `luna-none-x-cert-20261022T140544Z` | 9,758 | 0 | 0 | $0.42 |
| `haiku55-off-cert-20261022T123919Z` | 9,758 | 0 | 0 | $0.59 |
| `jev-c51-cert-20261022T123919Z` | 9,758 | 0 | 0 | $1.42 |

`luna-none` was valid before its single §9.2 retry pass (0.12% API errors); the pass rewrote all 12 rows.

## Spend

| Provider | Before `cert` | `cert` and `aa` | Spent | Projected in the contract | Cap |
|---|---:|---:|---:|---:|---:|
| OpenAI | $2.47 | $6.13 | $8.60 | $8.84 | $15 |
| Anthropic | $0.83 | $0.59 | $1.42 | $1.43 | $10 |
| TypeSafe | $1.14 | $1.42 | $2.56 | $2.56 | $5 |

## Verdicts

D-A2 and D-B2 are NOT RUN (`no dev gain`, §8.1). The other five decisions are **SHIP** at the 95% level and after the family adjustment. As amendment 1 (§7.8) anticipated, the registered gates say little here: the incumbent automates 2.05% of `cert` at τ_inc = 0.95, so G3 (A not worse by more than 3 pp) cannot fail, and each candidate runs at the threshold that matched zero `dev` misroutes. The A/A run passes G1 and G2 with a 0.29 pp outcome flip rate.

| Decision | Candidate τ | G1 W difference | G3 A difference | Cluster bootstrap | Newly wrong auto-routes |
|---|---:|---:|---:|---|---:|
| D-A1 `luna-none` | 1.00 | 0.00 pp | −1.98 pp | G3 PASS → UNRESOLVED | 0 |
| D-B1 `haiku55-off` | 0.97 | +0.01 pp | +0.81 pp | no change | 1 |
| D-J `jev-c51` | 1.01 | 0.00 pp | −2.05 pp | G3 PASS → UNRESOLVED | 0 |
| D-O `luna-dec` | 1.01 | 0.00 pp | −2.05 pp | G3 PASS → UNRESOLVED | 0 |
| D-X `luna-none-x` | 1.00 | +0.07 pp | +11.10 pp | no change | 7 |

## §7.8 policy analysis (descriptive)

Each arm at its own τ_2% from `dev`; unweighted `cert` estimates with two-sided 95% Wilson intervals; the A difference has one-sided 95% Tango bounds.

| Arm | τ_2% | `cert` W | One-sided 95% upper W | `cert` A | A minus incumbent |
|---|---:|---:|---:|---:|---:|
| `inc` | 0.95 | 0.00% | 0.03% | 2.05% | — |
| `luna-none` | 0.99 | 1.30% | 1.50% | 34.75% | +32.70 pp [31.92, 33.49] |
| `haiku55-off` | 0.90 | 1.26% | 1.46% | 34.80% | +32.75 pp [31.97, 33.54] |
| `luna-dec` | 0.99 | 1.49% | 1.70% | 25.32% | +23.27 pp [22.56, 24.00] |
| `luna-none-x` | 0.99 | 1.54% | 1.76% | 42.89% | +40.84 pp [40.02, 41.66] |
| `jev-c51` | 1.01 | 0.00% | 0.03% | 0.00% | −2.05 pp [−2.30, −1.83] |

Every LLM candidate stays under the 2% limit on `cert` while automating 25–43% of traffic, against 2% for the incumbent. `jev-c51` automates nothing: its confidence saturates at 1.00, where its `dev` W was already 2.29%.

## Amendment 2: Jev at its top confidence (§7.9, descriptive)

Jev's 0% above comes from how it reports confidence, not from how it routes. On `dev` its in-scope top-1 accuracy is 85.6% (incumbent 84.2%). TypeSafe computes the confidence as (p_max − 1/n)/(1 − 1/n) from probabilities rounded to 0.01, so 38% of its `dev` answers share the top value, 1.00. At 1.00 its weighted `dev` W is 2.29%, and the next threshold up automates nothing.

- **Timeline:** the amendment text was committed and pushed at 15:04 UTC (`58f0a20`), before any `cert` estimate of the two rules. `contract-v2` was tagged at `3ee1db7` after an independent review. That review re-derived τ_J2 = 0.94 from the `dev` runs. The tag is on the branch commit, which the tag keeps reachable after the squash merge.
- **Run:** one `jev-noul` `cert` run, `jev-noul-cert-20261022T152203Z`, made 15:22–15:37 UTC: 9,758 ok, 0 invalid, 0 API errors, billed $1.96. TypeSafe spend is now $4.52 against the raised $6 cap.
- **Record:** `decisions/A2-jev.md`, written by `swapcheck jev-policy` and replayed by CI.

| Rule | Weighted `dev` W / A | `cert` W | One-sided 95% upper W | `cert` A | A minus incumbent |
|---|---:|---:|---:|---:|---:|
| J1 `jev-c51` at τ = 1.00 | 2.29% / 42.38% | 2.22% | 2.48% | 42.96% | +40.91 pp [40.09, 41.73] |
| J2 `jev-noul`, match ≥ 0.94 at confidence 1.00 | 1.88% / 40.59% | 2.03% | 2.28% | 40.88% | +38.83 pp [38.02, 39.65] |

At the operating points its API makes available, Jev automates about as much as the best LLM candidate (`luna-none-x`: 42.89% at 1.54% W). Neither rule stays clearly below the 2% limit, though. J2 was fitted on `dev` to 1.88% and lands at 2.03% on `cert`, and its upper bound of 2.28% is above 2%. The LLM candidates' upper bounds are 1.46–1.76%. Most of Jev's excess sits in `transfers` and `out_of_scope`, as it does for every candidate. D-J's registered verdict is unchanged.

## Amendment 3: risk-limit sensitivity (§7.10, descriptive)

The 2% limit is an operator's setting (20 misrouted messages per 1,000), not a property of the models, so amendment 3 repeats the comparison at 1, 2, 5, 10 and 15%. Each configuration gets its own threshold from `dev` by the §6 rule at each limit; `jev-noul` uses the J2 signal. No new run.

- **Timeline:** the amendment text was committed and pushed at 17:19 UTC (`3f7b03b`), before any `cert` estimate at a limit other than 2%. The thresholds were frozen in `contracts/contract-v3.yaml`, and `contract-v3` was tagged at `1a4f374` after an independent review that re-derived all 35 thresholds and the two fixed incumbent points from the `dev` runs. The report was computed after the tag.
- **Record:** `decisions/A3-limits.md`, written by `swapcheck risk-limits` and replayed by CI. At 2% it reproduces the §7.8 and §7.9 numbers.

`cert` W / A at each configuration's own threshold (9,758 paired items, none dropped):

| Configuration | ≤ 1% | ≤ 2% | ≤ 5% | ≤ 10% | ≤ 15% |
|---|---|---|---|---|---|
| `inc` | 0.00 / 2.05 | 0.00 / 2.05 | 0.00 / 2.05 | 0.00 / 2.05 | 14.98\* / 72.37 |
| `luna-none` | 0.00 / 0.07 | 1.30 / 34.75 | 4.12 / 50.20 | 4.12 / 50.20 | 12.91 / 71.26 |
| `luna-none-x` | 0.07 / 13.15 | 1.54 / **42.89** | 1.54 / 42.89 | 7.65 / 63.86 | 12.45 / **73.16** |
| `haiku55-off` | 0.42 / **19.98** | 1.26 / 34.80 | 2.80 / 46.88 | 7.69 / 63.01 | 7.69 / 63.01 |
| `luna-dec` | 0.73 / 15.87 | 1.49 / 25.32 | 4.83\* / 47.27 | 9.84\* / 62.71 | 14.31 / 70.40 |
| `jev-c51` | 0.00 / 0.00 | 0.00 / 0.00 | 4.48 / **53.63** | 9.46 / **66.19** | 14.83\* / 74.90 |
| `jev-noul` (J2) | 0.46 / 16.11 | 2.03\* / 40.88 | 3.81 / 46.97 | 3.81 / 46.97 | 3.81 / 46.97 |

In %. \* = the one-sided 95% upper bound of W is not below the limit. **Bold** = the highest A among the configurations whose upper bound is below the limit.

- **The incumbent has no setting between 2% and 72%.** `gpt-4o-mini` states its confidence in steps of 0.05. Below a 14% limit its threshold stays at 0.95, where it automates 2.05%; the next step, 0.90, automates 72.37% with 14.98% of messages misrouted. With no confidence gate (τ = 0) it misroutes 26.82% and automates 87.47%. So at every limit from 2% to 10%, each LLM candidate automates 25–64% of traffic against the incumbent's 2%. At 1%, `luna-none` automates 0.07%, less than the incumbent. At 15%, the LLM candidates' A differences against the incumbent range from −9.36 to +0.79 pp, and across all candidates, Jev included, from −25.40 to +2.53 pp.
- **The leader depends on the limit.** Among the configurations whose upper bound of W is below the limit, Haiku 5.5 leads at 1%, Luna with the adapted prompt at 2%, Jev (`jev-c51`) at 5% and 10%, and the adapted Luna again at 15%. At 1%, `luna-none` and `jev-c51` automate almost nothing: their confidence piles up at the top of the scale too.
- **The `dev` thresholds mostly held on `cert`.** Every point estimate of W stays at or below its limit except J2 at 2% (2.03%). The upper bound reaches the limit for J2 at 2%, `luna-dec` at 5% and 10%, and `jev-c51` and the incumbent at 15%.
- **Some signals run out.** Across the tested limits, J2 automates at most 46.97%: at 5%, 10% and 15% its threshold stays at 0.13. The only lower threshold, 0, would also admit answers below Choice confidence 1.00 that pass the catalog and Noul gates. `haiku55-off` keeps the same threshold, 0.62, at 10% and 15%.

## Cost and speed (not gated, indicative)

`python analysis/cert_speed.py` prints these values from the `cert` runs in `runs/manifest.yaml`. Costs follow the §11 cost model at the prices in `config/prices.yaml`. Billed is every attempt, retry and warm-up divided by the 9,758 items. Steady is one call per message with the shared prefix read from cache, and sparse is the same call with nothing cached. Wall clock is the final attempt of each item, non-streamed, at concurrency 16 from one client machine, as in the decision records. Server time is OpenAI's `openai-processing-ms` header; Anthropic and TypeSafe send no equivalent.

| Configuration | Model | Billed $/1,000 | Steady $/1,000 | Sparse $/1,000 | Input/output tokens per message | Wall clock p50/p95 s | Server p50/p95 s |
|---|---|---:|---:|---:|---|---|---|
| `inc` | `gpt-4o-mini-2024-07-18` | 0.238 | 0.218 | 0.410 | 2,682/15.5 | 2.80/7.05 | 0.76/1.41 |
| `luna-none` | `gpt-6-luna` | 0.041 | 0.039 | 0.277 | 2,681/21.9 | 1.54/6.68 | 0.84/5.69 |
| `luna-none-x` | `gpt-6-luna` | 0.043 | 0.042 | 0.312 | 3,019/20.9 | 1.66/3.50 | 0.89/1.81 |
| `luna-dec` | `gpt-6-luna` (Decisions API) | 0.232 | 0.232 | 0.232 | 2,319/0.0 | 1.04/3.34 | 0.18/0.60 |
| `haiku55-off` | `claude-haiku-5-5` | 0.060 | 0.059 | 0.452 | 4,405/26.0 | 2.38/7.08 | – |
| `jev-c51` | `jev-1.13.0` | 0.146 | 0.146 | 0.146 | 3,468/561.3 | 2.38/6.01 | – |
| `jev-noul` | `jev-1.13.0` | 0.201 | 0.201 | 0.201 | 4,784/569.5 | 0.76/2.85 | – |

- **Cached prefixes make Luna and Haiku the cheapest.** The LLMs read a prompt prefix of a few thousand tokens from cache: Luna and Haiku at a tenth of their input price, `gpt-4o-mini` at half. Jev and the Decisions API bill only input and give no cache discount. So `jev-c51` costs about 3.7× `luna-none` per message and about two thirds of the incumbent; `luna-dec` costs about 6× `luna-none` on the same model. Jev's output tokens are free and are shown only for completeness.
- **Wall clock and server time rank differently.** The incumbent's server time p50 is 0.76 s against 2.80 s wall clock. `luna-dec`'s server time is 4.7× shorter than `luna-none`'s at p50 (0.18 against 0.84 s), but its wall clock only 1.5× (1.04 against 1.54 s). Haiku and Jev report no server time.
- **The runs were not all contemporaneous.** `inc`, `haiku55-off` and `jev-c51` started together at 12:39 UTC, one process per provider; the other OpenAI runs followed in the OpenAI process, partly overlapping the Haiku run, and `jev-noul` ran at 15:22 UTC. The two Jev designs differ by 3× in wall clock p50 on the same model, so time of day and load on this client are confounded with the configuration. These numbers do not rank providers by speed; the latency study below does.
- **Cache hit rate decides the cost order.** With nothing cached, `jev-c51` ($0.146) costs about half of `luna-none` ($0.277) and a third of `haiku55-off` ($0.452). It breaks even with `luna-none` at a cache hit rate of about 55% (65% when misses pay the 1.25× cache-write price) and with `haiku55-off` at about 78% (83%). The `cert` runs read the cache on 99.7–100% of calls.
- **No flag.** No decision record raises `COST` or `LATENCY` (§7.2).

## Latency study (§9.6, descriptive)

- **Timeline:** protocol committed and pushed at 18:19:34 UTC (`540d4e1`) and code at 18:33:55 UTC (`c133c08`, tag `latency-v1`), both before any study call. Run `latency-20261022T194349Z`, 19:43–20:01 UTC: 200 rounds, six configurations interleaved one request at a time, from Belgrade over home Wi-Fi. 1,200 calls, 0 errors, 0 retries; billed $0.19.
- **Record:** `decisions/latency.md`, written by `swapcheck latency-report` and replayed by CI.

| Configuration | Total p50/p95 s | Server p50/p95 s |
|---|---|---|
| `inc` | 1.02/1.62 | 0.72/1.34 |
| `luna-none` | 1.26/1.69 | 0.96/1.31 |
| `luna-dec` | 0.28/0.60 | 0.08/0.39 |
| `haiku55-off` | 1.25/2.08 | – |
| `jev-c51` | 0.28/0.35 | – |
| `jev-noul` | 0.28/0.40 | – |

- **The decision interfaces are about 4× faster end to end.** Jev and the Decisions API answer in 0.28 s at p50, the three LLM configurations in 1.02–1.26 s. Jev has the tightest tail (p95 0.35 s).
- **The Decisions API takes 12× less server time than Luna's Responses API** (0.08 against 0.96 s at p50), in line with OpenAI's "up to 10x faster".
- **The network adds little from here.** A TCP connect to each API host takes 60–78 ms at p50; OpenAI calls spend 0.14–0.30 s outside the server at p50.
- **Against TypeSafe's claims:** typesafe.ai headlines "193.6x Faster" on System One workflows and shows 0.114 s per task for Jev against 8.566 s for LLMs. From Belgrade, Jev takes 0.28 s including about 0.08 s of round trip, and the small LLMs without reasoning take 1.0–1.3 s: a 4× advantage on this router.
- **The `cert` timings above measured this client under load.** At concurrency 16, Jev's p50 was 0.76–2.38 s; one request at a time, it is 0.28 s.

## Process notes

- The NOT RUN decisions were written to the manifest with `swapcheck.manifest.add_not_run`, from the contract's budget plan, because no CLI command writes them; `decide` checks that they equal the frozen plan.
- No `cert` message was read before the records were generated. The records quote the newly wrong auto-routes with attribution (spec §2.1).
