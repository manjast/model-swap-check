# Pilot (M3)

**Date:** 2026-10-22, 09:15–09:21 UTC. All 14 pilot configurations of spec §9.1 were run on the 100 `pilot` items, from this machine. Runs were sequential within a provider and parallel across the three providers. The run records are in `runs/*-pilot-*`.

**Code:** the runs started from `34b9eb0` (recorded in `run.json`), with the uncommitted additions of this milestone: per-attempt rate-limit/timing headers and `run --capture-dir`. Neither changes a request.

**Spend:** OpenAI $0.101, Anthropic $0.030, TypeSafe $0.069, in total $0.20.

- Outside `runs/`: three Claude calls on the warm-up message "Hello" measured the structured-output overhead, ≈ $0.001.
- The text of a pilot item appears in none of the 1,423 captured responses and none of the run records (substring check over all 100 texts).

**Reproduce:** `python analysis/pilot.py` prints every table below from `runs/`. Numbers here are rounded.

## Acceptance (test plan §5)

| ID | Result |
|---|---|
| T-L1 | Met. 100/100 `ok` for every configuration; 0 invalid outputs, 0 API errors, 0 HTTP 429. 15 items needed a retry: `luna-low` 5 timeouts, `haiku55-low` 2 timeouts, `haiku55-off` 8 connection errors. All succeeded on the second attempt. |
| T-L2 | Met. After the warm-up, 100/100 calls read the cache for every Luna and Haiku 5.5 configuration (≥ 90% expected). `inc` (implicit, best effort): 98/100. |
| T-L3 | Measured. The explicit mode is kept for `cert` (see Cache). |
| T-L4 | Met. The cost model and pre-`dev` gate are computed from the pilot (see Cost and budget). Spec §11's planning table is updated. |
| T-L5 | Met, except the TypeSafe account limit, which is not readable through the API (see Rate limits). |
| T-L6 | Met. Ten real responses are in `tests/fixtures/responses/pilot-*.json` and drive T-R2, including one `jev-c51`, one `jev-noul` and one `luna-dec` response, plus two warm-ups with cache writes. Each keeps its request ID. Headers are limited to request IDs, rate limits, timing and content type. gitleaks is clean. |
| T-L7 | Met (see Latency). |
| T-L8 | Met. `jev-c51` 6%, `jev-noul` 4%, `luna-dec` 14% (see Option order). |
| T-L9 | Met. Reasoning tokens are far below the planning assumption (see Cost and budget). The §9.5 projection has been updated before any `dev` run. |

## Open items (spec §14)

| Item | Answer |
|---|---|
| `gpt-6-luna` accepts `temperature: 0` at effort `none` | Yes. Every `luna-none` call succeeded, and the response echoes `temperature: 0.0`. At `low`, where it is omitted, the response shows the default 1.0. |
| Structured outputs with the 51-value enum on all configurations | Yes. 800 LLM calls (8 configurations × 100) returned valid enum values, 0 invalid. The Jev and Decisions interfaces returned only listed values. |
| `gpt-4o-mini` callable from this account | Yes. It returned `gpt-4o-mini-2024-07-18`. |
| Luna explicit vs implicit cache mode | Equal billed cost; explicit is kept. See Cache. |
| Token overhead of Claude's injected structured-output instructions | **882 input tokens per call.** The same `haiku55-off` request on "Hello" counted 4,377 input tokens with `output_config.format` and 3,495 without; a repeat with the format gave 4,377 again. The overhead sits in the cached prefix (4,368 tokens), so steady traffic pays it at the cache-read price. |
| Reasoning/thinking tokens per item at `low` and `medium` | Mean / p90: `luna-low` 8 / 42, `luna-medium` 73 / 168, `haiku55-low` 73 / 220, `haiku55-medium` 114 / 269. |
| Account rate limits | OpenAI 5,000 requests and 2,000,000 tokens per minute, the same for `gpt-4o-mini`, Luna Responses and Luna Decisions. Anthropic `claude-haiku-5-5`: 1,000 requests, 500,000 input tokens and 80,000 output tokens per minute. TypeSafe returns no rate-limit header, and its docs point to the console, which has not been read. `config/limits.yaml` is updated (see Rate limits). |
| `openai-processing-ms` on Responses calls | Present on 100% of Responses and Decisions calls. |
| Jev option-order sensitivity | `jev-c51` 6/100 (above 5%: stated as a limitation in D-J if c51 is selected); `jev-noul` 4/100. |
| Jev latency from this machine | p50 0.9–3.3 s, p95 3.7–7.8 s. That is well above TypeSafe's "about 100 ms", which is measured at TypeSafe's own location; no server timing header exists to separate the network. |
| `luna-dec` option-order sensitivity | **14/100.** Above 5%, so it is stated as a limitation in the D-O record. |
| Decisions `confidence` as a function of the probabilities | `round((p_max − 1/n) / (1 − 1/n), 2)` with n = 51. All 200 calls agree within the 2-decimal rounding (max \|error\| 0.005); `p_max` itself misses by up to 0.02. Jev follows the same function (n = 51 for c51, 50 for the noul intent question). |
| Decisions API: `cached_tokens`, `x-request-id`, rate-limit headers, model ID | The `cached_tokens` field is present and always 0, with no warm-ups. `x-request-id` and the `x-ratelimit-*` headers are present. The returned model is `gpt-6-luna`. |
| `luna-dec` latency from this machine | p50 2.1 s / 1.5 s (normal / reversed run), against 2.2 s for `luna-none`. The server time (`openai-processing-ms`) p50 is 188 ms against 848 ms, about 4.5× faster. At concurrency 16 from here, the wall-clock time is dominated by everything outside the server. |
| Anthropic API version `2023-06-01` | Accepted (all Anthropic calls succeeded); recorded in `run.json`. |

