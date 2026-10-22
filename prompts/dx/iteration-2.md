# D-X iteration 2 (luna-none)

Written on 2026-10-22 from iteration 1 and the error counts of its `dev` run by true and routed intent and by confidence, with no message text read (spec §2.5, §8.3). Iteration 1 cut wrong routes from 926 to 380 but stated 1 on only 2 items, so the matched threshold stayed at 1. This iteration asks for a graded top of the confidence scale and sharpens three descriptions. The catalog and its examples are the incumbent's.

## routing_instruction

You triage customer messages sent to a banking app's support team. Choose exactly one of the listed intents: the one that matches what the customer is asking about or reporting. Judge by the customer's main question or problem, not by single words in the message. Many listed intents sit next to related banking topics that are not listed; choose an intent only if the message is about exactly what its description says.

## oos_clause

If none of the listed intents fits the message, including when it is about a related topic that the list does not cover, answer out_of_scope.

## output_clause

Answer with JSON only. "intent" is the chosen intent exactly as written in the list, or out_of_scope. "confidence" is your probability, from 0 to 1, that the chosen intent is correct. Give 1 when the message can only mean the chosen intent; give 0.99 or 0.98 when it clearly fits but another listed intent or an unlisted topic is conceivable; give lower values as the doubt grows.

## catalog

### activate_my_card

- description: The customer has a card and wants to activate it or asks how activation works. Not for linking a card to the app.
- example: I need assistance to activate the card on my account.

### apple_pay_or_google_pay

- description: Using Apple Pay, Google Pay or a phone or watch wallet with the account, including topping up through them.
- example: Can I add funds directly from my Apple Watch?

### automatic_top_up

- description: Setting up automatic top-ups or asking how they work, their rules and their limits.
- example: When I travel, can it automatically add money in certain intervals?

### balance_not_updated_after_bank_transfer

- description: Money the customer sent into their own account by bank transfer has not appeared in the balance yet.
- example: I've transferred money into my account but the balance is the same

### balance_not_updated_after_cheque_or_cash_deposit

- description: A cheque or cash deposit has not shown up in the account balance. Not for how to add money by cash or cheque.
- example: I put money in my account a week ago but its still not there, what is happening?

### beneficiary_not_allowed

- description: The customer cannot add a particular beneficiary or send money to them because it is not allowed, as opposed to a transfer that failed for another reason.
- example: Why can't I use this beneficiary?

### cancel_transfer

- description: The customer wants to cancel, stop or reverse a transfer they made, often one sent to the wrong account.
- example: I've made a horrible mistake!  I transferred money to the wrong account by accident!  I entered one of the digits wrong.  I need this cancelled immediately please.

### card_about_to_expire

- description: The card is expiring or has expired: how to get a replacement, what it costs and how long it takes.
- example: I need a new card to replace an expired one. Will it cost anything, and how soon?

### card_arrival

- description: A new card that was already ordered has not arrived yet: delivery status, delays and tracking. Not for how long card delivery usually takes.
- example: I was expecting my new card by now.

### card_linking

- description: Linking a received or found card to the app, or adding a card back to the app.
- example: I received my card. How do I link it to the app?

### card_payment_fee_charged

- description: An unexpected fee was charged on a payment made with the card.
- example: Explain the extra fee on my card when paying.

### card_payment_not_recognised

- description: A card payment in the app or on the statement that the customer does not recognise. Not for a card that may be compromised and needs blocking, and not for direct debits.
- example: i dont recognize a charge on my card

### card_payment_wrong_exchange_rate

- description: The exchange rate applied to a card purchase in a foreign currency looks wrong.
- example: I recently bought something in foreign currency and I am unsure of the exchange rate. Is this rate applied correctly?

### cash_withdrawal_charge

- description: A fee was charged for withdrawing cash.
- example: Why did I get charged for withdrawing cash?

### cash_withdrawal_not_recognised

- description: A cash withdrawal on the account that the customer did not make or does not recognise.
- example: I am seeing unathorized transactions in the app, on my account.

### change_pin

- description: How or where to change the card PIN. Not for a PIN that is blocked, and not for getting a card.
- example: How can I change my PIN even though I'm out of the country in Austria at the moment?

### country_support

- description: Which countries the service and its cards are available in or can be used in. Not for which shops or cash machines accept the card.
- example: Which countries do you support?

### declined_card_payment

- description: A particular card payment or purchase was declined. Not for a card that does not work at all, contactless or virtual card problems, or declined transfers.
- example: I'm not sure why the card payment didn't work.

### declined_cash_withdrawal

- description: An ATM declined a cash withdrawal or would not give out cash.
- example: Why am I unable to withdraw my money through this card?

### declined_transfer

- description: A transfer was declined or rejected, and how to avoid that.
- example: How can I check for an unsupported merchant for my transfer request?

### direct_debit_payment_not_recognised

- description: A direct debit on the account that the customer does not recognise or did not set up.
- example: There is a direct debit charge on my account that I don't recognize.

### disposable_card_limits

- description: Limits on disposable cards: how many can be created and how many transactions each one allows. Not for how to get a disposable card.
- example: I must make several disposable cards every day.

### edit_personal_details

