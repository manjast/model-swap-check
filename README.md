# model-swap-check

Can a production LLM feature move to a new model without getting worse? This repository answers that for one realistic feature, a support-message router built on `gpt-4o-mini`, which OpenAI removes from its API on 2027-01-14. Old and new models see the same messages; acceptance rules are frozen before the test runs; every decision can be replayed from the recorded responses.

**Status:** specification phase. No model has been called yet.

- [Specification](docs/spec.md)
- [Test plan](docs/test-plan.md)
- [Power analysis](analysis/power.py): how often the acceptance rules certify an equally good candidate

Data: [Banking77](https://github.com/PolyAI-LDN/task-specific-datasets) (Casanueva et al., 2020), CC BY 4.0, with the in-scope intents of Banking77-OOS (Zhang et al., 2022).
