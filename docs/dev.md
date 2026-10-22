# Development runs and contract freeze (M4)

**Date:** 2026-10-22, 10:16–12:07 UTC. Fifteen `dev` runs on all 3,075 `dev` items, in the spec §9.1 order within each provider, each with the spend ceiling of the pre-`dev` gate (docs/pilot.md). Every run is complete and valid: 0 API errors, 1 invalid output in 46,125 calls (`haiku55-low`). The records are in `runs/*-dev-*`. Everything below is reproduced by `python analysis/dev.py freeze`, which wrote [`contracts/contract-v1.yaml`](../contracts/contract-v1.yaml) and its selection records.

## Spend

| Provider | Pilot | Dev | Spent | Projected after `cert` (§9.5) | Cap − $0.50 |
|---|---:|---:|---:|---:|---:|
| OpenAI | $0.10 | $2.37 | $2.47 | $8.84 | $14.50 |
| Anthropic | $0.03 | $0.80 | $0.83 | $1.43 | $9.50 |
| TypeSafe | $0.07 | $1.07 | $1.14 | $2.56 | $4.50 |

Per run: `inc` $0.72, `luna-dec` $0.71, `jev-noul` $0.62, `jev-c51` $0.45, `haiku55-medium` $0.34, `luna-medium` $0.28, `haiku55-low` $0.27, `haiku55-off` $0.18, `luna-low` $0.14, the three D-X iterations $0.13 each, `luna-none` $0.12.

## §3.4 competence check: passed

On the 2,000 in-scope `dev` items, `gpt-4o-mini` routes 1,683 correctly (84.15%) against 1,592 (79.60%) for the leave-one-out nearest-centroid baseline. No prompt revision was needed.

## §6 calibration, and amendment 1

`gpt-4o-mini` states its confidence in steps of 0.05 and gives 0.9 to 1,994 of the 2,618 items it routes; 470 of those are wrong (254 of them messages the catalog does not cover). Only 50 items get 0.95, all right. The smallest threshold with weighted W ≤ 2% is therefore 0.95, where the incumbent auto-routes 1.83%.

| Incumbent τ | Items at this confidence | Wrong | Weighted W | Weighted A |
|---|---:|---:|---:|---:|
| 0.95 | 50 | 0 | 0.00% | 1.83% |
| 0.90 | 1,994 | 470 | 14.34% | 71.83% |
| 0.80 | 357 | 289 | 23.95% | 85.32% |

Seen after the incumbent's run and before any candidate run, this made G3 unable to fail and matched every candidate to zero observed `dev` misroutes. Spec amendment 1 (commit `d22fb2d`, pushed 10:39:09 UTC; the first candidate run started 10:39:33 UTC) keeps the registered analysis unchanged and adds the descriptive §7.8 policy analysis at the 2% limit. Every decision record states the limitation.

Thresholds of the registered analysis, each candidate matched to the incumbent's weighted `dev` W of 0.00%:

| Configuration | τ | Weighted `dev` W | Weighted `dev` A |
|---|---:|---:|---:|
| `inc` | 0.95 | 0.00% | 1.83% |
| `luna-none` | 1.00 | 0.00% | 0.32% |
| `luna-low` | 1.00 | 0.00% | 0.15% |
| `luna-medium` | 1.00 | 0.00% | 0.06% |
| `haiku55-off` | 0.97 | 0.00% | 2.73% |
| `haiku55-low` | 0.96 | 0.00% | 2.96% |
| `haiku55-medium` | 0.96 | 0.00% | 2.93% |
| `jev-c51` | 1.01 | 0.00% | 0.00% |
| `jev-noul` | 1.01 | 0.00% | 0.00% |
| `luna-dec` | 1.01 | 0.00% | 0.00% |
| `luna-none-x` (iteration 3) | 1.00 | 0.00% | 13.64% |

Both Jev designs and `luna-dec` auto-route nothing at zero misroutes: their confidence is rounded to two decimals and saturates at 1.00 (`jev-c51` 1,173 items, 76 wrong; `luna-dec` 414 items, 28 wrong).

## §7.8 policy thresholds (own weighted `dev` W ≤ 2%)

| Configuration in the `cert` plan | τ_2% | Weighted `dev` W | Weighted `dev` A |
|---|---:|---:|---:|
| `inc` | 0.95 | 0.00% | 1.83% |
| `luna-none` | 0.99 | 1.14% | 34.55% |
| `luna-none-x` | 0.99 | 1.44% | 42.46% |
| `haiku55-off` | 0.90 | 1.48% | 33.47% |
| `luna-dec` | 0.99 | 1.67% | 25.07% |
| `jev-c51` | 1.01 | 0.00% | 0.00% |

`jev-c51` has no threshold at 2%: at confidence 1.00 alone its weighted W is 2.29%.

## §8 selections

- **§8.1 reasoning effort: none qualifies, so D-A2 and D-B2 are NOT RUN (`no dev gain`).** Luna: `low` and `medium` automate less than `none` at the matched threshold (−0.17 pp and −0.26 pp; 0 vs 5 and 0 vs 8 discordant items). Haiku 5.5: `low` +0.23 pp and `medium` +0.21 pp over `off`, but the bootstrap 10th percentiles are −0.06 pp and −0.11 pp and the sign tests give p = 0.18 and 0.24. All gain-test numbers are in the contract's selection records.
- **§8.2 Jev design: `jev-c51`.** Both designs have A = 0 at the matched threshold; the tie goes to `jev-c51`.
- **§8.3 D-X: iteration 3.** Each iteration was written from the previous run's error counts by true and routed intent and by confidence (`python analysis/dev.py dx-errors RUN_ID`); no `dev` message text was read. The files are in `prompts/dx/`; the selected one is `prompts/luna-none-x.md`.

| Iteration | Change | Changed lines | τ | Weighted `dev` A | Wrong routes at any τ |
|---|---|---:|---:|---:|---:|
| 0 | the incumbent prompt (`luna-none`) | 0 | 1.00 | 0.32% | 926 |
| 1 | scope boundaries in 17 descriptions and the instructions; 0.99 only for exact matches | 19 | 1.00 | 0.06% | 380 |
| 2 | a graded top of the confidence scale; 3 descriptions sharpened | 21 | 1.01 | 0.00% | 403 |
| 3 | iteration 2, without 1 for reports of something that failed or did not arrive | 21 | 1.00 | 13.64% | 377 |

## §9.5 budget plan

The `cert` plan is `inc`, `luna-none`, `aa`, `luna-dec`, `luna-none-x`, `haiku55-off`, `jev-c51`; nothing is dropped and no provider is blocked. Projected spend after `cert` is in the table above.

## §7.3 margins

The worst own-threshold `dev` discordance of the planned LLM candidates is at or below the 1% floor in every slice, so every slice uses 1%. The first grid pair, δ_W = 0.50 pp and δ_S = 1.5 pp, already has joint power 91.25% (4,000 simulations), and every planned decision has the same power.

## Process note

The first launch of iteration 2 ran before its edits had been saved, so it would have repeated iteration 1's prompt. It was stopped during start-up before any request (OpenAI spend was $1.9246 before and after) and left no run directory.
