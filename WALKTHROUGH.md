# Walkthrough

A reading path through the repository, then the design questions a reviewer is likely to ask, with the answer and where to check it.

## Reading path (about 30 minutes)

1. **[README](README.md)**: the answer table and the three lessons.
2. **[Specification](docs/spec.md)**, in this order:
   - §1: the decisions under test and the deployment assumption (an asynchronous ticket queue, so latency is reported, never gated);
   - §5: the two metrics, W (share of all messages auto-routed to the wrong queue) and A (share auto-routed);
   - §6: how each configuration gets its own threshold from development data;
   - §7.1–§7.4: the gates, verdicts and statistics;
   - §7.8–§7.10: the three amendments, and what each one could and could not change.
3. **One decision record**, e.g. [`decisions/D-A1.md`](decisions/D-A1.md): gate table, slices, the naive model-ID swap, the newly wrong auto-routes, cost and the stated limitation.
4. **[Test-run summary](docs/cert.md)**: runs, spend, verdicts, the amendments' results and the cost and speed table.
5. **Code**, following one test run end to end:
   - [`providers/`](src/swapcheck/providers/): pure adapters, one per API; they build request bodies and parse responses, with no I/O;
   - [`http.py`](src/swapcheck/http.py): one request with the retry policy and per-attempt spend admission;
   - [`runner.py`](src/swapcheck/runner.py): warm-ups, fan-out under concurrency and rate limits, append-only rows, resume, the in-run budget stop;
   - [`freeze.py`](src/swapcheck/freeze.py) and [`manifest.py`](src/swapcheck/manifest.py): a test run starts only on the frozen code, once per configuration;
   - [`outcomes.py`](src/swapcheck/outcomes.py), [`calibrate.py`](src/swapcheck/calibrate.py), [`stats.py`](src/swapcheck/stats.py) and [`decide.py`](src/swapcheck/decide.py): routing outcomes, thresholds, paired bounds and the decision records;
   - [`jev_policy.py`](src/swapcheck/jev_policy.py) and [`risk_limits.py`](src/swapcheck/risk_limits.py): amendments 2 and 3.
6. **[Test plan](docs/test-plan.md)**: every test ID maps to a spec section; [`tests/test_golden.py`](tests/test_golden.py) replays committed synthetic runs into decision records byte for byte, offline.

## Questions and answers

**Why W and A instead of accuracy?**
A router's risk is a wrong automatic route, and its value is the work it takes off people. Accuracy mixes the two and ignores the threshold. Top-1 accuracy is still reported as a diagnostic (spec §5).

**Why does each model get its own threshold?**
Confidence values are not comparable between models. Keeping the incumbent's threshold of 0.95 and changing only the model ID to Luna took W from 0.00% to 3.91% on the test set. Each LLM decision record shows this naive swap next to the fitted comparison (spec §7.5).

**Why freeze the rules before the test run?**
With five candidates, several thresholds and seven slices, there are enough choices to make almost any candidate look good after the fact. The specification, the margins and the thresholds are fixed first; the contract is tagged in git; the runner refuses a test run whose code or inputs differ from the tagged commit and refuses a second test run of the same configuration under that tag (spec §7.7, §9.5).

**What happens when a frozen rule turns out to be uninformative?**
It stays, and its limitation is written into every decision record. The automation gate compared candidates with the incumbent's 2.05% and could not fail; this was seen after the incumbent's development run. New analyses were added as declared amendments: the text is committed before the numbers it reports are computed, and each has its own tagged contract and CI replay. Amendment 2 failed on the test set (W 2.03% against a 2% limit) and is published as it came out.

**Which statistics, and why?**
Gates compare candidate and incumbent on the same messages, so the bounds are one-sided Tango score bounds for paired proportions. They were chosen by simulation at the planned slice sizes, where a percentile bootstrap and the normal approximation released an at-margin candidate too often (spec §7.1). Single proportions in the descriptive analyses use Wilson score intervals. The slice gate passes only if every slice passes its one-sided 95% upper bound; only its FAIL side uses a Bonferroni correction over seven slices. An intent-cluster bootstrap is reported as a sensitivity check.

**How big is run-to-run noise?**
The incumbent ran twice on 3,080 test messages. 0.29 pp of routing outcomes flipped, and the repeat passed the error-rate gates against the first run (spec §7.6).

**Why plain HTTP instead of the vendor SDKs?**
One retry policy for every provider (the SDKs retry on their own), request bodies that tests can snapshot exactly, and the raw response JSON in the records (spec §12).

**How is spending kept under the cap?**
Every HTTP attempt, retries and warm-ups included, must be admitted before it starts: spent so far, plus reservations of attempts in flight, plus its own worst-case cost must stay under the provider's cap minus $0.50. Spend is computed from the persisted item and warm-up records, retries included, so a later run sees what earlier runs cost; a hard kill can still lose the charges of the requests in flight at that moment (spec §9.5).

**Can I trust the decision records were not edited by hand?**
CI regenerates every record from the recorded responses and fails if one byte differs. The replay commands are in the README; they need no API key.

**Why is cost reported per message rather than per token?**
A router sends the same few thousand tokens of queue descriptions with every message. Whether that block is cached decides the bill: per message, Luna with caching costs $0.039 per 1,000, and Jev, whose input price per token is lower but which has no cache, $0.146 (spec §11, `analysis/cert_speed.py`).

**What would you do differently?**
Look at the incumbent's confidence distribution in the pilot. Of 100 pilot messages, `gpt-4o-mini` gave 74 a confidence of 0.90 and one a confidence of 0.95. That was enough to see that the automation gate could not fail, while changing it was still cheap.

**How would this transfer to my own classifier?**
Replace the data loader and the catalog in `config/`, keep the runner, the cost model and the decision code, and run the same phases: pilot, development runs and threshold fitting, freeze, one test run per configuration. The specific numbers here are for clean, single-turn English Banking77 messages and one prompt; they will not transfer.
