# Architecture

Ledger is a single FastAPI service over Postgres. It is small on purpose: the
surface area is narrow so the money invariants can be enforced everywhere they
matter.

## Request lifecycle

```
HTTP request
  → CORS middleware
  → RequestContextMiddleware        resolves tenant (signed token) + request id
  → route handler (feature slice)   e.g. transfers.routes.create_transfer
  → service                         opens/owns the DB transaction
  → posting engine                  writes transaction + postings + snapshots
  → Postgres                        deferred balance trigger fires at COMMIT
```

The tenant is always taken from the request context, never the body
(`tenant-from-auth-context`). The service layer owns the transaction boundary so
a transfer's posting and its idempotency record commit together
(`idempotency-postgres`, `engine-does-not-own-transaction`).

## Modules (feature slices)

| Module | Responsibility | Key decisions |
|---|---|---|
| `money` | `Minor` units, `Currency`, rounding | `integer-minor-units`, `bankers-rounding-at-presentation` |
| `accounts` | chart of accounts, open/read | `sign-at-posting-time`, `chart-materialized-path` |
| `postings` | the double-entry engine | `append-only-ledger`, `balance-trigger` |
| `transfers` | idempotent money movement | `transfer-is-one-transaction`, `transfer-advisory-lock` |
| `idempotency` | key store in Postgres | `idempotency-fingerprint`, `idempotency-postgres` |
| `balances` | materialized snapshots | `balance-snapshot` |
| `reconciliation` | import + deterministic match | `reconciliation-deterministic-first` |
| `statements` | immutable, streamed export | `statement-immutable`, `statement-streamed-export` |
| `config` / `api` / `data` | platform | `composed-settings`, `alembic-owns-ddl` |

## The two enforcement layers

1. **Database** — the deferred `transactions_balance_check` trigger rejects any
   unbalanced transaction at commit; foreign keys and the snapshot watermark hold
   referential and freshness invariants.
2. **Application** — the posting engine validates balance and leg count before
   the DB ever sees the rows; the service layer owns atomicity.

Where the two overlap (transactions must balance), that is deliberate
defense-in-depth, not redundancy: the app gives a good error message, the DB
guarantees correctness even against a raw write.

## Where the graph comes from

This repo is a Memento subject. The [`DECISIONS.md`](../DECISIONS.md) record and
the [`prs/`](../prs/) ledger are the structured inputs; Memento's distillation
pipeline turns each merged PR + its session transcripts into decision nodes
anchored to the files above, authored by the PR's engineer, grouped by feature,
with `superseded_by` edges along the three supersede chains in `prs/README.md`.
