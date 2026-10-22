# D-J: inc → jev-noul

Analysis code: `synthetic-golden-v1`; decision_index=5.

**Verdict: INCONCLUSIVE**

Conditions: candidate τ = 0.70; incumbent τ = 0.70.
Paired n=210; dropped API-error/absent items=0.
Frozen dev W=0.00 pp; A=80.00 pp; power at frozen margins=65.00 pp.

## Gates

Family-adjusted column: one-sided 1 - 0.05/7 over all seven decisions (including NOT RUN).

| Gate | Estimate | Tango [L,U] | Wald [L,U] | Margin | 95% status | Family-adjusted |
|---|---:|---|---|---:|---|---|
| G1 W overall | 0.00 pp | [-1.27 pp, 1.27 pp] | [0.00 pp, 0.00 pp] | 1.00 pp | UNRESOLVED | UNRESOLVED |
| G2 W slices | — | see slice table | — | 3.00 pp | UNRESOLVED | UNRESOLVED |
| G3 A overall | 0.95 pp | [-2.34 pp, 4.34 pp] | [-2.18 pp, 4.08 pp] | -3.00 pp | PASS | UNRESOLVED |
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

not applicable (decision interface, not a model-ID swap).

## Newly wrong auto-routes

Messages are quoted from the split under test; Banking77 texts are CC BY 4.0 (Casanueva et al., 2020).
None.

## Cost and speed (not gated)

| Arm | Billed $/1,000 | Steady $/1,000 | Sparse $/1,000 | Latency p50/p95 ms | Reasoning tokens/message mean/p95 |
|---|---:|---:|---:|---|---|
| inc | 0.06 | 0.05 | 0.10 | 120.00/160.00 | not reported/not reported |
| jev-noul | 0.01 | 0.00 | 0.03 | 120.00/160.00 | not reported/not reported |

Flags: none. Flags never change the verdict.
Latency is indicative, not a live-chat limit; all calls and retries are included in billed cost.
- incumbent, without cache reads: latency p50/p95 ms 120.00/160.00.
- incumbent, with cache reads: latency p50/p95 ms 120.00/160.00.
- candidate, without cache reads: latency p50/p95 ms 120.00/160.00.
- candidate, with cache reads: latency p50/p95 ms 120.00/160.00.

## Not tested

Reasoning efforts above medium; Claude Haiku 4.5; gpt-4.1-mini; Jev 1.14 (jev-preview) and other decision models (Laya, Kev); live-chat latency limits; multi-turn conversations; languages other than English; streaming; real production traffic.
