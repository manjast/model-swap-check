# D-O: inc → luna-dec

Analysis code: `synthetic-golden-v1`; decision_index=6.

**Verdict: BLOCK**

Conditions: candidate τ = 0.70; incumbent τ = 0.70.
Paired n=210; dropped API-error/absent items=0.
Frozen dev W=0.00 pp; A=80.00 pp; power at frozen margins=65.00 pp.

## Gates

Family-adjusted column: one-sided 1 - 0.05/7 over all seven decisions (including NOT RUN).

| Gate | Estimate | Tango [L,U] | Wald [L,U] | Margin | 95% status | Family-adjusted |
|---|---:|---|---|---:|---|---|
| G1 W overall | 8.10 pp | [5.51 pp, 11.75 pp] | [5.00 pp, 11.19 pp] | 1.00 pp | FAIL | FAIL |
| G2 W slices | — | see slice table | — | 3.00 pp | UNRESOLVED | UNRESOLVED |
| G3 A overall | 5.71 pp | [3.16 pp, 9.11 pp] | [2.86 pp, 8.57 pp] | -3.00 pp | PASS | PASS |
| G4 V | 99.52 pp | — | — | 99.50 pp | PASS | PASS |

### Slices

| Slice | Estimate | Tango [L,U] | Wald [L,U] | Margin | 95% status | Family-adjusted |
|---|---:|---|---|---:|---|---|
| cards | 0.00 pp | [-8.27 pp, 8.27 pp]; harm L -16.67 pp | [0.00 pp, 0.00 pp] | 3.00 pp | UNRESOLVED | UNRESOLVED |
| card_payments | 10.00 pp | [0.90 pp, 22.55 pp]; harm L -8.34 pp | [0.99 pp, 19.01 pp] | 3.00 pp | UNRESOLVED | UNRESOLVED |
| cash | 10.00 pp | [0.90 pp, 22.55 pp]; harm L -8.34 pp | [0.99 pp, 19.01 pp] | 3.00 pp | UNRESOLVED | UNRESOLVED |
| transfers | 6.67 pp | [-2.16 pp, 18.27 pp]; harm L -11.12 pp | [-0.82 pp, 14.16 pp] | 3.00 pp | UNRESOLVED | UNRESOLVED |
| top_ups | 10.00 pp | [0.90 pp, 22.55 pp]; harm L -8.34 pp | [0.99 pp, 19.01 pp] | 3.00 pp | UNRESOLVED | UNRESOLVED |
| account_other | 10.00 pp | [0.90 pp, 22.55 pp]; harm L -8.34 pp | [0.99 pp, 19.01 pp] | 3.00 pp | UNRESOLVED | UNRESOLVED |
| out_of_scope | 10.00 pp | [0.90 pp, 22.55 pp]; harm L -8.34 pp | [0.99 pp, 19.01 pp] | 3.00 pp | UNRESOLVED | UNRESOLVED |

### Sample sizes for UNRESOLVED gates

- G2/cards: total paired n needed = no discordant pairs observed.
- G2/card_payments: total paired n needed = not reachable at this point estimate.
- G2/cash: total paired n needed = not reachable at this point estimate.
- G2/transfers: total paired n needed = not reachable at this point estimate.
- G2/top_ups: total paired n needed = not reachable at this point estimate.
- G2/account_other: total paired n needed = not reachable at this point estimate.
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

not applicable (decision interface, not a model-ID swap).

## Newly wrong auto-routes

Messages are quoted from the split under test; Banking77 texts are CC BY 4.0 (Casanueva et al., 2020).
- `synthetic-cert-03-020` truth=`balance_not_updated_after_bank_transfer` candidate=`activate_my_card`: "Please help with my banking request number 20."
- `synthetic-cert-02-028` truth=`cash_withdrawal_charge` candidate=`activate_my_card`: "Please help with my banking request number 28."
- `synthetic-cert-03-009` truth=`balance_not_updated_after_bank_transfer` candidate=`activate_my_card`: "Please help with my banking request number 9."
- `synthetic-cert-01-014` truth=`card_payment_fee_charged` candidate=`activate_my_card`: "Please help with my banking request number 14."
- `synthetic-cert-02-006` truth=`cash_withdrawal_charge` candidate=`activate_my_card`: "Please help with my banking request number 6."
- `synthetic-cert-04-012` truth=`automatic_top_up` candidate=`activate_my_card`: "Please help with my banking request number 12."
- `synthetic-cert-01-003` truth=`card_payment_fee_charged` candidate=`activate_my_card`: "Please help with my banking request number 3."
- `synthetic-cert-02-017` truth=`cash_withdrawal_charge` candidate=`activate_my_card`: "Please help with my banking request number 17."
- `synthetic-cert-05-026` truth=`Refund_not_showing_up` candidate=`activate_my_card`: "Please help with my banking request number 26."
- `synthetic-cert-01-025` truth=`card_payment_fee_charged` candidate=`activate_my_card`: "Please help with my banking request number 25."
- `synthetic-cert-04-001` truth=`automatic_top_up` candidate=`activate_my_card`: "Please help with my banking request number 1."
- `synthetic-cert-05-004` truth=`Refund_not_showing_up` candidate=`activate_my_card`: "Please help with my banking request number 4."
- `synthetic-cert-04-023` truth=`automatic_top_up` candidate=`activate_my_card`: "Please help with my banking request number 23."
- `synthetic-cert-05-015` truth=`Refund_not_showing_up` candidate=`activate_my_card`: "Please help with my banking request number 15."
- `synthetic-cert-06-007` truth=`age_limit` candidate=`activate_my_card`: "Please help with my banking request number 7."
- `synthetic-cert-06-029` truth=`age_limit` candidate=`activate_my_card`: "Please help with my banking request number 29."
- `synthetic-cert-06-018` truth=`age_limit` candidate=`activate_my_card`: "Please help with my banking request number 18."

## Cost and speed (not gated)

| Arm | Billed $/1,000 | Steady $/1,000 | Sparse $/1,000 | Latency p50/p95 ms | Reasoning tokens/message mean/p95 |
|---|---:|---:|---:|---|---|
| inc | 0.06 | 0.05 | 0.10 | 120.00/160.00 | not reported/not reported |
| luna-dec | 0.06 | 0.06 | 0.06 | 120.00/160.00 | not reported/not reported |

Flags: none. Flags never change the verdict.
Latency is indicative, not a live-chat limit; all calls and retries are included in billed cost.
- incumbent, without cache reads: latency p50/p95 ms 120.00/160.00.
- incumbent, with cache reads: latency p50/p95 ms 120.00/160.00.
- candidate, without cache reads: latency p50/p95 ms 120.00/160.00.
- candidate, with cache reads: latency p50/p95 ms 120.00/160.00.

## Not tested

Reasoning efforts above medium; Claude Haiku 4.5; gpt-4.1-mini; Jev 1.14 (jev-preview) and other decision models (Laya, Kev); live-chat latency limits; multi-turn conversations; languages other than English; streaming; real production traffic.
