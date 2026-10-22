# D-B1: inc → haiku55-off

Analysis code: `synthetic-golden-v1`; decision_index=3.

**Verdict: BLOCK**

Conditions: candidate τ = 0.70; incumbent τ = 0.70.
Paired n=210; dropped API-error/absent items=0.
Frozen dev W=0.00 pp; A=80.00 pp; power at frozen margins=65.00 pp.

## Gates

Family-adjusted column: one-sided 1 - 0.05/7 over all seven decisions (including NOT RUN).

| Gate | Estimate | Tango [L,U] | Wald [L,U] | Margin | 95% status | Family-adjusted |
|---|---:|---|---|---:|---|---|
| G1 W overall | 0.00 pp | [-1.27 pp, 1.27 pp] | [0.00 pp, 0.00 pp] | 1.00 pp | UNRESOLVED | UNRESOLVED |
| G2 W slices | — | see slice table | — | 3.00 pp | UNRESOLVED | UNRESOLVED |
| G3 A overall | -12.38 pp | [-17.50 pp, -7.60 pp] | [-17.26 pp, -7.50 pp] | -3.00 pp | FAIL | FAIL |
| G4 V | 100.00 pp | — | — | 99.50 pp | PASS | PASS |

### Slices

| Slice | Estimate | Tango [L,U] | Wald [L,U] | Margin | 95% status | Family-adjusted |
|---|---:|---|---|---:|---|---|
| cards | 0.00 pp | [-8.27 pp, 8.27 pp]; harm L -16.67 pp | [0.00 pp, 0.00 pp] | 3.00 pp | UNRESOLVED | UNRESOLVED |
| card_payments | 0.00 pp | [-8.27 pp, 8.27 pp]; harm L -16.67 pp | [0.00 pp, 0.00 pp] | 3.00 pp | UNRESOLVED | UNRESOLVED |
| cash | 0.00 pp | [-8.27 pp, 8.27 pp]; harm L -16.67 pp | [0.00 pp, 0.00 pp] | 3.00 pp | UNRESOLVED | UNRESOLVED |
| transfers | 0.00 pp | [-8.27 pp, 8.27 pp]; harm L -16.67 pp | [0.00 pp, 0.00 pp] | 3.00 pp | UNRESOLVED | UNRESOLVED |
| top_ups | 0.00 pp | [-8.27 pp, 8.27 pp]; harm L -16.67 pp | [0.00 pp, 0.00 pp] | 3.00 pp | UNRESOLVED | UNRESOLVED |
| account_other | 0.00 pp | [-8.27 pp, 8.27 pp]; harm L -16.67 pp | [0.00 pp, 0.00 pp] | 3.00 pp | UNRESOLVED | UNRESOLVED |
| out_of_scope | 0.00 pp | [-8.27 pp, 8.27 pp]; harm L -16.67 pp | [0.00 pp, 0.00 pp] | 3.00 pp | UNRESOLVED | UNRESOLVED |

### Sample sizes for UNRESOLVED gates

- G1: total paired n needed = no discordant pairs observed.
- G2/cards: total paired n needed = no discordant pairs observed.
- G2/card_payments: total paired n needed = no discordant pairs observed.
- G2/cash: total paired n needed = no discordant pairs observed.
- G2/transfers: total paired n needed = no discordant pairs observed.
- G2/top_ups: total paired n needed = no discordant pairs observed.
- G2/account_other: total paired n needed = no discordant pairs observed.
- G2/out_of_scope: total paired n needed = no discordant pairs observed.

## Cluster-bootstrap sensitivity

10,000 intent-cluster resamples; descriptive only.
- G1: UNRESOLVED → PASS.
- G2: UNRESOLVED → PASS.

## Noise floor

A/A G1 UNRESOLVED; G2 UNRESOLVED; outcome flip rate 0.00 pp; paired n=210, dropped=0.
WARNING: A/A noise floor UNRESOLVED.
Dev wrong-auto discordance used for power/margins:

| Slice | Frozen dev discordance |
|---|---:|
| cards | 1.00 pp |
| card_payments | 1.00 pp |
| cash | 1.00 pp |
| transfers | 1.00 pp |
| top_ups | 1.00 pp |
| account_other | 1.00 pp |
| out_of_scope | 1.00 pp |

## Naive swap at incumbent τ

Two-sided 95% Wilson score intervals (unweighted, descriptive; no verdict).

| Scope | n | W [95% CI] | A [95% CI] |
|---|---:|---|---|
| overall | 210 | 0.00 pp [0.00 pp, 1.80 pp] | 68.57 pp [62.01 pp, 74.47 pp] |
| cards | 30 | 0.00 pp [0.00 pp, 11.35 pp] | 80.00 pp [62.69 pp, 90.49 pp] |
| card_payments | 30 | 0.00 pp [0.00 pp, 11.35 pp] | 80.00 pp [62.69 pp, 90.49 pp] |
| cash | 30 | 0.00 pp [0.00 pp, 11.35 pp] | 80.00 pp [62.69 pp, 90.49 pp] |
| transfers | 30 | 0.00 pp [0.00 pp, 11.35 pp] | 80.00 pp [62.69 pp, 90.49 pp] |
| top_ups | 30 | 0.00 pp [0.00 pp, 11.35 pp] | 80.00 pp [62.69 pp, 90.49 pp] |
| account_other | 30 | 0.00 pp [0.00 pp, 11.35 pp] | 80.00 pp [62.69 pp, 90.49 pp] |
| out_of_scope | 30 | 0.00 pp [0.00 pp, 11.35 pp] | 0.00 pp [0.00 pp, 11.35 pp] |