## Cache

| Configuration | Calls with cache read | Read tokens | Write tokens (incl. warm-ups) | Billed, 100 items |
|---|---|---|---|---|
| `inc` | 98/100 | 232,192 | 0 | $0.0297 |
| `luna-none` (explicit) | 100/100 | 264,800 | 0 | $0.0039 |
| `luna-none-implicit` | 100/100 | 264,800 | 4,263 | $0.0043 |
| `luna-low` | 100/100 | 264,800 | 2,648 | $0.0088 |
| `luna-medium` | 100/100 | 264,800 | 2,648 | $0.0080 |
| `haiku55-off` | 100/100 | 436,800 | 4,368 | $0.0064 |
| `haiku55-low` | 100/100 | 436,900 | 4,369 | $0.0119 |
| `haiku55-medium` | 100/100 | 436,900 | 0 | $0.0116 |

**Explicit vs implicit (T-L3).** The implicit run went first, at 09:16. It wrote the prefix in its warm-up (2,653 tokens) and then about 16 tokens per call; those per-call writes are billed at the write price.

The explicit `luna-none` run went last, at 09:20. It wrote nothing, because `luna-low` and `luna-medium` had already written the same explicit prefix minutes earlier, so its $0.0039 lacks one warm-up write. With that write added (2,648 tokens at $0.125 per million, $0.0003), it comes to $0.0042, against $0.0043 implicit.

The two modes cost the same within $0.0001 per 100 items. The explicit mode stays for `cert` (spec §4) because the breakpoint is deterministic and there are no per-call writes. Zero writes in `haiku55-medium` and `luna-none` show the same effect: a run inside the TTL of an earlier run with the same prefix starts warm.

## Cost and budget

Per configuration, per 1,000 messages; the token columns are per item, mean / p90.

| Configuration | Uncached in | Cache read | Output | Reasoning | $/1k mean | $/1k p90 | Steady | Sparse |
|---|---|---|---|---|---|---|---|---|
| `inc` | 347 / 619 | 2,322 / 2,432 | 15 / 17 | 0 | 0.235 | 0.255 | 0.227 | 0.409 |
| `luna-none` | 19 / 32 | 2,648 | 21 / 23 | 0 | 0.039 | 0.041 | 0.039 | 0.277 |
| `luna-low` | 172 / 35 | 2,648 | 81 / 79 | 8 / 42 | 0.084 | 0.069 | 0.043 | 0.282 |
| `luna-medium` | 19 / 32 | 2,648 | 96 / 190 | 73 / 168 | 0.076 | 0.124 | 0.076 | 0.315 |
| `haiku55-off` | 23 / 37 | 4,368 | 25 / 30 | 0 | 0.058 | 0.061 | 0.058 | 0.451 |
| `haiku55-low` | 104 / 39 | 4,369 | 119 / 251 | 73 / 220 | 0.114 | 0.171 | 0.095 | 0.488 |
| `haiku55-medium` | 23 / 37 | 4,369 | 139 / 292 | 114 / 269 | 0.116 | 0.192 | 0.116 | 0.509 |
| `jev-c51` | 3,465 / 3,479 | 0 | 561 / 563 | – | 0.146 | 0.146 | 0.146 | 0.146 |
| `jev-noul` | 4,782 / 4,796 | 0 | 570 / 572 | – | 0.201 | 0.201 | 0.201 | 0.201 |
| `luna-dec` | 2,318 / 2,331 | 0 | 0 | 0 | 0.232 | 0.233 | 0.232 | 0.232 |

