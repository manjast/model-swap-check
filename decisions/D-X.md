# D-X: inc → luna-none-x

Analysis code: `src tree bb82167c21baa59dc1095573671bdde94edbe40f, analysis tree 884e88e42c8f7b0fbfebdb3f44a5511f2dd9fb06`; decision_index=7.

**Verdict: SHIP**

Conditions: candidate τ = 1.00; incumbent τ = 0.95.
Use adapted prompt SHA-256 `8b0ffa521ce81eb8d74d86450482fde4a05ef8a3864a3ceafd5fc45781840fb5` (dev iteration 3), not the incumbent prompt.
Limitation (§7.8): the incumbent's weighted dev A at τ_inc is 1.83 pp, below the 3.00 pp G3 margin, so G3 cannot fail while its cert A stays below the margin; candidates were matched to the incumbent's dev W of 0.00 pp. See the policy analysis.
Paired n=9758; dropped API-error/absent items=0.
Frozen dev W=0.00 pp; A=13.64 pp; power at frozen margins=91.25 pp.

## Gates

Family-adjusted column: one-sided 1 - 0.05/7 over all seven decisions (including NOT RUN).

| Gate | Estimate | Tango [L,U] | Wald [L,U] | Margin | 95% status | Family-adjusted |
|---|---:|---|---|---:|---|---|
| G1 W overall | 0.07 pp | [0.04 pp, 0.13 pp] | [0.03 pp, 0.12 pp] | 0.50 pp | PASS | PASS |
| G2 W slices | — | see slice table | — | 1.50 pp | PASS | PASS |
| G3 A overall | 11.10 pp | [10.57 pp, 11.65 pp] | [10.56 pp, 11.64 pp] | -3.00 pp | PASS | PASS |
| G4 V | 100.00 pp | — | — | 99.50 pp | PASS | PASS |

### Slices

| Slice | Estimate | Tango [L,U] | Wald [L,U] | Margin | 95% status | Family-adjusted |
|---|---:|---|---|---:|---|---|
| cards | 0.07 pp | [-0.12 pp, 0.32 pp]; harm L -0.35 pp | [-0.05 pp, 0.19 pp] | 1.50 pp | PASS | PASS |
| card_payments | 0.00 pp | [-0.18 pp, 0.18 pp]; harm L -0.41 pp | [0.00 pp, 0.00 pp] | 1.50 pp | PASS | PASS |
| cash | 0.00 pp | [-0.28 pp, 0.28 pp]; harm L -0.62 pp | [0.00 pp, 0.00 pp] | 1.50 pp | PASS | PASS |
| transfers | 0.38 pp | [0.17 pp, 0.77 pp]; harm L -0.08 pp | [0.10 pp, 0.65 pp] | 1.50 pp | PASS | PASS |
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
| overall | 9758 | 6.62 pp [6.14 pp, 7.13 pp] | 61.43 pp [60.46 pp, 62.39 pp] |
| cards | 1407 | 3.91 pp [3.02 pp, 5.05 pp] | 91.90 pp [90.36 pp, 93.21 pp] |
| card_payments | 1473 | 5.36 pp [4.32 pp, 6.63 pp] | 76.78 pp [74.56 pp, 78.87 pp] |
| cash | 966 | 3.83 pp [2.79 pp, 5.23 pp] | 81.06 pp [78.46 pp, 83.40 pp] |
| transfers | 1328 | 12.20 pp [10.55 pp, 14.07 pp] | 65.14 pp [62.53 pp, 67.65 pp] |
| top_ups | 844 | 1.78 pp [1.08 pp, 2.91 pp] | 79.27 pp [76.40 pp, 81.86 pp] |
| account_other | 1143 | 4.55 pp [3.49 pp, 5.92 pp] | 88.10 pp [86.10 pp, 89.85 pp] |
| out_of_scope | 2597 | 9.47 pp [8.41 pp, 10.66 pp] | 9.47 pp [8.41 pp, 10.66 pp] |

## Policy analysis at the 2% limit (§7.8, amendment 1)

