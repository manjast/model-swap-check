# Fine-tuned encoder baselines (post hoc)

Written on 2026-10-23, after the [classifier baseline](classifier-baseline.md) was published and before any fine-tuned model was trained. Descriptive: no registered decision, threshold, contract or LLM number changes.

## Question

Tine Kolenik asked under the LinkedIn post how a fine-tuned ModernBERT or SetFit compares. The classifier baseline froze the embeddings and trained only a logistic regression on top; these two baselines also train the encoder itself on the labelled messages. Same split, same misroute limits (amendment 3, spec §7.10), same thresholds rule.

## Method, fixed before training

- **ModernBERT:** `answerdotai/ModernBERT-base` at revision `8949b909`, fully fine-tuned with a classification head (Transformers `AutoModelForSequenceClassification`). AdamW at learning rate 5e-5 with weight decay 0.01, batch 32, 10 epochs, linear decay after a 10% warm-up, up to 128 tokens per message (more than the longest message, so nothing is cut), 32-bit floats. Confidence = the top class's softmax probability.
- **SetFit:** SetFit 1.2.0 with `sentence-transformers/paraphrase-mpnet-base-v2` at revision `6cc9279c`: one epoch of contrastive training on sentence pairs (20 iterations, the SetFit paper's setting: 40 pairs per training message; batch 16), then a logistic-regression head with up to 5,000 iterations (the default 100 stopped before convergence in a test run with a tiny random model). Confidence = the head's top probability.
- **No tuning:** one recipe per model, the values above, seed 20261023. Nothing is changed after seeing a result.
- **Training data and variants:** as in the classifier baseline, the 250 `examples` and the 3,075 `dev` messages with their labels. `-50` trains on the 50 queues only (the fairer match for the LLMs); `-51` adds a "none of these" class from the `dev` out-of-scope messages (optimistic, as the test's out-of-scope messages come from the same 27 Banking77 intents).
- **Thresholds and test predictions:** the classifier baseline's five folds (same stratification and seed), `examples` always in training. Each `dev` message is predicted by the fold model that never saw it; at each limit (1, 2, 5, 10 and 15%) τ is the smallest threshold with weighted `dev` W at or below the limit (`swapcheck.calibrate.fit_candidate`). Test probabilities are the mean of the same five fold models, the method the classifier baseline needed to stay within the limits; no model is retrained on everything.
- **Reported:** automation and misroutes on the 9,758 `cert` messages at each limit, with the one-sided 95% Wilson upper bound of W against the limit; top pick right on in-scope `dev` (cross-fitted) and `cert` messages; training minutes per fold; latency as the median of 100 single-message predictions on the training machine. Local latency has no network round trip, so it is not directly comparable to the API calls from Belgrade.
- **Machine:** Google Colab, free tier, T4 GPU (`analysis/finetune_colab.ipynb`). The run record holds the device, GPU name, thread count, package versions and git commit; Colab's own PyTorch is kept, the other packages are pinned. Results on another machine can differ slightly in the last digits.
- **Order:** `modernbert-50` first, then `modernbert-51`, `setfit-50` and `setfit-51`. Each runs to the end once started; a stopped run resumes at the next fold.

Committed: the text-free predictions (item ID, predicted intent, its probability) and `fit.json` per model. Each fold's probabilities stay in the git-ignored `data/finetune/` until all five folds are done.

`python analysis/finetune_baseline.py report` prints the results from the committed predictions, next to the classifier baseline's fold-average rows; nothing else is reported.

## How to run

On Google Colab: open [`analysis/finetune_colab.ipynb`](../analysis/finetune_colab.ipynb) in Colab, pick a T4 GPU and run all cells. Finished folds are kept on Google Drive, so after a disconnect running all cells again continues at the next fold.

On your own machine, Python 3.12 or newer and [uv](https://docs.astral.sh/uv/):

```sh
git clone https://github.com/manjast/model-swap-check && cd model-swap-check
uv venv
uv pip install -e '.[finetune]'   # Linux without a GPU, first: uv pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
.venv/bin/swapcheck data          # download Banking77 at a pinned commit, verify SHA-256, write the splits
.venv/bin/python analysis/finetune_baseline.py train modernbert 50
```

On Windows, `.venv\Scripts\` replaces `.venv/bin/`. The first run downloads the model (599 MB for ModernBERT, 438 MB for the SetFit encoder). Progress lines show the estimated minutes left in each fold. Without a GPU, expect hours per model.

## Results

Run on Google Colab (free tier, Tesla T4) on 2026-10-23 and 24 from the merged method commit `3f19d43`, each of the four once, all five folds to the end. Colab's own PyTorch 2.11.0 was used in place of the pinned 2.14.1, as the method says; the other packages match `pyproject.toml`. Output of `python analysis/finetune_baseline.py report`, automation (misroutes) in % of the 9,758 test messages:

| Variant | 1% | 2% | 5% | 10% | 15% | Top pick right, tuning / test | Training per fold | Latency p50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `lr-50` (embeddings + LR) | 20.37 (1.04)\* | 31.33 (1.94)\* | 54.31 (4.41) | 69.89 (8.87) | 79.05 (14.29) | 92.9% / 92.9% | - | - |
| `lr-51` (embeddings + LR) | 56.59 (1.08)\* | 62.11 (1.79)\* | 70.93 (5.12)\* | 70.93 (5.12) | 70.93 (5.12) | 89.8% / 89.7% | - | - |
| `modernbert-50` | 18.38 (0.91)\* | 32.80 (1.77)\* | 49.08 (3.47) | 62.53 (6.63) | 71.03 (10.75) | 88.9% / 90.3% | 4.1 min | 16 ms |
| `modernbert-51` | 46.75 (0.49) | 53.23 (0.97) | 64.48 (3.16) | 70.49 (6.23) | 70.49 (6.23) | 85.5% / 87.6% | 5.7 min | 16 ms |
| `setfit-50` | 8.35 (0.68) | 16.63 (1.98)\* | 33.52 (3.98) | 50.72 (7.05) | 64.04 (10.02) | 90.2% / 90.5% | 20.7 min | 11 ms |
| `setfit-51` | 49.81 (0.92)\* | 55.95 (1.51) | 65.68 (3.80) | 72.07 (7.33) | 72.07 (7.33) | 87.8% / 88.2% | 26.5 min | 12 ms |

Training time and single-message latency measured on: cuda (Tesla T4) on Linux x86_64, 1 CPU thread.

\* marks a one-sided 95% Wilson upper bound of W at or above the limit. The `lr` rows are the classifier baseline's fold-average rows.

Reading:

- **Accuracy:** training the whole encoder did not beat the logistic regression on frozen embeddings. On in-scope tuning messages ModernBERT picks the right queue 88.9% of the time and SetFit 90.2%, against 92.9% for the logistic regression; all three are above the LLMs (84.2% for `gpt-4o-mini`, 85.6% for Jev, 86.7% for Luna).
- **Without examples of "none of these" (`-50`):** ModernBERT is level with the logistic regression at the strict limits (18% against 20% at 1%, 33% against 31% at 2%) and behind from 5% up. It stays behind the adapted Luna prompt at 2% (43%) and just behind Haiku at 1% (20%). SetFit automates far less at the strict limits (8% at 1%, 17% at 2%).
- **With examples of "none of these" (`-51`):** both automate about half of all messages at 1% and 2%, less than the logistic regression (57% and 62%) and with misroutes further below the limit. The same optimistic case as `lr-51`: the test's out-of-scope messages come from topics seen in training.
- **Calibration:** with test probabilities averaged over the five fold models, measured misroutes stayed within the limit at every level for all four, including 1%, where `lr-50` landed at 1.04%.
- **Speed and cost:** no API cost. Training takes 4 to 6 minutes per fold for ModernBERT and 21 to 27 for SetFit on a free T4; a prediction takes 11 to 16 ms on that GPU. This latency has no network round trip, so it is not comparable to the API calls from Belgrade (0.30 s for the embedding call, 0.28 to 1.26 s for the LLMs); running the encoder means hosting a model.
- **What this does not show:** each model ran with one recipe fixed in advance. A learning-rate or epoch sweep could move ModernBERT's numbers; this baseline answers what a first, untuned fine-tune gives.
