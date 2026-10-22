# model-swap-check working rules

Read `README.md`, `docs/spec.md`, `docs/test-plan.md`, and the relevant decision/config documents before substantive work. The specification and test plan are the contract; do not implement a behavior that they do not define.

## Spec-first workflow

For a non-trivial change, before implementation record or update:

1. the requirement and non-goals;
2. the design and provider/API boundary;
3. acceptance cases and test IDs in `docs/test-plan.md`;
4. budget, retry, privacy, provenance and failure-state implications;
5. the smallest vertical implementation slices.

Challenge the design independently before coding. Check that the test oracle is independent of the implementation and that a plausible defect would fail a test. Keep development, calibration, held-out evaluation, live spend and release evidence separate.

## Implementation

- Preserve the existing Python/uv/pytest/ruff/mypy conventions and frozen contracts.
- Keep provider calls behind explicit typed interfaces; keep deterministic parsing, metrics, gates, retries and cost accounting in ordinary code.
- Keep secrets in `.env` or approved runtime configuration; never read or commit secret values or raw provider responses containing them.
- Do not add a provider, dependency, model, threshold, dataset, hosted service or API behavior without a documented decision and authorization.
- Use concise comments only for protocol constraints, invariants or non-obvious provider behavior.

## Verification and Git

Run the targeted test first, then the required `uv run ruff check .`, `uv run mypy src`, `uv run pytest -q`, and the relevant CLI smoke. Do not report a live or paid run as complete without its recorded budget, retry, provenance and artifact checks.

Use a feature branch and PR. This repository permits squash merges only where its current workflow authorizes them; do not apply the two-parent merge rule from the other governed repositories here. Never push or merge without explicit user authorization.
