# model-swap-check

Your LLM classifier has to move. OpenAI removes `gpt-4o-mini` from its API on 2027-01-14, and a support-message router built on it needs a new home. This repository decides, with data instead of guesses, between three ways out:

- OpenAI's named successor, `gpt-6-luna`;
- a rival LLM, Anthropic's `claude-haiku-5-5`;
- a new class of model: TypeSafe's Jev, a decision model that returns calibrated probabilities instead of text.

Every model is scored against ground-truth labels on the same messages. Reasoning effort and request design are selected on development data. Acceptance rules are frozen before the test runs, and every decision can be replayed from the recorded responses.

**Status:** specification phase. No model has been called yet.

- [Specification](docs/spec.md)
- [Test plan](docs/test-plan.md)
- [Power analysis](analysis/power.py): how often the acceptance rules certify an equally good candidate

Data: [Banking77](https://github.com/PolyAI-LDN/task-specific-datasets) (Casanueva et al., 2020), CC BY 4.0, with the in-scope intents of Banking77-OOS (Zhang et al., 2022).
