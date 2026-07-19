# Ledger

A double-entry billing and payments core. Ledger keeps money correct: an
append-only posting engine, idempotent transfers, materialized balances,
statement reconciliation, and immutable statements — all over Postgres.

> **This repository is a Memento demo subject.** It is a realistic,
> decision-dense product whose git/PR history and decision record feed
> [Memento](../memento), which distills it into a knowledge graph of
> **decisions, files, PRs, engineers, and features** (with `superseded_by`
> edges as decisions evolve). The Memento hook is wired in
> `.claude/settings.json`. See [`DECISIONS.md`](./DECISIONS.md) for the durable
> decision record and [`docs/ROADMAP.md`](./docs/ROADMAP.md) for what's next.

## What it does

- **Accounts** — a hierarchical chart of accounts, each typed by its normal
  balance (debit or credit) and pinned to a single currency.
- **Postings** — the double-entry engine. Every transaction is a set of postings
  that must sum to zero; the ledger is append-only.
- **Transfers** — a high-level, idempotent money-movement API on top of postings.
- **Balances** — materialized per-account snapshots, updated in the posting's own
  transaction.
- **Reconciliation** — import external statement lines and match them to postings.
- **Statements** — point-in-time, immutable, streamed exports.

## Quickstart

```bash
cp .env.example .env            # fill in LEDGER_AUTH_SECRET
docker compose up -d db
uv sync --all-extras
uv run alembic upgrade head
uvicorn main:app --app-dir backend --reload
```

Open http://localhost:8000/docs for the OpenAPI UI.

## Design north star

Correctness of money outranks throughput, elegance, and convenience. Every
load-bearing invariant (transactions balance, the ledger is append-only, minor
units never mix with counts, a transfer is idempotent) is enforced as close to
the data as possible — a DB trigger or constraint first, the service layer
second. The reasoning behind each of those choices lives in `DECISIONS.md`.

## Repository layout

See [`CLAUDE.md`](./CLAUDE.md) for the module map and the invariants, and
[`docs/architecture.md`](./docs/architecture.md) for the request lifecycle.

## Team

Ownership is in [`CODEOWNERS`](./CODEOWNERS); the people behind the modules are
in [`docs/TEAM.md`](./docs/TEAM.md).
