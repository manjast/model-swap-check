# model-swap-check

Your LLM classifier has to move. OpenAI removes `gpt-4o-mini` from its API on 2027-01-14, and a support-message router built on it needs a new home. This repository decides, with data instead of guesses, between four ways out:

- OpenAI's named successor, `gpt-6-luna`;
- a rival LLM, Anthropic's `claude-haiku-5-5`;
- a new class of model: TypeSafe's Jev, a decision model that returns calibrated probabilities instead of text;
- OpenAI's answer to that class: the Decisions API, which serves `gpt-6-luna` behind a decision interface.

Every model is scored against ground-truth labels on the same messages. Reasoning effort and request design are selected on development data. Acceptance rules are frozen before the test runs, and every decision can be replayed from the recorded responses.

**Status:** M5 done: the seven planned test-set (`cert` and `aa`) runs are in, and the decision records are in [`decisions/`](decisions/) ([summary](docs/cert.md)). All five run decisions are SHIP. The automation gate (G3) could not fail, because the incumbent automates only 2% at its threshold (spec amendment 1); the error-rate and validity gates were live and passed. The descriptive analysis at the 2% risk limit shows every LLM candidate automating 25–43% of traffic within that limit. Jev's 0% there comes from its coarse confidence. Amendment 2 shows it automating about 41–43% at its top confidence, with wrong routes at 2.0–2.2%, just above the limit. Amendment 3 repeats the comparison at limits from 1% to 15%. The incumbent automates 2% at every limit below 14%. Among candidates whose wrong-route rate stays clearly within the limit, the best automates 20% at 1%, 43% at 2%, 54% at 5% and 66% at 10%, and which candidate is best depends on the limit. Write-up (M6) next.

- [Specification](docs/spec.md)
- [Test plan](docs/test-plan.md)
- [Pilot results](docs/pilot.md), reproduced by `python analysis/pilot.py`
- [Development runs and contract freeze](docs/dev.md), reproduced by `python analysis/dev.py freeze`
- [Test-set runs and decisions](docs/cert.md); cost and speed reproduced by `python analysis/cert_speed.py`
- [Power analysis](analysis/power.py): how often the acceptance rules certify an equally good candidate
- [Incumbent prompt](prompts/incumbent-v1.md), its [Jev translation](prompts/jev-v1.yaml) and its [Decisions API translation](prompts/decisions-v1.yaml)

```sh
uv venv && uv pip install -e '.[dev]'
.venv/bin/swapcheck data     # download Banking77 at a pinned commit, verify SHA-256, write the splits
.venv/bin/swapcheck prompt   # prompt size and hash; regenerate the Jev and Decisions translations
.venv/bin/pytest
```

Data: [Banking77](https://github.com/PolyAI-LDN/task-specific-datasets) (Casanueva et al., 2020), CC BY 4.0, with the in-scope intents of Banking77-OOS (Zhang et al., 2022).
