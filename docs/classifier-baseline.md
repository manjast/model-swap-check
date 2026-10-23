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

Added after the fit.
