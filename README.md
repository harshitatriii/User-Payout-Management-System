# User Payout Management System

My solution for the Faym SDE Intern assignment.

This is a backend system that manages payouts to creators for affiliate sales. Every sale
starts as `pending`. Creators get a 10% advance on their pending sales. Later an admin
marks each sale `approved` or `rejected`, and the system settles the final payout
(adjusting for the advance that was already paid). Creators can withdraw their balance
(once every 24 hours), and if a payout fails, the money is put back so they can try again.

Built with **Django + Django REST Framework**, using **SQLite** so it runs without any
database setup.

## How to run

```bash
# 1. create and activate a virtual environment
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # mac / linux

# 2. install dependencies
pip install -r requirements.txt

# 3. set up the database
python manage.py migrate

# 4. (optional) load the example data from the assignment
python manage.py seed_data

# 5. run the tests
python manage.py test

# 6. start the server
python manage.py runserver
# API:   http://127.0.0.1:8000/api/
# admin: python manage.py createsuperuser  ->  http://127.0.0.1:8000/admin/
```

## Trying the main flow

This reproduces the exact example from the assignment (final payout = ₹68):

```bash
python manage.py seed_data              # john_doe with 3 pending sales of Rs.40
python manage.py run_advance_payouts    # pays 10% advance = Rs.12  (Rs.4 per sale)
```

Now mark 1 sale `rejected` and 2 `approved` (from the browsable API or the admin), then
open `GET /api/creators/1/payout-summary/`. You'll see:

```
final_settlement_total = 68.00
current_balance        = 80.00      (advance 12 + final 68)
```

## How I designed it (short version)

The main idea: I don't keep just one balance number and add/subtract from it directly.
Instead, every money movement is saved as a row in a **ledger** table
(`PayoutTransaction`) — advance, final payout, clawback, withdrawal, recovery. The
creator's balance is basically the sum of these rows. I also keep a cached `balance` field
on the creator, updated together with each ledger row, so reads are fast.

The decisions I care about most:

- **An advance is never paid twice.** Even if the advance job runs many times, or two
  copies run at the same moment, a sale can only ever get one advance. I enforce this with
  a database unique constraint on `(sale, type)`, backed up by a flag and a row lock.
- **Every money change is atomic and locks the row** (`transaction.atomic` +
  `select_for_update`), so two requests can't corrupt the balance.
- **Money is stored as `Decimal`, never `float`**, so there are no rounding errors.

The full reasoning is in [docs/LLD.md](docs/LLD.md).

## Project structure

```
User-Payout-Management-System/
├── manage.py
├── requirements.txt
├── config/                 # Django project (settings, urls)
├── payouts/
│   ├── models.py           # the database tables (schema)
│   ├── services.py         # all the business logic
│   ├── serializers.py      # input / output validation
│   ├── views.py            # the API endpoints (thin layer)
│   ├── urls.py             # routes
│   ├── admin.py            # admin panel setup
│   ├── exceptions.py       # custom errors -> proper HTTP codes
│   ├── constants.py        # advance rate, cooldown, money precision
│   ├── tests.py            # tests (8)
│   └── management/commands/ # seed_data, run_advance_payouts
└── docs/
    ├── LLD.md              # low-level design + decisions + edge cases
    ├── SCHEMA.md           # database schema and relationships
    └── API.md              # list of endpoints with examples
```

## Where each deliverable is

| Deliverable | Where to find it |
|---|---|
| Low-Level Design | `docs/LLD.md` |
| DB schema with relationships | `docs/SCHEMA.md`, `payouts/models.py` |
| Class design | `payouts/services.py`, `payouts/models.py` |
| APIs / endpoints | `docs/API.md`, `payouts/views.py` |
| Edge cases & failure scenarios | `docs/LLD.md`, `payouts/tests.py` |
| Working implementation | the whole repo — `python manage.py test` (8 passing) |
| Design decisions & trade-offs | `docs/LLD.md` |
