# model-swap-check

Your LLM classifier has to move. OpenAI removes `gpt-4o-mini` from its API on 2027-01-14, and a support-message router built on it needs a new home. This repository decides, with data instead of guesses, between four ways out:

- OpenAI's named successor, `gpt-6-luna`;
- a rival LLM, Anthropic's `claude-haiku-5-5`;
- a new class of model: TypeSafe's Jev, a decision model that returns calibrated probabilities instead of text;
- OpenAI's answer to that class: the Decisions API, which serves `gpt-6-luna` behind a decision interface.

Every model is scored against ground-truth labels on the same messages. Reasoning effort and request design are selected on development data. Acceptance rules are frozen before the test runs, and every decision can be replayed from the recorded responses.

**Status:** M4 done: all 13 development runs are in, the incumbent passed its competence check and the acceptance contract is frozen in `contracts/contract-v1.yaml`. The incumbent's stated confidence turned out to support the registered 2% risk limit only at 1.83% automation, so spec amendment 1 added a descriptive analysis at that limit before any candidate was run. No test-set (`cert`) run yet.

- [Specification](docs/spec.md)
- [Test plan](docs/test-plan.md)
- [Pilot results](docs/pilot.md), reproduced by `python analysis/pilot.py`
- [Development runs and contract freeze](docs/dev.md), reproduced by `python analysis/dev.py freeze`
- [Power analysis](analysis/power.py): how often the acceptance rules certify an equally good candidate
- [Incumbent prompt](prompts/incumbent-v1.md), its [Jev translation](prompts/jev-v1.yaml) and its [Decisions API translation](prompts/decisions-v1.yaml)

```sh
uv venv && uv pip install -e '.[dev]'
.venv/bin/swapcheck data     # download Banking77 at a pinned commit, verify SHA-256, write the splits
.venv/bin/swapcheck prompt   # prompt size and hash; regenerate the Jev and Decisions translations
.venv/bin/pytest
```

Data: [Banking77](https://github.com/PolyAI-LDN/task-specific-datasets) (Casanueva et al., 2020), CC BY 4.0, with the in-scope intents of Banking77-OOS (Zhang et al., 2022).
