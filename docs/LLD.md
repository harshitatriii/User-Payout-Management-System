# Low-Level Design

## What the system does

The system pays creators for affiliate sales. A sale can be in one of three states:

- **pending** – the product was bought (but could still be returned)
- **approved** – delivered and the return window is over, so the earning is real
- **rejected** – the product was returned/cancelled, so the earning is gone

Because a pending sale isn't "real money" yet, the business pays creators a small **10%
advance** on pending sales, and then settles up properly once each sale is approved or
rejected.

## The main idea: a ledger instead of a plain balance

The first decision I made was how to store money. The simple way is to keep one `balance`
number on the creator and add or subtract from it. I didn't do that, because it's hard to
audit and easy to get wrong (especially with reversals like clawbacks and refunds).

Instead I use a **ledger**. Every money movement is a row in the `PayoutTransaction` table
with a signed amount:

```
type              amount   linked to
advance           +4.00     sale 1
advance           +4.00     sale 2
advance           +4.00     sale 3
clawback          -4.00     sale 1     (sale 1 got rejected)
final_credit     +36.00     sale 2     (sale 2 approved)
final_credit     +36.00     sale 3     (sale 3 approved)
                 -------
   balance = sum = 80.00
```

The balance is just the sum of a creator's ledger rows. This way I can explain every
rupee, and things like clawbacks or failed-payout recovery are just more rows.

To keep reads fast, I also store a cached `balance` field on the `Creator`. It's updated in
the **same database transaction** as each ledger row (see the `_post()` helper in
`services.py`), so the two never go out of sync. `LedgerService.compute_balance()` can
re-calculate the real balance from the ledger any time, which is useful for checking the
cache is correct.

## Entities (tables)

| Entity | What it is | Important fields |
|--------|-----------|------------------|
| `Creator` | the user earning payouts | `username`, `balance` (cached) |
| `Brand` | a brand behind a sale | `name` |
| `Sale` | one affiliate sale | `earning`, `status`, `advance_paid`, `advance_amount` |
| `Withdrawal` | a withdrawal request | `amount`, `status`, `recovered` |
| `PayoutTransaction` | one ledger entry | `type`, `amount` (signed), `sale?`, `withdrawal?` |

Full column details are in [SCHEMA.md](SCHEMA.md).

## Class design (the service layer)

I kept all the business logic in `services.py`, separate from the API views. The views just
take the request and call a service. This way the logic doesn't depend on Django REST — I
can call the same code from an API, a management command, a test, or the shell.

The services are:

- **`AdvancePayoutService`** – pays the 10% advance on pending sales, and makes sure a sale
  is never advanced twice.
- **`ReconciliationService`** – handles approving/rejecting a sale and settling the payout.
- **`WithdrawalService`** – handles withdrawal requests, the 24-hour limit, and status
  changes.
- **`PayoutRecoveryService`** – puts money back when a payout fails.
- **`LedgerService`** – a small helper to compute the balance from the ledger.

There's also a `_post()` helper that writes one ledger row and updates the cached balance
together. Every money change goes through it.

## How each flow works

### Advance payout
The advance job goes through every pending sale that hasn't been advanced yet. For each one
it locks the sale row, double-checks it's still pending and not advanced, writes an
`advance` ledger row for 10% of the earning, and marks the sale as advanced. Running the
job again does nothing to already-advanced sales, so it's safe to run any number of times.

### Reconciliation (approve / reject)
When an admin reconciles a sale, I first check it's still `pending` (a sale can only be
reconciled once — otherwise I return a 409 error). Then:
- **approved** → I pay `earning − advance` as a `final_credit`.
- **rejected** → the advance was not earned, so I claw it back with a negative row.

### Withdrawal
When a creator requests a withdrawal, I lock their row, check they haven't made a
withdrawal in the last 24 hours, check they have enough balance, then create the withdrawal
and write a negative `withdrawal_debit` row.

### Failed payout recovery
A withdrawal starts as `initiated`. The payment provider would later report the result; I
simulate that with the `mark` endpoint. If it comes back `failed` / `cancelled` /
`rejected`, I credit the amount back to the balance and mark the withdrawal `recovered` so
it can never be credited twice. A failed withdrawal doesn't count towards the 24-hour
limit, so the creator can retry right away.

## Design decisions and trade-offs

**Ledger + cached balance.** The ledger makes everything auditable and reversible; the
cached balance makes reads fast. The trade-off is I have to keep the cache in sync, which I
do by always updating both inside the same transaction.

**Idempotency with a database constraint.** The advance rule says "never pay twice." A
simple `if` check isn't enough, because two jobs running at the same time could both pass
the check before either saves. So I added a unique constraint on `(sale, type)` in the
database — the database itself rejects a second advance row for the same sale. The flag and
row lock are the first line of defense; the constraint is the guarantee.

**Atomic + locked money moves.** Every money change runs inside `transaction.atomic` and
locks the creator/sale row with `select_for_update`. Without this, two withdrawals arriving
together could both read the old balance and both succeed, overdrawing the account. The
lock makes the second one wait and see the updated balance.

**Decimal, not float.** Money is stored and calculated as `Decimal` (rounded to 2 places),
because floats have rounding errors (`0.1 + 0.2` isn't exactly `0.3`), which is not
acceptable for money.

**Failed withdrawals don't count for the 24-hour limit.** The assignment says a failed
payout should be retryable. If failed withdrawals counted towards the limit, a creator
whose payout bounced would be stuck for 24 hours, which felt wrong. So only
active/successful withdrawals count.

## Edge cases handled

- Running the advance job multiple times never double-pays a sale (flag + lock +
  unique constraint). Tested.
- Approving a sale that never got an advance pays the full earning. Tested.
- Reconciling the same sale twice returns a 409 error. Tested.
- An invalid reconcile status returns 400.
- Withdrawing more than the balance returns 400. Tested.
- A second withdrawal within 24 hours returns 429. Tested.
- A withdrawal amount of 0 or less returns 400.
- A failed payout is credited back exactly once and can be retried. Tested.
- All amounts are rounded to paise so there's no float drift.
- If a rejected sale's advance was already withdrawn, the clawback can push the balance
  negative — the ledger records this honestly, and withdrawals are blocked while the
  balance is short. I left this as a clear policy rather than hiding it.

## What I'd add if this went to production

- Run the advance job on a schedule (cron / Celery) instead of manually.
- Add an idempotency key on the withdrawal request API so client retries are safe.
- Connect a real payment provider and update withdrawal status from its webhook.
- Add authentication (only admins reconcile, creators only touch their own withdrawals).
- A periodic job that checks the cached balance against the ledger to catch any drift.
