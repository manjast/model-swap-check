# Examples ablation (post hoc, `dev` only)

Written on 2026-10-23, after every test result was published and before either run below. Descriptive: no registered decision, threshold, contract or test number changes, and this prompt never runs on `cert`.

## Question

Each catalog entry in `prompts/incumbent-v1.md` carries one example message, drawn by a fixed hash rule from the intent's five `examples` messages (spec §2.3, §3.1) and never edited. Six of the 50 read like a neighbouring intent:

| Intent | Problem with the current example | Replacement (`examples` item) | Why this one |
|---|---|---|---|
| `transfer_timing` | complains that money has not arrived, the topic of `balance_not_updated_after_bank_transfer` and `transfer_not_received_by_recipient` | `train-6679` | asks how long a transfer abroad takes; no complaint about missing money |
| `reverted_card_payment?` | an online purchase that fails, which reads as `declined_card_payment` | `train-6786` | the payment was taken, then returned, and the seller was not paid |
| `wrong_exchange_rate_for_cash_withdrawal` | asks about withdrawing abroad without fees; no exchange rate | `train-8355` | says the rate applied at the ATM was wrong |
| `transfer_fee_charged` | unexpected fees with no transfer mentioned | `train-7264` | asks about a fee on a money transfer |
| `cash_withdrawal_not_recognised` | unauthorised transactions with no cash withdrawal mentioned | `train-8931` | a cash withdrawal the customer does not recognise |
| `transaction_charged_twice` | mixes a duplicate card and a refund | `train-6406` | one purchase charged several times |

The six were named from reading the prompt, before any per-intent numbers were computed. The replacements were picked by reading the other four `examples` messages of each intent (the split the spec lets prompt authors read). Six more examples are vague rather than misleading and stay unchanged.

Does replacing the six change what `gpt-4o-mini` and Luna automate, or how often they pick the right queue?

## Runs

`prompts/examples-ablation.md` is `prompts/incumbent-v1.md` with exactly those six example lines replaced; instructions, descriptions and the other 44 examples are identical. `inc-ex` and `luna-none-ex` in `config/configurations.yaml` are `inc` and `luna-none` with that prompt, sending the same requests otherwise (T-R1 checks both). Each runs once on the 3,075 `dev` items, compared with the recorded `inc` and `luna-none` dev runs. Expected spend: about $0.85 from the OpenAI budget (the recorded dev runs cost $0.72 and $0.12).

## Comparisons, fixed before the runs

`python analysis/examples_ablation.py` prints all three; nothing else is reported.

1. **Automation at the 2% limit:** each configuration's own threshold on weighted `dev` (spec §7.8) and its automation (A) and misroutes (W) there, plus A and W at the fixed 0.95. Thresholds are fitted and measured on the same items, so both prompts look equally optimistic.
2. **Top-pick accuracy** on in-scope `dev` items answered in both runs, with an exact two-sided sign test on the items whose correctness changed.
3. **Per replaced example:** the share of the intent's own items picked right, and the wrong picks it attracts from other intents.

Scale for noise: a second `inc` run on 3,080 test items flipped 0.29 pp of outcomes (docs/cert.md), and each intent has 40 `dev` items, so one item is 2.5 points of its share.

## Results

Runs `inc-ex-dev-20261023T134523Z` ($0.66) and `luna-none-ex-dev-20261023T134636Z` ($0.12), both complete with no invalid outputs or API errors. Output of `python analysis/examples_ablation.py`:

| Configuration | τ at the 2% limit | A at the limit | W at the limit | A at 0.95 | W at 0.95 |
|---|---:|---:|---:|---:|---:|
| `inc` | 0.95 | 1.83% | 0.00% | 1.83% | 0.00% |
| `inc-ex` | 0.95 | 2.36% | 0.00% | 2.36% | 0.00% |
| `luna-none` | 0.99 | 34.55% | 1.14% | 49.58% | 3.72% |
| `luna-none-ex` | 0.99 | 35.53% | 1.25% | 48.98% | 3.30% |

`inc` → `inc-ex`: top pick right on 84.15% → 84.35% of 2000 in-scope items answered in both runs; 30 items improved, 26 got worse (sign test p = 0.69).
`luna-none` → `luna-none-ex`: top pick right on 86.65% → 87.10% of 2000 in-scope items answered in both runs; 25 items improved, 16 got worse (sign test p = 0.21).

Per replaced example: own items picked right / wrong picks attracted (all dev items, out of scope included).

| Intent | `inc` | `inc-ex` | `luna-none` | `luna-none-ex` |
|---|---:|---:|---:|---:|
| `cash_withdrawal_not_recognised` | 95.00% / 32 | 90.00% / 4 | 87.50% / 2 | 87.50% / 1 |
| `reverted_card_payment?` | 75.00% / 7 | 75.00% / 8 | 87.50% / 0 | 82.50% / 0 |
| `transaction_charged_twice` | 92.50% / 1 | 92.50% / 0 | 87.50% / 0 | 90.00% / 0 |
| `transfer_fee_charged` | 92.50% / 45 | 85.00% / 35 | 87.50% / 25 | 82.50% / 25 |
| `transfer_timing` | 95.00% / 60 | 95.00% / 53 | 95.00% / 52 | 95.00% / 41 |
| `wrong_exchange_rate_for_cash_withdrawal` | 77.50% / 3 | 77.50% / 4 | 75.00% / 0 | 72.50% / 0 |

Reading:

- **Little changes overall.** At the 2% limit automation rises by 0.53 points for `gpt-4o-mini` and 0.98 for Luna; at 0.95 Luna's misroutes fall from 3.72% to 3.30%. Accuracy moves by 0.20 and 0.45 points, and neither sign test separates the change from chance.
- **Single examples do pull answers.** With its new example, `cash_withdrawal_not_recognised` attracts 4 wrong `gpt-4o-mini` picks instead of 32, and `transfer_timing` attracts 53 and 41 instead of 60 and 52. Some intents also lose own items (`transfer_fee_charged` 92.5% → 85.0% for `gpt-4o-mini`, 87.5% → 82.5% for Luna).
- **For the published results:** with the six examples replaced, automation at the 2% limit on `dev` changes by about half a point for `gpt-4o-mini` and one point for Luna. The model comparisons and the finding that a threshold does not carry over to a new model are unaffected.
