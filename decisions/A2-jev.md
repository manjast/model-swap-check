# Amendment 2: Jev at its top confidence (§7.9)

Contract `contract-v2` (analysis code `src tree ea01a607f0610f9eb5139afb198db9fe0c101cbc, analysis tree afc55185ad38d92295a52ebf5228478c8493e713`); the incumbent and `jev-c51` reuse their `contract-v1` cert runs. Descriptive; no verdict. D-J stays as registered.

Incumbent: `inc-cert-20261022T123919Z` at τ_inc = 0.95. Unweighted cert estimates on the paired items, two-sided 95% Wilson score intervals.

## J1: `jev-c51` at τ = 1.00

Run `jev-c51-cert-20261022T123919Z`; frozen τ = 1.00 (weighted dev W 2.29 pp, A 42.38 pp). Paired n=9758; dropped API-error/absent items=0.

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
| candidate | overall | 9758 | 2.22 pp [1.95 pp, 2.54 pp] | 42.96 pp [41.98 pp, 43.94 pp] |
| candidate | cards | 1407 | 0.64 pp [0.34 pp, 1.21 pp] | 65.17 pp [62.65 pp, 67.62 pp] |
| candidate | card_payments | 1473 | 1.02 pp [0.62 pp, 1.67 pp] | 55.13 pp [52.58 pp, 57.65 pp] |
| candidate | cash | 966 | 1.35 pp [0.79 pp, 2.29 pp] | 65.32 pp [62.26 pp, 68.26 pp] |
| candidate | transfers | 1328 | 4.74 pp [3.73 pp, 6.02 pp] | 38.48 pp [35.90 pp, 41.13 pp] |
| candidate | top_ups | 844 | 0.95 pp [0.48 pp, 1.86 pp] | 65.40 pp [62.13 pp, 68.54 pp] |
| candidate | account_other | 1143 | 0.52 pp [0.24 pp, 1.14 pp] | 58.27 pp [55.39 pp, 61.09 pp] |
| candidate | out_of_scope | 2597 | 3.97 pp [3.28 pp, 4.79 pp] | 3.97 pp [3.28 pp, 4.79 pp] |

- incumbent: one-sided 95% upper Wilson bound of W = 0.03 pp: below 2%.
- candidate: one-sided 95% upper Wilson bound of W = 2.48 pp: not below 2%.
- A difference (candidate minus incumbent) = 40.91 pp; one-sided 95% Tango bounds [40.09 pp, 41.73 pp].

## J2: `jev-noul`, Noul match probability ≥ τ_J2 where the Choice confidence is 1.00

Run `jev-noul-cert-20261022T152203Z`; frozen τ = 0.94 (weighted dev W 1.88 pp, A 40.59 pp). Paired n=9758; dropped API-error/absent items=0.

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
| candidate | overall | 9758 | 2.03 pp [1.77 pp, 2.33 pp] | 40.88 pp [39.91 pp, 41.86 pp] |
| candidate | cards | 1407 | 0.92 pp [0.54 pp, 1.57 pp] | 63.26 pp [60.70 pp, 65.73 pp] |
| candidate | card_payments | 1473 | 0.88 pp [0.52 pp, 1.50 pp] | 51.05 pp [48.50 pp, 53.60 pp] |
| candidate | cash | 966 | 1.55 pp [0.94 pp, 2.55 pp] | 61.39 pp [58.28 pp, 64.41 pp] |
| candidate | transfers | 1328 | 3.61 pp [2.74 pp, 4.76 pp] | 36.30 pp [33.75 pp, 38.92 pp] |
| candidate | top_ups | 844 | 0.83 pp [0.40 pp, 1.70 pp] | 63.98 pp [60.69 pp, 67.15 pp] |
| candidate | account_other | 1143 | 0.44 pp [0.19 pp, 1.02 pp] | 55.56 pp [52.66 pp, 58.41 pp] |
| candidate | out_of_scope | 2597 | 3.74 pp [3.07 pp, 4.54 pp] | 3.74 pp [3.07 pp, 4.54 pp] |

- incumbent: one-sided 95% upper Wilson bound of W = 0.03 pp: below 2%.
- candidate: one-sided 95% upper Wilson bound of W = 2.28 pp: not below 2%.
- A difference (candidate minus incumbent) = 38.83 pp; one-sided 95% Tango bounds [38.02 pp, 39.65 pp].