- description: Changing personal details on the account, such as the address after a move.
- example: Can I change my details because I moved?

### exchange_charge

- description: Fees for exchanging one currency into another.
- example: Do I pay extra for exchange?

### exchange_via_app

- description: How to exchange one currency for another in the app. Not for what rate is applied or how rates are set.
- example: I would like to change to a different currency.

### extra_charge_on_statement

- description: An unexplained extra charge on the statement, often a small amount such as 1 pound or 1 dollar.
- example: Why did they charge me an extra $1?

### failed_transfer

- description: An outgoing transfer failed or keeps failing. Not for a beneficiary that is refused as not allowed.
- example: I can't transfer any money from my account to my friend's account, it keeps rejecting it. Can you tell me why? I have enough funds in my account to transfer.

### fiat_currency_support

- description: Which currencies the customer can hold, and holding money in several currencies. Not for receiving money from other people.
- example: Am I allowed to hold money in multiple currencies?

### getting_spare_card

- description: Getting an additional card for the account, including one for a family member, and how many cards are allowed.
- example: I'm looking to get an additional card.

### lost_or_stolen_phone

- description: The customer's phone was lost or stolen, and what to do about access to the app and account.
- example: my phone has been stolen by someone

### order_physical_card

- description: Ordering a physical card, including a physical version of a virtual card, its cost and where it can be delivered. Not for getting a virtual card or replacing an expiring card.
- example: Where can I get a physical card?

### pending_card_payment

- description: A card payment still shows as pending, or what a pending payment means.
- example: What does a 'pending payment' mean?

### pending_cash_withdrawal

- description: An ATM cash withdrawal still shows as pending.
- example: I needed cash today, so I used another provider's ATM, and when I attempted to withdraw, it declined. I just checked it out and I'm still showing my account with that amount pending! I didn't take any money out, it was declined, so I don't want that to be processed as a withdrawal.

### pending_top_up

- description: A top-up is still pending or has not finished.
- example: Why hasn't my top-up finished pending yet?

### pending_transfer

- description: A transfer is stuck as pending, or how long the pending period lasts.
- example: How long does the "pending" period of a transfer take?

### Refund_not_showing_up

- description: A refund that a merchant says it sent does not appear in the account or on the statement.
- example: The refund isn't appearing in my account

### request_refund

- description: The customer wants a refund or their money back for a purchase.
- example: Please help me get a refund?

### reverted_card_payment?

- description: A card payment was taken and then returned to the account or cancelled, so the merchant was not paid.
- example: I cannot seem to buy something online with my card? the payment comes back, what's going on?

### supported_cards_and_currencies

- description: Which cards, such as Visa, Mastercard or foreign credit cards, and which currencies can be used to top up the account. Not for fees on card top-ups or adding money by transfer.
- example: I only have one other credit card from the US. Do you accept that?

### top_up_failed

- description: A top-up from a card failed or was declined. Not for a top-up that went through and was later reversed.
- example: I tried to charge my card but it was declined. A couple days ago I was able to charge it and it was accepted. Is something wrong? Will you double check for me please?

### top_up_reverted

- description: A top-up appeared in the account and was then cancelled or reversed. Not for general questions about topping up by card.
- example: What did you do with my money??? I just topped up, I saw the money was there, but now it's gone!! What did you do with it?

### transaction_charged_twice

- description: One purchase was charged twice or several times.
- example: I had a duplicate card and bought something and it showed up twice. I canceled my card, how do I get my money back?

### transfer_fee_charged

- description: A fee was charged on a transfer, or the recipient received less than was sent. Not for fees on top-ups by bank transfer.
- example: Hi! I'm a university student studying abroad and I noticed that when I was trying to cross-reference my budget for this month that there were extra fees I was not expecting. Why is that? I've had this account for years and I haven't had any trouble so far, it might not even be on your all's end since I'm still new to international travel and finance, but I wanted to double check in case a mistake was made!

### transfer_not_received_by_recipient

- description: The recipient has not received a transfer that the customer sent.
- example: I made a transfer the day before yesterday within this country. It is still not showing up at all. I have double-checked and the account number is certainly right. I've actually type this multiple times. can you look into what is going on here?

### transfer_timing

- description: How long a transfer takes to arrive, including transfers to and from other countries.
- example: I just did a transfer, but don't see the money in my account. What's up?

### verify_top_up

- description: How to verify a top-up or the card used for it, including where to find the verification code.
- example: I can't see a verification code anywhere

### visa_or_mastercard

- description: Whether the card is a Visa or a Mastercard, or a preference for one of them.
- example: Mastercard is my preferred company.

### why_verify_identity

- description: Why identity verification is needed, and using the account before verification is complete. Not for how to complete verification or problems completing it.
- example: If my identy verifacation hasn't gone through can I use my account?

### wrong_amount_of_cash_received

- description: An ATM gave out less cash than the customer requested.
- example: I got some cash but it wasn't the right amount.

### wrong_exchange_rate_for_cash_withdrawal

- description: The exchange rate applied to a cash withdrawal in a foreign currency looks wrong.
- example: Can I make a withdraw in my home currency at an ATM? I'm on vacation and am a bit worried because I don't have cash with me. Is it possible to withdraw here without any additional costs or fees?
