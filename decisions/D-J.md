# D-J: inc → jev-c51

Analysis code: `src tree bb82167c21baa59dc1095573671bdde94edbe40f, analysis tree 884e88e42c8f7b0fbfebdb3f44a5511f2dd9fb06`; decision_index=5.

**Verdict: SHIP**

Conditions: candidate τ = 1.01; incumbent τ = 0.95.
Option-order sensitivity (pilot): 6/100 choices changed with the 50 intents reversed. Limitation: above 5%, so this verdict holds for the catalog order used here only.
Limitation (§7.8): the incumbent's weighted dev A at τ_inc is 1.83 pp, below the 3.00 pp G3 margin, so G3 cannot fail while its cert A stays below the margin; candidates were matched to the incumbent's dev W of 0.00 pp. See the policy analysis.
Paired n=9758; dropped API-error/absent items=0.
Frozen dev W=0.00 pp; A=0.00 pp; power at frozen margins=91.25 pp.

## Gates

Family-adjusted column: one-sided 1 - 0.05/7 over all seven decisions (including NOT RUN).

| Gate | Estimate | Tango [L,U] | Wald [L,U] | Margin | 95% status | Family-adjusted |
|---|---:|---|---|---:|---|---|
| G1 W overall | 0.00 pp | [-0.03 pp, 0.03 pp] | [0.00 pp, 0.00 pp] | 0.50 pp | PASS | PASS |
| G2 W slices | — | see slice table | — | 1.50 pp | PASS | PASS |
| G3 A overall | -2.05 pp | [-2.30 pp, -1.83 pp] | [-2.29 pp, -1.81 pp] | -3.00 pp | PASS | PASS |
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
| out_of_scope | 0.00 pp | [-0.10 pp, 0.10 pp]; harm L -0.23 pp | [0.00 pp, 0.00 pp] | 1.50 pp | PASS | PASS |

### Sample sizes for UNRESOLVED gates

None.

## Cluster-bootstrap sensitivity

10,000 intent-cluster resamples; descriptive only.
- G3: PASS → UNRESOLVED.

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

not applicable (decision interface, not a model-ID swap).

## Policy analysis at the 2% limit (§7.8, amendment 1)

Descriptive; it never changes the verdict. Each arm runs at its own τ fitted on dev to weighted W ≤ 2%: incumbent τ_2% = 0.95 (dev W 0.00 pp, A 1.83 pp), candidate τ_2% = 1.01 (dev W 0.00 pp, A 0.00 pp). Unweighted cert estimates on the paired items, two-sided 95% Wilson score intervals.

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
| candidate | overall | 9758 | 0.00 pp [0.00 pp, 0.04 pp] | 0.00 pp [0.00 pp, 0.04 pp] |
| candidate | cards | 1407 | 0.00 pp [0.00 pp, 0.27 pp] | 0.00 pp [0.00 pp, 0.27 pp] |
| candidate | card_payments | 1473 | 0.00 pp [0.00 pp, 0.26 pp] | 0.00 pp [0.00 pp, 0.26 pp] |
| candidate | cash | 966 | 0.00 pp [0.00 pp, 0.40 pp] | 0.00 pp [0.00 pp, 0.40 pp] |
| candidate | transfers | 1328 | 0.00 pp [0.00 pp, 0.29 pp] | 0.00 pp [0.00 pp, 0.29 pp] |
| candidate | top_ups | 844 | 0.00 pp [0.00 pp, 0.45 pp] | 0.00 pp [0.00 pp, 0.45 pp] |
| candidate | account_other | 1143 | 0.00 pp [0.00 pp, 0.33 pp] | 0.00 pp [0.00 pp, 0.33 pp] |
| candidate | out_of_scope | 2597 | 0.00 pp [0.00 pp, 0.15 pp] | 0.00 pp [0.00 pp, 0.15 pp] |

- incumbent: one-sided 95% upper Wilson bound of W = 0.03 pp: below 2%.
- candidate: one-sided 95% upper Wilson bound of W = 0.03 pp: below 2%.
- A difference (candidate minus incumbent) = -2.05 pp; one-sided 95% Tango bounds [-2.30 pp, -1.83 pp].

## Newly wrong auto-routes

Messages are quoted from the split under test; Banking77 texts are CC BY 4.0 (Casanueva et al., 2020).
None.

## Cost and speed (not gated)

| Arm | Billed $/1,000 | Steady $/1,000 | Sparse $/1,000 | Latency p50/p95 ms | Reasoning tokens/message mean/p95 |
|---|---:|---:|---:|---|---|
| inc | 0.24 | 0.22 | 0.41 | 2803.91/7049.83 | 0.00/0.00 |
| jev-c51 | 0.15 | 0.15 | 0.15 | 2379.42/6006.82 | not reported/not reported |

Flags: none. Flags never change the verdict.
Latency is indicative, not a live-chat limit; all calls and retries are included in billed cost.
- incumbent, without cache reads: latency p50/p95 ms 3474.52/8793.08.
- incumbent, with cache reads: latency p50/p95 ms 2802.75/7048.53.
- candidate, without cache reads: latency p50/p95 ms 2379.42/6006.82.
- candidate, with cache reads: latency p50/p95 ms not reported/not reported.

## Not tested

Reasoning efforts above medium; Claude Haiku 4.5; gpt-4.1-mini; Jev 1.14 (jev-preview) and other decision models (Laya, Kev); live-chat latency limits; multi-turn conversations; languages other than English; streaming; real production traffic.
