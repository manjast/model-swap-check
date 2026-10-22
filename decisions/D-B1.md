# D-B1: inc → haiku55-off

Analysis code: `src tree bb82167c21baa59dc1095573671bdde94edbe40f, analysis tree 884e88e42c8f7b0fbfebdb3f44a5511f2dd9fb06`; decision_index=3.

**Verdict: SHIP**

Conditions: candidate τ = 0.97; incumbent τ = 0.95.
Limitation (§7.8): the incumbent's weighted dev A at τ_inc is 1.83 pp, below the 3.00 pp G3 margin, so G3 cannot fail while its cert A stays below the margin; candidates were matched to the incumbent's dev W of 0.00 pp. See the policy analysis.
Paired n=9758; dropped API-error/absent items=0.
Frozen dev W=0.00 pp; A=2.73 pp; power at frozen margins=91.25 pp.

## Gates

Family-adjusted column: one-sided 1 - 0.05/7 over all seven decisions (including NOT RUN).

| Gate | Estimate | Tango [L,U] | Wald [L,U] | Margin | 95% status | Family-adjusted |
|---|---:|---|---|---:|---|---|
| G1 W overall | 0.01 pp | [-0.02 pp, 0.05 pp] | [-0.01 pp, 0.03 pp] | 0.50 pp | PASS | PASS |
| G2 W slices | — | see slice table | — | 1.50 pp | PASS | PASS |
| G3 A overall | 0.81 pp | [0.54 pp, 1.09 pp] | [0.54 pp, 1.08 pp] | -3.00 pp | PASS | PASS |
| G4 V | 100.00 pp | — | — | 99.50 pp | PASS | PASS |

### Slices

| Slice | Estimate | Tango [L,U] | Wald [L,U] | Margin | 95% status | Family-adjusted |
|---|---:|---|---|---:|---|---|
| cards | 0.00 pp | [-0.19 pp, 0.19 pp]; harm L -0.42 pp | [0.00 pp, 0.00 pp] | 1.50 pp | PASS | PASS |
| card_payments | 0.00 pp | [-0.18 pp, 0.18 pp]; harm L -0.41 pp | [0.00 pp, 0.00 pp] | 1.50 pp | PASS | PASS |
| cash | 0.00 pp | [-0.28 pp, 0.28 pp]; harm L -0.62 pp | [0.00 pp, 0.00 pp] | 1.50 pp | PASS | PASS |
| transfers | 0.00 pp | [-0.20 pp, 0.20 pp]; harm L -0.45 pp | [0.00 pp, 0.00 pp] | 1.50 pp | PASS | PASS |
| top_ups | 0.00 pp | [-0.32 pp, 0.32 pp]; harm L -0.71 pp | [0.00 pp, 0.00 pp] | 1.50 pp | PASS | PASS |
| account_other | 0.00 pp | [-0.24 pp, 0.24 pp]; harm L -0.52 pp | [0.00 pp, 0.00 pp] | 1.50 pp | PASS | PASS |
| out_of_scope | 0.04 pp | [-0.07 pp, 0.17 pp]; harm L -0.19 pp | [-0.02 pp, 0.10 pp] | 1.50 pp | PASS | PASS |

### Sample sizes for UNRESOLVED gates

None.

## Cluster-bootstrap sensitivity

10,000 intent-cluster resamples; descriptive only.
No gate status changes.

## Noise floor

A/A G1 PASS; G2 PASS; outcome flip rate 0.29 pp; paired n=3080, dropped=0.
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
| overall | 9758 | 0.15 pp [0.09 pp, 0.25 pp] | 11.14 pp [10.53 pp, 11.78 pp] |
| cards | 1407 | 0.07 pp [0.01 pp, 0.40 pp] | 27.58 pp [25.30 pp, 29.97 pp] |
| card_payments | 1473 | 0.00 pp [0.00 pp, 0.26 pp] | 10.12 pp [8.68 pp, 11.76 pp] |
| cash | 966 | 0.00 pp [0.00 pp, 0.40 pp] | 14.60 pp [12.51 pp, 16.96 pp] |
| transfers | 1328 | 0.00 pp [0.00 pp, 0.29 pp] | 4.22 pp [3.26 pp, 5.44 pp] |
| top_ups | 844 | 0.00 pp [0.00 pp, 0.45 pp] | 17.89 pp [15.45 pp, 20.62 pp] |
| account_other | 1143 | 0.00 pp [0.00 pp, 0.33 pp] | 16.45 pp [14.41 pp, 18.71 pp] |
| out_of_scope | 2597 | 0.54 pp [0.32 pp, 0.90 pp] | 0.54 pp [0.32 pp, 0.90 pp] |

## Policy analysis at the 2% limit (§7.8, amendment 1)

