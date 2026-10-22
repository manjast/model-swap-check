# D-A1: inc → luna-none

Analysis code: `synthetic-golden-v1`; decision_index=1.

**Verdict: BLOCK**

Conditions: candidate τ = 0.70; incumbent τ = 0.70.
Paired n=209; dropped API-error/absent items=1.
Frozen dev W=0.00 pp; A=80.00 pp; power at frozen margins=65.00 pp.

## Gates

Family-adjusted column: one-sided 1 - 0.05/7 over all seven decisions (including NOT RUN).

| Gate | Estimate | Tango [L,U] | Wald [L,U] | Margin | 95% status | Family-adjusted |
|---|---:|---|---|---:|---|---|
| G1 W overall | 2.87 pp | [1.49 pp, 5.45 pp] | [0.97 pp, 4.77 pp] | 1.00 pp | FAIL | UNRESOLVED |
| G2 W slices | — | see slice table | — | 3.00 pp | UNRESOLVED | UNRESOLVED |
| G3 A overall | 5.26 pp | [3.25 pp, 8.42 pp] | [2.72 pp, 7.80 pp] | -3.00 pp | PASS | PASS |
| G4 V | 100.00 pp | — | — | 99.50 pp | PASS | PASS |

### Slices

| Slice | Estimate | Tango [L,U] | Wald [L,U] | Margin | 95% status | Family-adjusted |
|---|---:|---|---|---:|---|---|
| cards | 3.45 pp | [-5.38 pp, 14.07 pp]; harm L -14.29 pp | [-2.12 pp, 9.02 pp] | 3.00 pp | UNRESOLVED | UNRESOLVED |
| card_payments | 3.33 pp | [-5.21 pp, 13.64 pp]; harm L -13.89 pp | [-2.06 pp, 8.72 pp] | 3.00 pp | UNRESOLVED | UNRESOLVED |
| cash | 3.33 pp | [-5.21 pp, 13.64 pp]; harm L -13.89 pp | [-2.06 pp, 8.72 pp] | 3.00 pp | UNRESOLVED | UNRESOLVED |
| transfers | 3.33 pp | [-5.21 pp, 13.64 pp]; harm L -13.89 pp | [-2.06 pp, 8.72 pp] | 3.00 pp | UNRESOLVED | UNRESOLVED |
| top_ups | 3.33 pp | [-5.21 pp, 13.64 pp]; harm L -13.89 pp | [-2.06 pp, 8.72 pp] | 3.00 pp | UNRESOLVED | UNRESOLVED |
| account_other | 0.00 pp | [-8.27 pp, 8.27 pp]; harm L -16.67 pp | [0.00 pp, 0.00 pp] | 3.00 pp | UNRESOLVED | UNRESOLVED |
| out_of_scope | 3.33 pp | [-5.21 pp, 13.64 pp]; harm L -13.89 pp | [-2.06 pp, 8.72 pp] | 3.00 pp | UNRESOLVED | UNRESOLVED |

### Sample sizes for UNRESOLVED gates

- G2/cards: total paired n needed = not reachable at this point estimate.
- G2/card_payments: total paired n needed = not reachable at this point estimate.
- G2/cash: total paired n needed = not reachable at this point estimate.
- G2/transfers: total paired n needed = not reachable at this point estimate.
- G2/top_ups: total paired n needed = not reachable at this point estimate.
- G2/account_other: total paired n needed = no discordant pairs observed.
- G2/out_of_scope: total paired n needed = not reachable at this point estimate.

## Cluster-bootstrap sensitivity

10,000 intent-cluster resamples; descriptive only.
- G2: UNRESOLVED → FAIL.

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
| overall | 209 | 2.87 pp [1.32 pp, 6.12 pp] | 86.12 pp [80.78 pp, 90.16 pp] |
| cards | 29 | 3.45 pp [0.61 pp, 17.18 pp] | 100.00 pp [88.30 pp, 100.00 pp] |
| card_payments | 30 | 3.33 pp [0.59 pp, 16.67 pp] | 100.00 pp [88.65 pp, 100.00 pp] |
| cash | 30 | 3.33 pp [0.59 pp, 16.67 pp] | 100.00 pp [88.65 pp, 100.00 pp] |
| transfers | 30 | 3.33 pp [0.59 pp, 16.67 pp] | 100.00 pp [88.65 pp, 100.00 pp] |
| top_ups | 30 | 3.33 pp [0.59 pp, 16.67 pp] | 100.00 pp [88.65 pp, 100.00 pp] |
| account_other | 30 | 0.00 pp [0.00 pp, 11.35 pp] | 100.00 pp [88.65 pp, 100.00 pp] |
| out_of_scope | 30 | 3.33 pp [0.59 pp, 16.67 pp] | 3.33 pp [0.59 pp, 16.67 pp] |

## Newly wrong auto-routes

Messages are quoted from the split under test; Banking77 texts are CC BY 4.0 (Casanueva et al., 2020).
- `synthetic-cert-04-028` truth=`automatic_top_up` candidate=`activate_my_card`: "Please help with my banking request number 28."
- `synthetic-cert-02-014` truth=`cash_withdrawal_charge` candidate=`activate_my_card`: "Please help with my banking request number 14."
- `synthetic-cert-03-021` truth=`balance_not_updated_after_bank_transfer` candidate=`activate_my_card`: "Please help with my banking request number 21."
- `synthetic-cert-01-007` truth=`card_payment_fee_charged` candidate=`activate_my_card`: "Please help with my banking request number 7."
- `synthetic-cert-00-000` truth=`activate_my_card` candidate=`declined_transfer`: "Please help with my banking request number 0."
- `synthetic-cert-06-005` truth=`age_limit` candidate=`activate_my_card`: "Please help with my banking request number 5."

## Cost and speed (not gated)

| Arm | Billed $/1,000 | Steady $/1,000 | Sparse $/1,000 | Latency p50/p95 ms | Reasoning tokens/message mean/p95 |
|---|---:|---:|---:|---|---|
| inc | 0.06 | 0.05 | 0.10 | 120.00/160.00 | not reported/not reported |
| luna-none | 0.03 | 0.01 | 0.07 | 120.00/160.00 | not reported/not reported |

Flags: none. Flags never change the verdict.
Latency is indicative, not a live-chat limit; all calls and retries are included in billed cost.
- incumbent, without cache reads: latency p50/p95 ms 120.00/160.00.
- incumbent, with cache reads: latency p50/p95 ms 120.00/160.00.
- candidate, without cache reads: latency p50/p95 ms 120.00/160.00.
- candidate, with cache reads: latency p50/p95 ms 120.00/160.00.

## Not tested

Reasoning efforts above medium; Claude Haiku 4.5; gpt-4.1-mini; Jev 1.14 (jev-preview) and other decision models (Laya, Kev); live-chat latency limits; multi-turn conversations; languages other than English; streaming; real production traffic.
