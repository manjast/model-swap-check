# Amendment 3: risk-limit sensitivity (§7.10)

Contract `contract-v3` (analysis code `src tree 9f28c9586fea87f72dd401fe1afc14e4cf20efff, analysis tree d1ad64f511c1b492f1d665d154329a681536a515`), on the cert runs of `contract-v1` and `contract-v2`. Descriptive and post hoc; no verdict. Every earlier record stays as written.

Each configuration runs at τ_L, its smallest threshold with weighted dev W ≤ L (the §6 rule; 1.01 if none); `jev-noul` runs on the J2 signal of §7.9. Cert estimates are unweighted, on the items paired with the incumbent's run (API errors in either arm dropped), with two-sided 95% Wilson score intervals. W upper is the one-sided 95% upper Wilson bound of W. A vs inc is the paired A difference (configuration minus incumbent) at the same limit, with one-sided 95% Tango bounds.

| Configuration | Run | Run contract | Paired n | Dropped |
|---|---|---|---:|---:|
| `inc` | `inc-cert-20261022T123919Z` | `contract-v1` | 9758 | 0 |
| `luna-none` | `luna-none-cert-20261022T131547Z` | `contract-v1` | 9758 | 0 |
| `luna-none-x` | `luna-none-x-cert-20261022T140544Z` | `contract-v1` | 9758 | 0 |
| `haiku55-off` | `haiku55-off-cert-20261022T123919Z` | `contract-v1` | 9758 | 0 |
| `luna-dec` | `luna-dec-cert-20261022T134855Z` | `contract-v1` | 9758 | 0 |
| `jev-c51` | `jev-c51-cert-20261022T123919Z` | `contract-v1` | 9758 | 0 |
| `jev-noul` | `jev-noul-cert-20261022T152203Z` | `contract-v2` | 9758 | 0 |

## Summary: cert W / A

| Configuration | 1% | 2% | 5% | 10% | 15% |
|---|---|---|---|---|---|
| `inc` | 0.00% / 2.05% | 0.00% / 2.05% | 0.00% / 2.05% | 0.00% / 2.05% | 14.98% / 72.37% |
| `luna-none` | 0.00% / 0.07% | 1.30% / 34.75% | 4.12% / 50.20% | 4.12% / 50.20% | 12.91% / 71.26% |
| `luna-none-x` | 0.07% / 13.15% | 1.54% / 42.89% | 1.54% / 42.89% | 7.65% / 63.86% | 12.45% / 73.16% |
| `haiku55-off` | 0.42% / 19.98% | 1.26% / 34.80% | 2.80% / 46.88% | 7.69% / 63.01% | 7.69% / 63.01% |
| `luna-dec` | 0.73% / 15.87% | 1.49% / 25.32% | 4.83% / 47.27% | 9.84% / 62.71% | 14.31% / 70.40% |
| `jev-c51` | 0.00% / 0.00% | 0.00% / 0.00% | 4.48% / 53.63% | 9.46% / 66.19% | 14.83% / 74.90% |
| `jev-noul` | 0.46% / 16.11% | 2.03% / 40.88% | 3.81% / 46.97% | 3.81% / 46.97% | 3.81% / 46.97% |

## Limit 1%

| Configuration | τ_L | Weighted dev W / A | n | W [95% CI] | W upper | A [95% CI] | A vs inc [L, U] |
|---|---:|---|---:|---|---|---|---|
| `inc` | 0.95 | 0.00% / 1.83% | 9758 | 0.00 pp [0.00 pp, 0.04 pp] | 0.03 pp: below 1% | 2.05 pp [1.79 pp, 2.35 pp] | — |
| `luna-none` | 1.00 | 0.00% / 0.32% | 9758 | 0.00 pp [0.00 pp, 0.04 pp] | 0.03 pp: below 1% | 0.07 pp [0.03 pp, 0.15 pp] | -1.98 pp [-2.23 pp, -1.76 pp] |
| `luna-none-x` | 1.00 | 0.00% / 13.64% | 9758 | 0.07 pp [0.03 pp, 0.15 pp] | 0.13 pp: below 1% | 13.15 pp [12.49 pp, 13.83 pp] | 11.10 pp [10.57 pp, 11.65 pp] |
| `haiku55-off` | 0.92 | 0.56% / 20.25% | 9758 | 0.42 pp [0.31 pp, 0.57 pp] | 0.54 pp: below 1% | 19.98 pp [19.20 pp, 20.79 pp] | 17.93 pp [17.30 pp, 18.59 pp] |
| `luna-dec` | 1.00 | 0.87% / 14.96% | 9758 | 0.73 pp [0.58 pp, 0.92 pp] | 0.88 pp: below 1% | 15.87 pp [15.16 pp, 16.61 pp] | 13.82 pp [13.22 pp, 14.44 pp] |
| `jev-c51` | 1.01 | 0.00% / 0.00% | 9758 | 0.00 pp [0.00 pp, 0.04 pp] | 0.03 pp: below 1% | 0.00 pp [0.00 pp, 0.04 pp] | -2.05 pp [-2.30 pp, -1.83 pp] |
| `jev-noul` | 0.99 | 0.62% / 15.25% | 9758 | 0.46 pp [0.34 pp, 0.62 pp] | 0.59 pp: below 1% | 16.11 pp [15.39 pp, 16.85 pp] | 14.06 pp [13.48 pp, 14.66 pp] |

