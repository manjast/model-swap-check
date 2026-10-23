# Classifier baseline (post hoc)

Written on 2026-10-23, after every test result was published and before any classifier prediction existed. Descriptive: no registered decision, threshold, contract or LLM number changes.

## Question

A reader asked whether a dedicated classifier trained on the labelled messages would beat the LLM candidates for fixed queues, and be faster, cheaper and easier to calibrate. The study only compared models a `gpt-4o-mini` router could switch to. This baseline answers the question on the same split, at the same misroute limits as amendment 3 (spec §7.10).

## Method, fixed before the fit

`analysis/classifier_baseline.py`, all outputs under `baselines/embed-lr/`:

- **Features:** OpenAI `text-embedding-3-small` (1,536 dimensions), one embedding per message for the 250 `examples`, 3,075 `dev` and 9,758 `cert` messages, sent verbatim in one paid pass. The vectors stay in the git-ignored `data/embeddings/` (derived from message text); their SHA-256, token count and cost are committed.
- **Classifier:** scikit-learn 1.9.1 `LogisticRegression` (L-BFGS, multinomial, default L2), confidence = the top class's probability. C is chosen from 0.1, 1, 10, 100 and 1,000 by 5-fold cross-validated log loss on the training items (seed 20261023); no other tuning.
- **Training data:** the 250 `examples` and the 3,075 `dev` messages with their labels. The LLMs used `dev` only to fit thresholds (and the D-X prompt rewrite); a classifier uses the labels to learn, which is the point of the question.
- **Two variants for "none of these":** 27% of `cert` belongs to none of the 50 queues.
  - `lr-51`: a 51st class trained on the 1,075 `dev` out-of-scope messages; a message whose top class is that one goes to a person. Optimistic here: the `cert` out-of-scope messages come from the same 27 Banking77 intents as the `dev` ones.
  - `lr-50`: the 50 queues only; an out-of-scope message is caught only by the threshold. The fairer match for the LLMs, whose prompt never showed an out-of-scope example.
- **Thresholds:** each `dev` message is predicted by a model trained without it (5-fold cross-fitting, `examples` always in training). At each limit (1, 2, 5, 10 and 15%), τ is the smallest threshold with weighted `dev` W at or below the limit (the §7.10 rule, `swapcheck.calibrate.fit_candidate`). The final model, trained on all training items, predicts `cert` once; A and W are measured there at each τ, with the one-sided 95% Wilson upper bound of W against the limit, as in `decisions/A3-limits.md`.
- **Accuracy:** top pick right on in-scope messages, on cross-fitted `dev` and on `cert`.
- **Cost and speed:** embedding tokens per message at $0.02 per million tokens (OpenAI pricing page, 2026-10-23); logistic-regression time per message on this machine; 100 single-message embedding calls from Belgrade, one at a time, for latency (p50 and p90).

`python analysis/classifier_baseline.py report` prints the results from the committed predictions; nothing else is reported.

## Results

Embeddings: 13,083 messages, 176,055 tokens, $0.0035. Output of `python analysis/classifier_baseline.py report`, automation (misroutes) in % of the 9,758 test messages; \* marks a one-sided 95% Wilson upper bound of W at or above the limit:

| Variant | 1% | 2% | 5% | 10% | 15% | Top pick right, tuning / test | C |
|---|---:|---:|---:|---:|---:|---:|---:|
| `lr-51` | 58.76 (1.32)\* | 63.29 (2.04)\* | 71.25 (5.24)\* | 71.25 (5.24) | 71.25 (5.24) | 89.8% / 90.0% | 100 |
| `lr-50` | 26.44 (1.75)\* | 36.78 (2.53)\* | 57.99 (5.05)\* | 72.46 (10.15)\* | 80.93 (15.48)\* | 92.9% / 93.0% | 100 |
| `lr-51`, fold average† | 56.59 (1.08)\* | 62.11 (1.79)\* | 70.93 (5.12)\* | 70.93 (5.12) | 70.93 (5.12) | 89.8% / 89.7% | 100 |
| `lr-50`, fold average† | 20.37 (1.04)\* | 31.33 (1.94)\* | 54.31 (4.41) | 69.89 (8.87) | 79.05 (14.29) | 92.9% / 92.9% | 100 |

† Added after the results (`fit-folds`): test probabilities averaged over the five cross-fitting models, the same models whose tuning predictions set the thresholds, instead of one model retrained on all items.

Cost: $0.0003 per 1,000 messages for the embedding; logistic regression adds 14 µs per message on this machine. Latency: 100 single-message embedding calls from Belgrade, p50 304 ms, p90 378 ms. A first latency sample (p50 321 ms) ran while the fit used every CPU core and was replaced by this one on an idle machine.

The study's configurations at the same limits, automation in % (README table, from `decisions/A3-limits.md`), with the fairer classifier variant:

| Configuration | 1% | 2% | 5% | 10% | 15% | $ per 1,000, busy / quiet | Latency p50 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `gpt-4o-mini` (incumbent) | 2.05 | 2.05 | 2.05 | 2.05 | 72.37\* | 0.218 / 0.410 | 1.02 s |
| Luna, incumbent prompt | 0.07 | 34.75 | 50.20 | 50.20 | 71.26 | 0.039 / 0.277 | 1.26 s |
| Luna, adapted prompt | 13.15 | 42.89 | 42.89 | 63.86 | 73.16 | 0.042 / 0.312 | – |
| Claude Haiku 5.5 | 19.98 | 34.80 | 46.88 | 63.01 | 63.01 | 0.059 / 0.452 | 1.25 s |
| Decisions API (Luna) | 15.87 | 25.32 | 47.27\* | 62.71\* | 70.40 | 0.232 / 0.232 | 0.28 s |
| Jev, Choice confidence | 0.00 | 0.00 | 53.63 | 66.19 | 74.90\* | 0.146 / 0.146 | 0.28 s |
| Jev, top confidence + catalog match | 16.11 | 40.88\* | 46.97 | 46.97 | 46.97 | 0.201 / 0.201 | 0.28 s |
| Embeddings + LR (`lr-50`, fold average) | 20.37\* | 31.33\* | 54.31 | 69.89 | 79.05 | 0.0003 | 0.30 s |

Reading:

- **Accuracy:** on in-scope tuning messages (cross-fitted, so each predicted by a model that never saw it) the classifier picks the right queue 92.9% of the time, against 84.2% for `gpt-4o-mini`, 85.6% for Jev and 86.7% for Luna; on the test set, 93.0%.
- **Cost and speed:** more than a hundred times cheaper per message than cached Luna, and about as fast as Jev and the Decisions API.
- **Automation without examples of "none of these" (`lr-50`):** behind the adapted Luna prompt at 2% (31% against 43%), level with Haiku at 1% (with misroutes just over the limit, 1.04%) and ahead of every LLM at 5%, 10% and 15%.
- **With examples of "none of these" (`lr-51`):** about 60% automated at 1% and 2%, far above every LLM. The test's out-of-scope messages come from topics it trained on, so this is the optimistic case.
- **Calibration:** the scores are smooth, so a threshold can sit anywhere. The method fixed in advance still overshot: with one model retrained on all items after the thresholds were set, test misroutes went over the limit at every level for `lr-50` (2.53% at the 2% limit). Using the same five models for the test as for the thresholds brought them within the limit from 2% up. A threshold belongs to the exact model it was fitted on, the same lesson as the LLM swap.
