# Latency study

Study: `latency-20261022T194349Z`

UTC window: 2026-10-22T19:43:49Z to 2026-10-22T20:01:24Z

Client: Belgrade, Serbia; home Wi-Fi, stable connection with good signal

Git commit: `c133c08ed8dffd8eb446368ec05fccabd2f4ce67`

Rounds: 200

All timings are milliseconds, rounded to whole ms; quantiles use method=higher.
Warm-ups are excluded. Errors are counted, not timed. No routing outcomes are analysed.

| Configuration | Successful final attempts | Retries | Errors | Total p50 / p95 | Headers p50 / p95 | Server p50 / p95 | Headers minus server p50 / p95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| inc | 200 | 0 | 0 | 1015 / 1624 | 1004 / 1618 | 721 / 1335 | 295 / 473 |
| luna-none | 200 | 0 | 0 | 1259 / 1690 | 1246 / 1679 | 958 / 1311 | 296 / 425 |
| luna-dec | 200 | 0 | 0 | 280 / 598 | 271 / 587 | 80 / 388 | 136 / 216 |
| haiku55-off | 200 | 0 | 0 | 1250 / 2080 | 1241 / 2071 | n/a / n/a | n/a / n/a |
| jev-c51 | 200 | 0 | 0 | 282 / 345 | 273 / 338 | n/a / n/a | n/a / n/a |
| jev-noul | 200 | 0 | 0 | 284 / 397 | 274 / 383 | n/a / n/a | n/a / n/a |

| Host | TCP probe p50 / p95 | Probe errors | New connections | Connect p50 | TLS p50 |
|---|---:|---:|---:|---:|---:|
| api.anthropic.com | 76 / 102 | 0 | 35 | 76 | 23 |
| api.openai.com | 60 / 85 | 0 | 1 | 63 | 26 |
| api.typesafe.ai | 78 / 103 | 0 | 15 | 88 | 27 |
