# CLAUDE.md

Guidelines for Claude Code (and engineers) working in the **Ledger** repository.

This project is instrumented with **Memento** (`.claude/settings.json` runs the
Memento hook on session end). The decisions you make while working here are
distilled from your merged PRs into the team's memory graph — so write PR
descriptions that state *why*, and keep `DECISIONS.md` current.

## Project Overview

Ledger is a double-entry billing/payments core. It exposes a small, strict API:
open accounts, post balanced transactions, move money idempotently, read
balances, reconcile against external statements, and issue immutable statements.
Correctness of money outranks everything else — every load-bearing invariant is
enforced in the database, not only in application code.

## The invariants (do not violate)

1. **The ledger is append-only.** Corrections are compensating entries, never
   `UPDATE`/`DELETE` of postings. (`DECISIONS.md` → append-only-ledger)
2. **Every transaction balances to zero** across its postings — enforced by a DB
   constraint trigger, not just the service layer.
3. **Money is integer minor units** (`Minor`, a `NewType`). Never float. Never
   mix minor units with counts — mypy strict is what stops you.
4. **Money mutations are idempotent** by `Idempotency-Key`, and the key commits
   in the *same Postgres transaction* as the posting.

## Architecture

```
backend/
├── main.py                ← thin entrypoint; wiring lives in api/backend_setup.py
├── config/                ← composed pydantic-settings (the only config entry point)
├── api/                   ← router + middleware wiring, lifespan, request deps
├── money/                 ← Minor NewType, Currency, rounding (presentation only)
├── data/                  ← engine, base repository, SQLModel tables
├── accounts/              ← chart of accounts (hierarchical, typed by normal balance)
├── postings/             ← the append-only double-entry engine (the core)
├── transfers/             ← idempotent money-movement API
├── idempotency/           ← Postgres-backed idempotency store + middleware
├── balances/              ← materialized balance snapshots
├── reconciliation/        ← statement import + deterministic matcher
└── statements/            ← point-in-time, immutable, streamed export
migrations/                ← Alembic owns ALL DDL (incl. the balance trigger)
tests/                     ← real per-test Postgres; the trigger must be exercised
```

New endpoints are added by registering a router in `api/backend_setup.py`'s
`setup_routes`, never by expanding `main.py`.

## Dev commands

| Command | Description |
|---|---|
| `docker compose up` | Postgres + API |
| `uvicorn main:app --app-dir backend --reload` | API against a local Postgres |
| `uv run alembic revision --autogenerate -m "..."` | Generate a migration |
| `uv run alembic upgrade head` | Apply migrations |
| `pytest` | Run the suite (needs Postgres + `initdb` on PATH) |

## Conventions

- Config is read only through the composed `settings` object — never `os.environ`.
- All DDL lives in Alembic; the app issues none at runtime.
- Every write goes through a repository wrapper that re-resolves the session per
  call, so the test harness can swap the DB per test.
- Timestamps are stored as `timestamptz` in UTC; the API serializes RFC3339.
- Branch names: `<name>/<feature>` (e.g. `priya/idempotency-postgres`). PRs need
  two reviewers, one of them a ledger-core owner (`CODEOWNERS`).
- This file is capped at ~150 lines. Compact before it grows; anything derivable
  from `pyproject.toml` or `DECISIONS.md` does not belong here.
