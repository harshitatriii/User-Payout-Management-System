# Database Schema

## How the tables relate

```
Creator 1 ───< Sale >─── 1 Brand
   │             │
   │             │ (0..1)
   │             ▼
   └────────< PayoutTransaction >──── 0..1 Withdrawal
                 (ledger)                    ▲
   Creator 1 ─────< Withdrawal ──────────────┘
```

- A `Creator` has many `Sale`s, many `Withdrawal`s, and many `PayoutTransaction`s.
- A `Brand` has many `Sale`s.
- A `PayoutTransaction` (a ledger row) optionally points to the `Sale` it settled
  (advance / final / clawback) or the `Withdrawal` it belongs to (debit / recovery).

## Tables

### creator
| column | type | notes |
|--------|------|-------|
| id | bigint (PK) | |
| username | varchar(150) | unique |
| name | varchar(200) | optional |
| balance | decimal(14,2) | cached balance; the ledger is the real source |
| created_at | datetime | |

### brand
| column | type | notes |
|--------|------|-------|
| id | bigint (PK) | |
| name | varchar(200) | unique |

### sale
| column | type | notes |
|--------|------|-------|
| id | bigint (PK) | |
| creator_id | FK → creator | on_delete = CASCADE |
| brand_id | FK → brand | on_delete = PROTECT |
| earning | decimal(12,2) | must be > 0 |
| status | varchar(20) | pending / approved / rejected |
| advance_paid | boolean | true once the advance is paid (idempotency flag) |
| advance_amount | decimal(12,2) | how much advance this sale got |
| reconciled_at | datetime | set when approved/rejected |
| created_at, updated_at | datetime | |

Indexes: `(creator, status)` and `(status, advance_paid)`. The second one speeds up the
advance job, which filters exactly on those two columns.

### withdrawal
| column | type | notes |
|--------|------|-------|
| id | bigint (PK) | |
| creator_id | FK → creator | on_delete = CASCADE |
| amount | decimal(14,2) | must be > 0 |
| status | varchar(20) | initiated / processing / success / failed / cancelled / rejected |
| recovered | boolean | true once a failed payout is credited back (so it happens once) |
| created_at, updated_at, completed_at | datetime | |

Index: `(creator, created_at)` — used by the 24-hour limit check.

### payout_transaction  (the ledger)
| column | type | notes |
|--------|------|-------|
| id | bigint (PK) | |
| creator_id | FK → creator | on_delete = CASCADE |
| sale_id | FK → sale (nullable) | set for advance / final_credit / clawback |
| withdrawal_id | FK → withdrawal (nullable) | set for withdrawal_debit / recovery_credit |
| type | varchar(30) | advance / final_credit / clawback / withdrawal_debit / recovery_credit |
| amount | decimal(14,2) | signed: credits are +, debits are − |
| description | varchar(255) | |
| created_at | datetime | |

**Constraint:** a unique constraint on `(sale, type)` (only when `sale` is not null). This
is what stops a sale from ever getting two advances. It's the main idempotency guarantee.

Index: `(creator, created_at)`.

## Notes

- All money columns are `DECIMAL`, never float, and values are rounded to 2 decimal places
  (paise) in code.
- A creator's balance = sum of `amount` across their `payout_transaction` rows.
- Sale status only moves `pending → approved` or `pending → rejected`, once (enforced in
  `ReconciliationService`).
