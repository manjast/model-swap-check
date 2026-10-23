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

Added after training.