## Limit 2%

| Configuration | τ_L | Weighted dev W / A | n | W [95% CI] | W upper | A [95% CI] | A vs inc [L, U] |
|---|---:|---|---:|---|---|---|---|
| `inc` | 0.95 | 0.00% / 1.83% | 9758 | 0.00 pp [0.00 pp, 0.04 pp] | 0.03 pp: below 2% | 2.05 pp [1.79 pp, 2.35 pp] | — |
| `luna-none` | 0.99 | 1.14% / 34.55% | 9758 | 1.30 pp [1.10 pp, 1.55 pp] | 1.50 pp: below 2% | 34.75 pp [33.81 pp, 35.70 pp] | 32.70 pp [31.92 pp, 33.49 pp] |
| `luna-none-x` | 0.99 | 1.44% / 42.46% | 9758 | 1.54 pp [1.31 pp, 1.80 pp] | 1.76 pp: below 2% | 42.89 pp [41.91 pp, 43.87 pp] | 40.84 pp [40.02 pp, 41.66 pp] |
| `haiku55-off` | 0.90 | 1.48% / 33.47% | 9758 | 1.26 pp [1.06 pp, 1.50 pp] | 1.46 pp: below 2% | 34.80 pp [33.86 pp, 35.75 pp] | 32.75 pp [31.97 pp, 33.54 pp] |
| `luna-dec` | 0.99 | 1.67% / 25.07% | 9758 | 1.49 pp [1.26 pp, 1.75 pp] | 1.70 pp: below 2% | 25.32 pp [24.47 pp, 26.20 pp] | 23.27 pp [22.56 pp, 24.00 pp] |
| `jev-c51` | 1.01 | 0.00% / 0.00% | 9758 | 0.00 pp [0.00 pp, 0.04 pp] | 0.03 pp: below 2% | 0.00 pp [0.00 pp, 0.04 pp] | -2.05 pp [-2.30 pp, -1.83 pp] |
| `jev-noul` | 0.94 | 1.88% / 40.59% | 9758 | 2.03 pp [1.77 pp, 2.33 pp] | 2.28 pp: not below 2% | 40.88 pp [39.91 pp, 41.86 pp] | 38.83 pp [38.02 pp, 39.65 pp] |

## Limit 5%

| Configuration | τ_L | Weighted dev W / A | n | W [95% CI] | W upper | A [95% CI] | A vs inc [L, U] |
|---|---:|---|---:|---|---|---|---|
| `inc` | 0.95 | 0.00% / 1.83% | 9758 | 0.00 pp [0.00 pp, 0.04 pp] | 0.03 pp: below 5% | 2.05 pp [1.79 pp, 2.35 pp] | — |
| `luna-none` | 0.94 | 3.97% / 50.24% | 9758 | 4.12 pp [3.74 pp, 4.53 pp] | 4.46 pp: below 5% | 50.20 pp [49.21 pp, 51.20 pp] | 48.16 pp [47.32 pp, 48.99 pp] |
| `luna-none-x` | 0.99 | 1.44% / 42.46% | 9758 | 1.54 pp [1.31 pp, 1.80 pp] | 1.76 pp: below 5% | 42.89 pp [41.91 pp, 43.87 pp] | 40.84 pp [40.02 pp, 41.66 pp] |
| `haiku55-off` | 0.82 | 2.76% / 46.97% | 9758 | 2.80 pp [2.49 pp, 3.14 pp] | 3.09 pp: below 5% | 46.88 pp [45.90 pp, 47.88 pp] | 44.84 pp [44.01 pp, 45.67 pp] |
| `luna-dec` | 0.87 | 4.95% / 47.83% | 9758 | 4.83 pp [4.42 pp, 5.27 pp] | 5.20 pp: not below 5% | 47.27 pp [46.28 pp, 48.27 pp] | 45.22 pp [44.40 pp, 46.06 pp] |
| `jev-c51` | 0.97 | 4.51% / 53.81% | 9758 | 4.48 pp [4.09 pp, 4.91 pp] | 4.84 pp: below 5% | 53.63 pp [52.64 pp, 54.62 pp] | 51.58 pp [50.75 pp, 52.41 pp] |
| `jev-noul` | 0.13 | 3.89% / 46.87% | 9758 | 3.81 pp [3.45 pp, 4.21 pp] | 4.14 pp: below 5% | 46.97 pp [45.98 pp, 47.96 pp] | 44.92 pp [44.09 pp, 45.75 pp] |

## Limit 10%

