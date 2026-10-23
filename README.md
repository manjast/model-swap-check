# model-swap-check

OpenAI removes `gpt-4o-mini` from its API on 2027-01-14. This repository decides, with frozen rules and replayable evidence, what should replace it in a support-message router: a model reads a customer message, picks one of 50 team queues and states its confidence; above a threshold the message is routed automatically, below it a person decides.

Four ways out were tested on 9,758 Banking77 test messages:

- OpenAI's named successor, `gpt-6-luna` (Luna), with the incumbent prompt and with an adapted prompt;
- a rival LLM, Anthropic's `claude-haiku-5-5`;
- TypeSafe's Jev (`jev-1.13.0`), a decision model that returns probabilities instead of text;
- OpenAI's Decisions API, which serves Luna behind a decision interface.

## The answer

Share of all messages routed automatically while the share routed to the wrong queue (W) stays within the limit. Each model uses its own threshold per limit, fitted on development data and measured once on the test set.

| Configuration | W ≤ 1% | W ≤ 2% | W ≤ 5% | W ≤ 10% | W ≤ 15% | $ per 1,000, busy / quiet | Latency p50 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `gpt-4o-mini` (incumbent) | 2.05% | 2.05% | 2.05% | 2.05% | 72.37%\* | 0.218 / 0.410 | 1.02 s |
| Luna, incumbent prompt | 0.07% | 34.75% | 50.20% | 50.20% | 71.26% | 0.039 / 0.277 | 1.26 s |
| Luna, adapted prompt | 13.15% | **42.89%** | 42.89% | 63.86% | **73.16%** | 0.042 / 0.312 | – |
| Claude Haiku 5.5 | **19.98%** | 34.80% | 46.88% | 63.01% | 63.01% | 0.059 / 0.452 | 1.25 s |
| Decisions API (Luna) | 15.87% | 25.32% | 47.27%\* | 62.71%\* | 70.40% | 0.232 / 0.232 | 0.28 s |
| Jev, Choice confidence | 0.00% | 0.00% | **53.63%** | **66.19%** | 74.90%\* | 0.146 / 0.146 | 0.28 s |
| Jev, top confidence + catalog match | 16.11% | 40.88%\* | 46.97% | 46.97% | 46.97% | 0.201 / 0.201 | 0.28 s |

\* The one-sided 95% upper bound of W is not below the limit; for Jev's top-confidence rule at 2%, the measured W (2.03%) is above it too. **Bold**: the leader at that limit. Cost at list prices with the prompt prefix read from cache (busy router) or not (quiet router), from `analysis/cert_speed.py`. Latency: end to end from Belgrade, one request at a time ([`decisions/latency.md`](decisions/latency.md)). Sources: [`decisions/A3-limits.md`](decisions/A3-limits.md), summarised in [`docs/cert.md`](docs/cert.md).

- **The migration is free capacity.** Between a 2% and a 10% limit, every LLM replacement automates 25–64% of traffic; the incumbent automates 2%.
- **There is no best model.** Haiku leads at 1%, adapted Luna at 2% and 15%, Jev at 5% and 10%. Pick the misroute limit first; it picks the model.
- At 15% the race is over: the incumbent at threshold 0.90 already automates 72%.

## Three lessons

1. **A confidence threshold does not carry over to a new model.** Swapping only the model ID to Luna and keeping the incumbent's threshold of 0.95 takes W from 0.00% to 3.91%; with the adapted prompt, to 6.62%. No errors, every answer valid and confident. Refit the threshold per model.
2. **A calibrated confidence score can still be useless for a risk gate.** `gpt-4o-mini` speaks in steps of 0.05: at 0.95 it automates 2.05% with no misroutes, at 0.90 it automates 72.37% and misroutes 14.98% of all messages, and nothing lies between. Jev and the Decisions API round probabilities to 0.01, so answers pile up at 1.00: Jev routes 42.96% of messages there with W 2.22%, so under a 2% limit it automates nothing, although it picks the right queue more often than `gpt-4o-mini` (85.6% against 84.2%).
3. **Vendor headlines are not your bill or your latency.** Jev costs $0.042 per million input tokens, but a router resends a few thousand tokens of queue descriptions with every message. Luna caches them at a tenth of the price, Jev cannot: on a busy router Jev costs 3.7× Luna per message, on a quiet one about half, and Luna takes over at about two messages an hour. Jev is fast, 0.28 s against 1.0–1.3 s for the small LLMs, but that is 4×, not the advertised 193.6×. The Decisions API runs Luna with 12× less server time (0.08 against 0.96 s), costs 6× as much per message as cached Luna and automates less.