Descriptive; it never changes the verdict. Each arm runs at its own τ fitted on dev to weighted W ≤ 2%: incumbent τ_2% = 0.95 (dev W 0.00 pp, A 1.83 pp), candidate τ_2% = 0.90 (dev W 1.48 pp, A 33.47 pp). Unweighted cert estimates on the paired items, two-sided 95% Wilson score intervals.

| Arm | Scope | n | W [95% CI] | A [95% CI] |
|---|---|---:|---|---|
| incumbent | overall | 9758 | 0.00 pp [0.00 pp, 0.04 pp] | 2.05 pp [1.79 pp, 2.35 pp] |
| incumbent | cards | 1407 | 0.00 pp [0.00 pp, 0.27 pp] | 7.04 pp [5.81 pp, 8.49 pp] |
| incumbent | card_payments | 1473 | 0.00 pp [0.00 pp, 0.26 pp] | 1.43 pp [0.93 pp, 2.17 pp] |
| incumbent | cash | 966 | 0.00 pp [0.00 pp, 0.40 pp] | 0.31 pp [0.11 pp, 0.91 pp] |
| incumbent | transfers | 1328 | 0.00 pp [0.00 pp, 0.29 pp] | 3.46 pp [2.61 pp, 4.59 pp] |
| incumbent | top_ups | 844 | 0.00 pp [0.00 pp, 0.45 pp] | 0.47 pp [0.18 pp, 1.21 pp] |
| incumbent | account_other | 1143 | 0.00 pp [0.00 pp, 0.33 pp] | 2.36 pp [1.63 pp, 3.42 pp] |
| incumbent | out_of_scope | 2597 | 0.00 pp [0.00 pp, 0.15 pp] | 0.00 pp [0.00 pp, 0.15 pp] |
| candidate | overall | 9758 | 1.26 pp [1.06 pp, 1.50 pp] | 34.80 pp [33.86 pp, 35.75 pp] |
| candidate | cards | 1407 | 0.28 pp [0.11 pp, 0.73 pp] | 61.41 pp [58.84 pp, 63.92 pp] |
| candidate | card_payments | 1473 | 0.54 pp [0.28 pp, 1.07 pp] | 36.59 pp [34.17 pp, 39.08 pp] |
| candidate | cash | 966 | 0.72 pp [0.35 pp, 1.49 pp] | 52.17 pp [49.02 pp, 55.31 pp] |
| candidate | transfers | 1328 | 3.99 pp [3.06 pp, 5.18 pp] | 32.61 pp [30.14 pp, 35.17 pp] |
| candidate | top_ups | 844 | 0.12 pp [0.02 pp, 0.67 pp] | 53.08 pp [49.71 pp, 56.43 pp] |
| candidate | account_other | 1143 | 0.52 pp [0.24 pp, 1.14 pp] | 49.34 pp [46.45 pp, 52.24 pp] |
| candidate | out_of_scope | 2597 | 1.69 pp [1.26 pp, 2.27 pp] | 1.69 pp [1.26 pp, 2.27 pp] |

- incumbent: one-sided 95% upper Wilson bound of W = 0.03 pp: below 2%.
- candidate: one-sided 95% upper Wilson bound of W = 1.46 pp: below 2%.
- A difference (candidate minus incumbent) = 32.75 pp; one-sided 95% Tango bounds [31.97 pp, 33.54 pp].

## Newly wrong auto-routes

Messages are quoted from the split under test; Banking77 texts are CC BY 4.0 (Casanueva et al., 2020).
- `train-1049` truth=`card_delivery_estimate` candidate=`card_arrival`: "Can you tell me when my card will arrive?"

## Cost and speed (not gated)

| Arm | Billed $/1,000 | Steady $/1,000 | Sparse $/1,000 | Latency p50/p95 ms | Reasoning tokens/message mean/p95 |
|---|---:|---:|---:|---|---|
| inc | 0.24 | 0.22 | 0.41 | 2803.91/7049.83 | 0.00/0.00 |
| haiku55-off | 0.06 | 0.06 | 0.45 | 2383.93/7075.60 | 0.00/0.00 |

Flags: none. Flags never change the verdict.
Latency is indicative, not a live-chat limit; all calls and retries are included in billed cost.
- incumbent, without cache reads: latency p50/p95 ms 3474.52/8793.08.
- incumbent, with cache reads: latency p50/p95 ms 2802.75/7048.53.
- candidate, without cache reads: latency p50/p95 ms not reported/not reported.
- candidate, with cache reads: latency p50/p95 ms 2383.93/7075.60.

## Not tested

Reasoning efforts above medium; Claude Haiku 4.5; gpt-4.1-mini; Jev 1.14 (jev-preview) and other decision models (Laya, Kev); live-chat latency limits; multi-turn conversations; languages other than English; streaming; real production traffic.