- **Timeout charges:** the five `luna-low` timeouts are charged per §9.5 (full uncached input plus max output), so its mean exceeds its p90.
- **Prices:** Jev output is free, and `luna-dec` bills input only.
- **Pre-`dev` gate (§9.5):** at the pilot p90, every provider fits with every `dev` run, so nothing is skipped.

| Provider | Spent | Dev runs | Spent + dev + cert without R | + R = low | + R = medium | Cap − $0.50 |
|---|---|---|---|---|---|---|
| OpenAI | $0.10 | $2.60 | $9.04 | + $0.67 | + $1.21 | $14.50 |
| Anthropic | $0.03 | $1.30 | $1.93 | + $1.67 | + $1.87 | $9.50 |
| TypeSafe | $0.07 | $1.07 | $3.10 | – | – | $4.50 |

`luna-dec` is the largest OpenAI item after the incumbent, at ≈ $3.00 over `dev` and `cert`, because the Decisions API reports no cache reads.

## Latency

Final attempt, wall clock from this machine at concurrency 16, in ms. These are indicative only.

| Configuration | p50 | p95 | Server p50 (`openai-processing-ms`) |
|---|---|---|---|
| `inc` | 1,775 | 3,762 | 752 |
| `luna-none` | 2,185 | 5,232 | 848 |
| `luna-none-implicit` | 3,840 | 8,109 | 880 |
| `luna-low` | 2,804 | 6,116 | 872 |
| `luna-medium` | 3,746 | 8,298 | 1,569 |
| `luna-dec` | 2,110 | 4,390 | 188 |
| `luna-dec-reversed` | 1,453 | 8,113 | 192 |
| `haiku55-off` | 3,068 | 8,188 | – |
| `haiku55-low` | 3,502 | 8,927 | – |
| `haiku55-medium` | 3,690 | 9,505 | – |
| `jev-c51` | 3,318 | 7,837 | – |
| `jev-c51-reversed` | 912 | 3,672 | – |
| `jev-noul` | 2,325 | 6,782 | – |
| `jev-noul-reversed` | 2,744 | 6,059 | – |

All Luna and Haiku calls after the warm-up read the cache, so the "with cache read" split equals the overall figure. For `inc`, the 98 calls with a cache read had a p50 of 1,775 ms; the two without one, 2,186 ms. Jev and `luna-dec` report no cache reads.

## Option order

| Interface | Items `ok` in both orders | Choice changed | Share |
|---|---|---|---|
| `jev-c51` | 100 | 6 | 6% |
| `jev-noul` | 100 | 4 | 4% |
| `luna-dec` | 100 | 14 | 14% |

These counts go into the contract (`order_sensitivity`, spec §7.7). `decide` then writes them into the D-J and D-O records, adding the limitation when more than 5% of the choices changed.

## Rate limits

`config/limits.yaml` now holds 80% of the account limits read from the headers: OpenAI 4,000 requests and 1,600,000 tokens per minute; Anthropic 800 requests and 400,000 tokens per minute.

The limiter's Anthropic token estimate counts the whole prompt, but Anthropic counts only uncached input and cache writes toward its input limit. The limit therefore binds at about 170 requests per minute. That keeps input use far below the account limit, and output at the pilot's `medium` p90 at about 50,000 tokens per minute, under 80% of the 80,000 output limit.

TypeSafe keeps 5 requests and 20,000 tokens per second, which produced no 429 in the pilot; its console value is still to be entered.