## Policy analysis at the 2% limit (§7.8, amendment 1)

Descriptive; it never changes the verdict. Each arm runs at its own τ fitted on dev to weighted W ≤ 2%: incumbent τ_2% = 0.70 (dev W 0.00 pp, A 80.00 pp), candidate τ_2% = 0.50 (dev W 2.00 pp, A 85.00 pp). Unweighted cert estimates on the paired items, two-sided 95% Wilson score intervals.

| Arm | Scope | n | W [95% CI] | A [95% CI] |
|---|---|---:|---|---|
| incumbent | overall | 210 | 0.00 pp [0.00 pp, 1.80 pp] | 80.95 pp [75.10 pp, 85.69 pp] |
| incumbent | cards | 30 | 0.00 pp [0.00 pp, 11.35 pp] | 93.33 pp [78.68 pp, 98.15 pp] |
| incumbent | card_payments | 30 | 0.00 pp [0.00 pp, 11.35 pp] | 93.33 pp [78.68 pp, 98.15 pp] |
| incumbent | cash | 30 | 0.00 pp [0.00 pp, 11.35 pp] | 96.67 pp [83.33 pp, 99.41 pp] |
| incumbent | transfers | 30 | 0.00 pp [0.00 pp, 11.35 pp] | 93.33 pp [78.68 pp, 98.15 pp] |
| incumbent | top_ups | 30 | 0.00 pp [0.00 pp, 11.35 pp] | 96.67 pp [83.33 pp, 99.41 pp] |
| incumbent | account_other | 30 | 0.00 pp [0.00 pp, 11.35 pp] | 93.33 pp [78.68 pp, 98.15 pp] |
| incumbent | out_of_scope | 30 | 0.00 pp [0.00 pp, 11.35 pp] | 0.00 pp [0.00 pp, 11.35 pp] |
| candidate | overall | 210 | 0.00 pp [0.00 pp, 1.80 pp] | 85.71 pp [80.34 pp, 89.81 pp] |
| candidate | cards | 30 | 0.00 pp [0.00 pp, 11.35 pp] | 100.00 pp [88.65 pp, 100.00 pp] |
| candidate | card_payments | 30 | 0.00 pp [0.00 pp, 11.35 pp] | 100.00 pp [88.65 pp, 100.00 pp] |
| candidate | cash | 30 | 0.00 pp [0.00 pp, 11.35 pp] | 100.00 pp [88.65 pp, 100.00 pp] |
| candidate | transfers | 30 | 0.00 pp [0.00 pp, 11.35 pp] | 100.00 pp [88.65 pp, 100.00 pp] |
| candidate | top_ups | 30 | 0.00 pp [0.00 pp, 11.35 pp] | 100.00 pp [88.65 pp, 100.00 pp] |
| candidate | account_other | 30 | 0.00 pp [0.00 pp, 11.35 pp] | 100.00 pp [88.65 pp, 100.00 pp] |
| candidate | out_of_scope | 30 | 0.00 pp [0.00 pp, 11.35 pp] | 0.00 pp [0.00 pp, 11.35 pp] |

- incumbent: one-sided 95% upper Wilson bound of W = 1.27 pp: below 2%.
- candidate: one-sided 95% upper Wilson bound of W = 1.27 pp: below 2%.
- A difference (candidate minus incumbent) = 4.76 pp; one-sided 95% Tango bounds [2.87 pp, 7.81 pp].

## Newly wrong auto-routes

Messages are quoted from the split under test; Banking77 texts are CC BY 4.0 (Casanueva et al., 2020).
None.

## Cost and speed (not gated)

| Arm | Billed $/1,000 | Steady $/1,000 | Sparse $/1,000 | Latency p50/p95 ms | Reasoning tokens/message mean/p95 |
|---|---:|---:|---:|---|---|
| inc | 0.06 | 0.05 | 0.10 | 120.00/160.00 | not reported/not reported |
| haiku55-off | 0.03 | 0.01 | 0.07 | 160.00/200.00 | not reported/not reported |

Flags: none. Flags never change the verdict.
Latency is indicative, not a live-chat limit; all calls and retries are included in billed cost.
- incumbent, without cache reads: latency p50/p95 ms 120.00/160.00.
- incumbent, with cache reads: latency p50/p95 ms 120.00/160.00.
- candidate, without cache reads: latency p50/p95 ms 160.00/200.00.
- candidate, with cache reads: latency p50/p95 ms 160.00/200.00.

## Not tested

Reasoning efforts above medium; Claude Haiku 4.5; gpt-4.1-mini; Jev 1.14 (jev-preview) and other decision models (Laya, Kev); live-chat latency limits; multi-turn conversations; languages other than English; streaming; real production traffic.