## What the registered decisions say

Five decisions were registered (D-A1 Luna, D-B1 Haiku, D-J Jev, D-O Decisions API, D-X adapted Luna); two reasoning variants were not run because they gave no gain on development data. All five are **SHIP**, and that says little: the acceptance gate on automation compared each candidate with the incumbent's 2.05%, so it could not fail. This was seen after the incumbent's development run and before any candidate run. The gate was kept, and the analysis at the 2% limit was added as amendment 1. Amendment 2 tested a rule that lets Jev automate at its top confidence; it landed at W 2.03%, just above 2%, and is reported as it came out. Amendment 3 is the five-limit table above. The verdicts and their limitation are in [`decisions/`](decisions/).

## How it was run

- **Rules before data.** The [specification](docs/spec.md) fixes the metrics, the threshold rule, the gates, the margins and the statistics before any test message is sent. Later analyses are declared amendments, each committed before its test numbers are computed; amendments 2 and 3 came after the first test results and are post hoc.
- **Frozen contracts.** Each analysis has a contract in [`contracts/`](contracts/), tagged in git (`contract-v1` to `contract-v3`). A test run starts only if the code, prompts and configuration equal the tagged commit, and under a given tag the runner refuses a second test run of the same configuration.
- **Replay.** Every decision record is written from the recorded responses in [`runs/`](runs/) by a command, and CI regenerates all of them on every change and compares them byte for byte.
- **Separate data.** Thresholds, reasoning effort, Jev's request design and the adapted prompt were chosen on 3,075 development messages. Each configuration ran once on the 9,758 test messages; the incumbent ran a second time on 3,080 of them to measure run-to-run noise (0.29 pp of outcomes flipped).
- **Fixed examples.** Each intent in the [incumbent prompt](prompts/incumbent-v1.md) carries one example message, drawn by a fixed hash rule from the intent's five `examples` messages (spec §2.3, §3.1) and never edited. Some are atypical: the example for `transfer_fee_charged` never mentions a transfer. Every configuration receives the same examples, and the adapted prompt could reword only instructions and descriptions (spec §8.3).
- **Cost.** About $14.50 in API calls in total, pilot and development runs included.

## Replay the decisions

```sh
uv venv && uv pip install -e '.[dev]'
.venv/bin/swapcheck data                      # download Banking77 at a pinned commit, verify SHA-256, write the splits
mkdir -p /tmp/replay
.venv/bin/swapcheck decide --output-dir /tmp/replay       # registered decisions (contract-v1)
.venv/bin/swapcheck jev-policy --output-dir /tmp/replay   # amendment 2 (contract-v2)
.venv/bin/swapcheck risk-limits --output-dir /tmp/replay  # amendment 3 (contract-v3)
.venv/bin/swapcheck latency-report --output-dir /tmp/replay  # latency study
diff -r decisions /tmp/replay && echo identical
.venv/bin/python analysis/cert_speed.py       # cost and speed table
.venv/bin/pytest
```

No API key is needed: the replay reads the recorded responses.

## Where to read next

- [`WALKTHROUGH.md`](WALKTHROUGH.md): a reading path through the repository and the design decisions behind it.
- [Specification](docs/spec.md) and [test plan](docs/test-plan.md).
- Results by phase: [pilot](docs/pilot.md) (`python analysis/pilot.py`), [development runs and contract freeze](docs/dev.md) (`python analysis/dev.py freeze`), [test runs and decisions](docs/cert.md) (`python analysis/cert_speed.py` for cost and speed).
- [Power analysis](analysis/power.py): how often the acceptance rules certify an equally good candidate.
- Prompts: [incumbent](prompts/incumbent-v1.md), its [Jev translation](prompts/jev-v1.yaml) and [Decisions API translation](prompts/decisions-v1.yaml), and the [adapted Luna prompt](prompts/luna-none-x.md).

## Not tested

Reasoning above `medium`; Claude Haiku 4.5; `gpt-4.1-mini`; Jev 1.14; multi-turn conversations; languages other than English; streaming; latency limits for live chat or voice (latency is reported, never gated); real production traffic. Banking77 is clean, single-turn English.

Data: [Banking77](https://github.com/PolyAI-LDN/task-specific-datasets) (Casanueva et al., 2020), CC BY 4.0, with the in-scope intents of Banking77-OOS (Zhang et al., 2022).

Code: MIT, see [LICENSE](LICENSE).