| Configuration | τ_L | Weighted dev W / A | n | W [95% CI] | W upper | A [95% CI] | A vs inc [L, U] |
|---|---:|---|---:|---|---|---|---|
| `inc` | 0.95 | 0.00% / 1.83% | 9758 | 0.00 pp [0.00 pp, 0.04 pp] | 0.03 pp: below 10% | 2.05 pp [1.79 pp, 2.35 pp] | — |
| `luna-none` | 0.94 | 3.97% / 50.24% | 9758 | 4.12 pp [3.74 pp, 4.53 pp] | 4.46 pp: below 10% | 50.20 pp [49.21 pp, 51.20 pp] | 48.16 pp [47.32 pp, 48.99 pp] |
| `luna-none-x` | 0.78 | 7.84% / 63.60% | 9758 | 7.65 pp [7.13 pp, 8.19 pp] | 8.10 pp: below 10% | 63.86 pp [62.90 pp, 64.80 pp] | 61.81 pp [60.99 pp, 62.61 pp] |
| `haiku55-off` | 0.62 | 7.66% / 63.43% | 9758 | 7.69 pp [7.17 pp, 8.23 pp] | 8.14 pp: below 10% | 63.01 pp [62.05 pp, 63.97 pp] | 60.97 pp [60.15 pp, 61.77 pp] |
| `luna-dec` | 0.55 | 9.93% / 63.12% | 9758 | 9.84 pp [9.26 pp, 10.44 pp] | 10.35 pp: not below 10% | 62.71 pp [61.74 pp, 63.66 pp] | 60.66 pp [59.84 pp, 61.47 pp] |
| `jev-c51` | 0.82 | 9.62% / 67.13% | 9758 | 9.46 pp [8.89 pp, 10.06 pp] | 9.96 pp: below 10% | 66.19 pp [65.25 pp, 67.12 pp] | 64.14 pp [63.34 pp, 64.94 pp] |
| `jev-noul` | 0.13 | 3.89% / 46.87% | 9758 | 3.81 pp [3.45 pp, 4.21 pp] | 4.14 pp: below 10% | 46.97 pp [45.98 pp, 47.96 pp] | 44.92 pp [44.09 pp, 45.75 pp] |

## Limit 15%

| Configuration | τ_L | Weighted dev W / A | n | W [95% CI] | W upper | A [95% CI] | A vs inc [L, U] |
|---|---:|---|---:|---|---|---|---|
| `inc` | 0.90 | 14.34% / 71.83% | 9758 | 14.98 pp [14.29 pp, 15.70 pp] | 15.59 pp: not below 15% | 72.37 pp [71.48 pp, 73.25 pp] | — |
| `luna-none` | 0.78 | 13.64% / 71.81% | 9758 | 12.91 pp [12.26 pp, 13.59 pp] | 13.48 pp: below 15% | 71.26 pp [70.36 pp, 72.15 pp] | -1.11 pp [-1.74 pp, -0.48 pp] |
| `luna-none-x` | 0.00 | 12.24% / 73.02% | 9758 | 12.45 pp [11.81 pp, 13.12 pp] | 13.01 pp: below 15% | 73.16 pp [72.27 pp, 74.03 pp] | 0.79 pp [0.15 pp, 1.43 pp] |
| `haiku55-off` | 0.62 | 7.66% / 63.43% | 9758 | 7.69 pp [7.17 pp, 8.23 pp] | 8.14 pp: below 15% | 63.01 pp [62.05 pp, 63.97 pp] | -9.36 pp [-10.00 pp, -8.72 pp] |
| `luna-dec` | 0.00 | 14.42% / 71.02% | 9758 | 14.31 pp [13.63 pp, 15.01 pp] | 14.90 pp: below 15% | 70.40 pp [69.49 pp, 71.30 pp] | -1.97 pp [-2.62 pp, -1.31 pp] |
| `jev-c51` | 0.61 | 14.72% / 75.57% | 9758 | 14.83 pp [14.14 pp, 15.55 pp] | 15.43 pp: not below 15% | 74.90 pp [74.03 pp, 75.75 pp] | 2.53 pp [1.92 pp, 3.14 pp] |
| `jev-noul` | 0.13 | 3.89% / 46.87% | 9758 | 3.81 pp [3.45 pp, 4.21 pp] | 4.14 pp: below 15% | 46.97 pp [45.98 pp, 47.96 pp] | -25.40 pp [-26.20 pp, -24.62 pp] |

## Incumbent at fixed thresholds

Not fitted. τ = 0 auto-routes every in-catalog answer; τ = 0.90 is the confidence `gpt-4o-mini` states most often.

| τ | Weighted dev W / A | n | W [95% CI] | W upper | A [95% CI] |
|---:|---|---:|---|---|---|
| 0.00 | 26.76% / 88.21% | 9758 | 26.82 pp [25.95 pp, 27.71 pp] | 27.56 pp | 87.47 pp [86.79 pp, 88.11 pp] |
| 0.90 | 14.34% / 71.83% | 9758 | 14.98 pp [14.29 pp, 15.70 pp] | 15.59 pp | 72.37 pp [71.48 pp, 73.25 pp] |