Descriptive; it never changes the verdict. Each arm runs at its own τ fitted on dev to weighted W ≤ 2%: incumbent τ_2% = 0.95 (dev W 0.00 pp, A 1.83 pp), candidate τ_2% = 0.99 (dev W 1.44 pp, A 42.46 pp). Unweighted cert estimates on the paired items, two-sided 95% Wilson score intervals.

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
| candidate | overall | 9758 | 1.54 pp [1.31 pp, 1.80 pp] | 42.89 pp [41.91 pp, 43.87 pp] |
| candidate | cards | 1407 | 0.28 pp [0.11 pp, 0.73 pp] | 73.13 pp [70.76 pp, 75.39 pp] |
| candidate | card_payments | 1473 | 1.15 pp [0.72 pp, 1.84 pp] | 46.91 pp [44.37 pp, 49.46 pp] |
| candidate | cash | 966 | 1.66 pp [1.02 pp, 2.67 pp] | 64.91 pp [61.84 pp, 67.85 pp] |
| candidate | transfers | 1328 | 4.52 pp [3.53 pp, 5.77 pp] | 40.44 pp [37.83 pp, 43.10 pp] |
| candidate | top_ups | 844 | 0.71 pp [0.33 pp, 1.54 pp] | 61.97 pp [58.64 pp, 65.18 pp] |
| candidate | account_other | 1143 | 1.14 pp [0.67 pp, 1.94 pp] | 65.09 pp [62.28 pp, 67.80 pp] |
| candidate | out_of_scope | 2597 | 1.31 pp [0.94 pp, 1.82 pp] | 1.31 pp [0.94 pp, 1.82 pp] |

- incumbent: one-sided 95% upper Wilson bound of W = 0.03 pp: below 2%.
- candidate: one-sided 95% upper Wilson bound of W = 1.76 pp: below 2%.
- A difference (candidate minus incumbent) = 40.84 pp; one-sided 95% Tango bounds [40.02 pp, 41.66 pp].

## Newly wrong auto-routes

Messages are quoted from the split under test; Banking77 texts are CC BY 4.0 (Casanueva et al., 2020).
- `test-2711` truth=`balance_not_updated_after_bank_transfer` candidate=`pending_transfer`: "My transfer is pending."
- `train-225` truth=`card_linking` candidate=`activate_my_card`: "Can I activate a card in the app?"
- `train-8769` truth=`balance_not_updated_after_bank_transfer` candidate=`transfer_timing`: "How long do bank transfers usually take?"
- `train-6067` truth=`pending_transfer` candidate=`transfer_timing`: "How long does a transfer take?"
- `train-2722` truth=`transfer_not_received_by_recipient` candidate=`transfer_timing`: "How long will it take for my transfer to arrive?"
- `test-845` truth=`transfer_not_received_by_recipient` candidate=`transfer_timing`: "How long does it take for a transfer to get to a recipient?"
- `test-2637` truth=`get_disposable_virtual_card` candidate=`disposable_card_limits`: "how many transactions can i make with a disposable card"

## Cost and speed (not gated)

| Arm | Billed $/1,000 | Steady $/1,000 | Sparse $/1,000 | Latency p50/p95 ms | Reasoning tokens/message mean/p95 |
|---|---:|---:|---:|---|---|
| inc | 0.24 | 0.22 | 0.41 | 2803.91/7049.83 | 0.00/0.00 |
| luna-none-x | 0.04 | 0.04 | 0.31 | 1658.88/3499.61 | 0.00/0.00 |

Flags: none. Flags never change the verdict.
Latency is indicative, not a live-chat limit; all calls and retries are included in billed cost.
- incumbent, without cache reads: latency p50/p95 ms 3474.52/8793.08.
- incumbent, with cache reads: latency p50/p95 ms 2802.75/7048.53.
- candidate, without cache reads: latency p50/p95 ms not reported/not reported.
- candidate, with cache reads: latency p50/p95 ms 1658.88/3499.61.

## Not tested

Reasoning efforts above medium; Claude Haiku 4.5; gpt-4.1-mini; Jev 1.14 (jev-preview) and other decision models (Laya, Kev); live-chat latency limits; multi-turn conversations; languages other than English; streaming; real production traffic.
