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

Added after the runs.
