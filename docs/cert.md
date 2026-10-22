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

## Process notes

- The NOT RUN decisions were written to the manifest with `swapcheck.manifest.add_not_run`, from the contract's budget plan, because no CLI command writes them; `decide` checks that they equal the frozen plan.
- No `cert` message was read before the records were generated. The records quote the newly wrong auto-routes with attribution (spec §2.1).
