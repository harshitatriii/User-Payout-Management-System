# API Reference

Base URL: `http://127.0.0.1:8000/api/`
All request/response bodies are JSON. Everything can also be tried in the DRF browsable API
by opening the URLs in a browser.

## Creators

**`POST /api/creators/`** – create a creator
```json
{ "username": "john_doe", "name": "John Doe" }
```

**`GET /api/creators/{id}/`** – get a creator

**`GET /api/creators/{id}/balance/`** – balance (cached + recalculated from the ledger)
```json
{ "creator": "john_doe", "cached_balance": "80.00", "ledger_balance": "80.00" }
```

**`GET /api/creators/{id}/ledger/`** – all transactions for the creator

**`GET /api/creators/{id}/payout-summary/`** – a summary that matches the assignment
```json
{
  "creator": "john_doe",
  "advance_paid_total": "12.00",
  "final_settlement_total": "68.00",
  "withdrawn_total": "0.00",
  "recovered_total": "0.00",
  "current_balance": "80.00"
}
```

## Brands

**`POST /api/brands/`** · **`GET /api/brands/`**
```json
{ "name": "brand_1" }
```

## Sales

**`POST /api/sales/`** – create a sale (starts as `pending`)
```json
{ "creator": 1, "brand": 1, "earning": "40.00" }
```

**`GET /api/sales/`** – list sales. Filters: `?creator=1&status=pending`

**`POST /api/sales/{id}/reconcile/`** – approve or reject a sale
```json
{ "status": "approved" }     // or "rejected"
```
Errors: `409` if the sale is already reconciled, `400` for an invalid status.

## Advance payout

**`POST /api/advance-payout/run/`** – run the advance job (safe to run repeatedly)
```json
{ "creator": 1 }      // optional; leave empty {} to run for everyone
```
Response:
```json
{ "eligible_sales": 3, "advances_paid": 3 }
```

## Withdrawals

**`POST /api/withdrawals/`** – request a withdrawal
```json
{ "creator": 1, "amount": "50.00" }
```
Errors: `400` if the amount is more than the balance or not positive, `429` if a withdrawal
was already made in the last 24 hours.

**`POST /api/withdrawals/{id}/mark/`** – set the result (simulates the payment provider)
```json
{ "status": "success" }     // "failed" / "cancelled" / "rejected" credit the money back
```

**`GET /api/withdrawals/`** – list withdrawals

## Full example (the assignment's ₹68 case)

```
POST /api/creators/            {"username": "john_doe"}
POST /api/brands/              {"name": "brand_1"}
POST /api/sales/               {"creator": 1, "brand": 1, "earning": "40.00"}   (x3)
POST /api/advance-payout/run/  {}                       -> advance total = 12.00
POST /api/sales/1/reconcile/   {"status": "rejected"}
POST /api/sales/2/reconcile/   {"status": "approved"}
POST /api/sales/3/reconcile/   {"status": "approved"}
GET  /api/creators/1/payout-summary/   -> final_settlement_total = 68.00, balance = 80.00
```

## Status codes used

`200` OK · `201` Created · `400` bad request (validation / not enough balance) ·
`404` not found · `409` conflict (already reconciled) · `429` too many requests (24-hour limit).
