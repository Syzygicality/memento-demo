# Ledger — Engineering Decision Record

This document records the durable engineering **decisions** behind the Ledger
codebase: the choices, constraints, and tradeoffs that govern how the code is and
must be built, and that a future engineer cannot recover from the diff alone.

It is written for decision extraction. Each entry is a self-contained claim that
records *why* the code is the way it is, followed by structured metadata:

- **Feature** — the subsystem the decision belongs to (`belongs_to` edge).
- **Files** — paths that exist verbatim in this repo (`governs` edges).
- **PR / Author** — the pull request and engineer that introduced it
  (`introduced` / `made` edges).
- **Supersedes** — the decision id this one replaces (`superseded_by` edge).

Each `###` heading is a stable decision id in backticks.

---

## App composition & routing

### `thin-entrypoint` — The API entrypoint stays minimal; wiring lives in setup
`backend/main.py` only constructs `FastAPI(lifespan=lifespan)` and delegates all
router and middleware registration to `api/backend_setup.py`. New endpoints are
added by registering a router in `setup_routes`, never by expanding `main.py`, so
there is one place that knows the full shape of the app.
- Feature: routing
- Files: `backend/main.py`, `backend/api/backend_setup.py`
- PR: #112 · Author: Maya Chen · 2026-01-28 · Confidence: high

### `middleware-order` — Middleware order is load-bearing
Middleware is registered in a fixed order in `setup_middlewares`: CORS outermost,
then the request-context middleware that resolves the tenant. The order is
deliberate — the tenant must be on `request.state` before any route runs, and
CORS must wrap everything — so it must not be reordered.
- Feature: routing
- Files: `backend/api/backend_setup.py`, `backend/api/middleware/request_context.py`
- PR: #121 · Author: Lena Fischer · 2026-02-09 · Confidence: high

### `tenant-from-auth-context` — Tenant is resolved from auth, never the body
Every money-mutating endpoint takes the acting tenant from the request context
(set by the middleware from a signed token), never from a field in the request
body. A body-supplied tenant would let one tenant post into another's accounts,
so tenant resolution is centralized in `api/deps.py`.
- Feature: routing
- Files: `backend/api/deps.py`, `backend/api/middleware/request_context.py`
- PR: #140 · Author: Lena Fischer · 2026-02-24 · Confidence: high

---

## Money representation

### `integer-minor-units` — Money is integer minor units, never float
Amounts are stored and computed as integer minor units (cents), typed as
`Minor`, a `NewType` over `int`. There is no float anywhere in the money path.
Floats reintroduce representation error that a ledger cannot tolerate, so the
integer representation is the invariant and `Decimal` appears only at
presentation.
- Feature: money
- Files: `backend/money/types.py`
- PR: #103 · Author: Diego Alvarez · 2026-01-21 · Confidence: high

### `minor-newtype-enforced-by-mypy` — Minor units never mix with counts
`Minor` exists specifically so mypy strict rejects code that adds a money amount
to a plain count or passes a count where an amount is expected — the most common
way a ledger grows a silent unit bug. The guarantee is only real because mypy
runs in strict mode over the whole backend.
- Feature: money
- Files: `backend/money/types.py`, `pyproject.toml`
- PR: #103 · Author: Diego Alvarez · 2026-01-21 · Confidence: high

### `bankers-rounding-at-presentation` — Rounding is banker's, and only at the edge
`round_minor` uses round-half-to-even, and rounding is applied only when
converting an externally supplied decimal into minor units — never on
already-stored minor units. Half-to-even avoids the directional bias that
half-up accumulates across aggregate reports.
- Feature: money
- Files: `backend/money/types.py`
- PR: #158 · Author: Tomás Reyes · 2026-03-06 · Confidence: medium

### `currency-fixed-per-account` — Currency is fixed per account; no implicit FX
An account's currency is captured at creation and never changes. Cross-currency
transfers are rejected outright; moving value across currencies must route
through explicit conversion accounts. Implicit FX inside a transfer would bury an
exchange-rate decision inside a money movement, so it is disallowed.
- Feature: accounts
- Files: `backend/money/types.py`, `backend/data/tables/accounts.py`, `backend/transfers/service.py`
- PR: #167 · Author: Diego Alvarez · 2026-03-13 · Confidence: high

---

## Accounts

### `sign-at-posting-time` — Accounts are typed by normal balance; sign applied at posting
Each account declares its normal balance (debit or credit). The sign convention
is applied when a posting is written, not when a balance is read, so a stored
posting is already correctly signed for its account and a balance is a plain sum
rather than a per-read reinterpretation.
- Feature: accounts
- Files: `backend/data/tables/accounts.py`, `backend/postings/engine.py`
- PR: #109 · Author: Diego Alvarez · 2026-01-26 · Confidence: high

### `chart-materialized-path` — The chart of accounts uses a materialized path
Accounts are arranged hierarchically via a dotted materialized `path`
(`assets.cash.operating`) rather than an adjacency list, because reporting rolls
up by prefix and a prefix scan is far cheaper than a recursive CTE on every
report.
- Feature: accounts
- Files: `backend/data/tables/accounts.py`
- PR: #115 · Author: Diego Alvarez · 2026-01-31 · Confidence: medium

### `open-account-seeds-zero-snapshot` — Opening an account seeds its balance row
Opening an account inserts its zero `AccountBalance` snapshot in the same
transaction, so the invariant "every open account has a balance row" holds from
creation and the posting engine never has to create one on a hot path.
- Feature: accounts
- Files: `backend/accounts/service.py`, `backend/data/tables/balances.py`
- PR: #172 · Author: Tomás Reyes · 2026-03-20 · Confidence: high

---

## Postings — the append-only core

### `append-only-ledger` — The ledger is append-only; corrections are compensating entries
Postings and transactions are never updated or deleted in normal operation. A
correction is a new, balanced transaction that references the original via
`corrects_id`. An append-only ledger is auditable and reproducible; mutating
history would make a past statement unreproducible.
- Feature: postings
- Files: `backend/data/tables/transactions.py`, `backend/postings/engine.py`
- PR: #110 · Author: Diego Alvarez · 2026-01-27 · Confidence: high

### `balance-trigger` — Transactions balance to zero, enforced by a DB trigger
Every transaction's postings must sum to zero. This is enforced by a **deferred
constraint trigger** (`transactions_balance_check`) that fires at commit, not
only by the service layer, so a bug or a raw SQL write can never commit an
unbalanced transaction. The trigger is deferred so the engine can insert legs one
at a time within the transaction.
- Feature: postings
- Files: `backend/postings/engine.py`, `migrations/versions/0002_balance_trigger_and_snapshots.py`
- PR: #128 · Author: Diego Alvarez · 2026-02-13 · Confidence: high

### `effective-at-distinct-from-created-at` — Backdating uses effective_at, not mutation
Postings carry an immutable `effective_at` separate from `created_at`, so a
backdated entry is representable by setting `effective_at` in the past without
mutating any existing row. Statement ordering uses `effective_at`; audit ordering
uses `created_at`.
- Feature: postings
- Files: `backend/data/tables/transactions.py`, `backend/statements/service.py`
- PR: #131 · Author: Diego Alvarez · 2026-02-17 · Confidence: high

### `engine-does-not-own-transaction` — The engine writes in the caller's transaction
`post_transaction` never opens or commits its own transaction; it writes into a
caller-provided session. This is what lets a transfer commit its posting and its
idempotency record together. A self-committing engine would break that atomicity.
- Feature: postings
- Files: `backend/postings/engine.py`, `backend/transfers/service.py`
- PR: #133 · Author: Priya Nair · 2026-02-19 · Confidence: high

---

## Balances

### `balance-on-read` — Balances are summed from postings on read *(superseded)*
The first balance implementation summed an account's postings on every read. It
was correct and simple, and it is retained here as the rationale for what
replaced it: summation cost grew linearly with an account's posting count and
became the dominant cost of a balance read past a few hundred thousand postings.
- Feature: balances
- Files: `backend/balances/service.py`
- PR: #114 · Author: Tomás Reyes · 2026-01-30 · Confidence: high
- Superseded-by: `balance-snapshot`

### `balance-snapshot` — Balances are materialized in a snapshot updated in-transaction
Each account has an `account_balances` row updated inside the same transaction as
the postings that change it, so a committed balance can never disagree with its
postings. This supersedes on-read summation, which did not scale. A `version` /
`as_of_posting_id` watermark makes a stale snapshot detectable, and `recompute`
remains the authoritative fallback.
- Feature: balances
- Files: `backend/data/tables/balances.py`, `backend/postings/engine.py`, `backend/balances/service.py`
- PR: #176 · Author: Tomás Reyes · 2026-03-25 · Confidence: high
- Supersedes: `balance-on-read`

---

## Transfers

### `transfer-is-one-transaction` — A transfer maps to exactly one balanced transaction
A transfer creates exactly one transaction with a debit leg and a credit leg,
committed atomically. Splitting a transfer across transactions would let a
partial transfer commit, so the two legs always share one transaction.
- Feature: transfers
- Files: `backend/transfers/service.py`, `backend/postings/engine.py`
- PR: #135 · Author: Priya Nair · 2026-02-21 · Confidence: high

### `transfer-row-lock` — Insufficient-funds guarded by a source-account row lock *(superseded)*
The first concurrency-safe transfer took `SELECT ... FOR UPDATE` on the source
account for the duration of the transfer, serializing writers. It was correct but
held the account row locked across the whole posting write and blocked unrelated
balance readers. Retained as the rationale for the advisory-lock replacement.
- Feature: transfers
- Files: `backend/transfers/service.py`
- PR: #135 · Author: Priya Nair · 2026-02-21 · Confidence: medium
- Superseded-by: `transfer-advisory-lock`

### `transfer-advisory-lock` — Per-account advisory lock replaces the row lock
Transfers serialize writers to the same source account with a Postgres
transaction-scoped **advisory lock** keyed by the account id, rather than a row
lock. This preserves the mutual exclusion the funds check needs while leaving the
account row readable, so balance reads stay live during a transfer. The lock
releases automatically at commit/rollback.
- Feature: transfers
- Files: `backend/transfers/locking.py`, `backend/transfers/service.py`
- PR: #188 · Author: Priya Nair · 2026-04-08 · Confidence: high
- Supersedes: `transfer-row-lock`

---

## Idempotency

### `idempotency-fingerprint` — A key reused with a different body is a 409
Idempotency keys are scoped per `(tenant, endpoint, key)` and stored with a
SHA-256 fingerprint of the canonicalized request body. A replay with the same
fingerprint returns the stored response; the same key with a *different* body is a
409 conflict, never a silent second execution — because the second body almost
always means a client bug.
- Feature: idempotency
- Files: `backend/idempotency/store.py`, `backend/data/tables/idempotency.py`
- PR: #137 · Author: Priya Nair · 2026-02-22 · Confidence: high

### `idempotency-redis` — Idempotency keys stored in Redis *(superseded)*
The first idempotency store was Redis, chosen for speed and TTL support. It could
not guarantee that the key and the posting committed together: a crash between the
Postgres commit and the Redis write left a completed transfer with no key, so a
retry double-posted. Retained as the rationale for moving the store to Postgres.
- Feature: idempotency
- Files: `backend/idempotency/store.py`
- PR: #137 · Author: Priya Nair · 2026-02-22 · Confidence: high
- Superseded-by: `idempotency-postgres`

### `idempotency-postgres` — The idempotency store lives in Postgres, in the same transaction
The idempotency record is written with the same session as the posting, so the
key and the money commit or roll back together. This supersedes the Redis store,
whose separate write could not be made atomic with the posting. The cost is one
extra row per mutating request, which the money guarantee more than justifies.
- Feature: idempotency
- Files: `backend/idempotency/store.py`, `backend/transfers/service.py`, `backend/data/tables/idempotency.py`
- PR: #181 · Author: Priya Nair · 2026-03-30 · Confidence: high
- Supersedes: `idempotency-redis`

### `idempotency-sweep-min-age` — The sweeper never reclaims keys younger than the in-flight window
Idempotency records have a TTL and are swept, but the sweep never deletes a key
younger than `LEDGER_IDEMPOTENCY_MIN_AGE_MINUTES`, the maximum in-flight request
window. Reclaiming a key while a slow original request is still running would let
a concurrent retry execute a second time.
- Feature: idempotency
- Files: `backend/idempotency/store.py`, `backend/config/config.py`
- PR: #199 · Author: Priya Nair · 2026-04-21 · Confidence: medium

---

## Reconciliation

### `reconciliation-deterministic-first` — Deterministic matching before any fuzzy fallback
The matcher links a statement line to a posting only on an exact amount, a small
date window, and an agreeing external reference. A line with more than one
candidate is reported ambiguous rather than guessed. Deterministic-first keeps
reconciliation explainable; a fuzzy match that silently moved money would be
unacceptable.
- Feature: reconciliation
- Files: `backend/reconciliation/matcher.py`
- PR: #190 · Author: Sam Okoro · 2026-04-10 · Confidence: high

### `reconciliation-exceptions-not-auto` — Unmatched lines become exceptions, never auto-adjustments
A statement line the matcher cannot resolve becomes a `ReconciliationException`
row for a human to resolve; it is never auto-adjusted into the ledger. Auto-posting
an unexplained difference would corrupt the very balances reconciliation exists to
verify.
- Feature: reconciliation
- Files: `backend/reconciliation/matcher.py`, `backend/data/tables/reconciliation.py`
- PR: #190 · Author: Sam Okoro · 2026-04-10 · Confidence: high

### `reconciliation-idempotent-import` — Statement import is idempotent by file content hash
A `StatementImport` is keyed by the SHA-256 of the uploaded file, so re-uploading
the same statement returns the existing import instead of duplicating its lines.
Operators retry uploads; without the hash key those retries would double-count a
statement.
- Feature: reconciliation
- Files: `backend/reconciliation/importer.py`, `backend/data/tables/reconciliation.py`
- PR: #196 · Author: Sam Okoro · 2026-04-17 · Confidence: high

---

## Statements

### `statement-immutable` — Statements are point-in-time and immutable once issued
A statement is generated purely by reading append-only postings over a
`[start, end)` window ordered by `effective_at`. Because its only inputs are
immutable, re-issuing a statement for a closed period yields identical output;
statements are never stored as mutable documents.
- Feature: statements
- Files: `backend/statements/service.py`
- PR: #201 · Author: Tomás Reyes · 2026-04-24 · Confidence: high

### `statement-streamed-export` — Statement export streams from a server-side cursor
Statement rows are streamed with `yield_per` rather than buffered into a list,
because a month-end statement for a busy account exceeds a comfortable memory
budget. The running balance is carried in the stream, so no full materialization
is required.
- Feature: statements
- Files: `backend/statements/service.py`, `backend/statements/routes.py`
- PR: #201 · Author: Tomás Reyes · 2026-04-24 · Confidence: medium

---

## Data access & configuration

### `composed-settings` — Configuration is one composed object; no direct os.environ
`config.py` composes one `settings` object from the database and other sections,
each reading env vars via pydantic-settings. Code reads configuration through this
object and never touches `os.environ` directly, so configuration has exactly one
entry point.
- Feature: platform
- Files: `backend/config/config.py`, `backend/config/database_config.py`
- PR: #106 · Author: Lena Fischer · 2026-01-23 · Confidence: high

### `alembic-owns-ddl` — Alembic owns all DDL, including the balance trigger
The application issues no DDL at runtime; every table and the balance-check
trigger are created by Alembic migrations. Startup only verifies connectivity. A
runtime `create_all` would let the app boot against a schema missing its trigger,
so DDL is Alembic's alone.
- Feature: platform
- Files: `backend/api/lifespan.py`, `migrations/env.py`, `alembic.ini`
- PR: #124 · Author: Lena Fischer · 2026-02-11 · Confidence: high

### `repository-reresolves-session` — Repositories re-resolve the session per call
Every table accessor calls `get_db_session()` per operation rather than caching a
session or engine, because the test harness monkeypatches `get_db_session` to a
per-test database. A cached engine would bypass the swap and hit the wrong DB.
- Feature: platform
- Files: `backend/data/repositories/base_repository.py`, `backend/data/database/engine.py`
- PR: #106 · Author: Lena Fischer · 2026-01-23 · Confidence: high

### `utc-timestamptz` — Timestamps are stored as UTC timestamptz
All timestamps are stored as `timestamptz` in UTC; the API serializes RFC3339.
Local time never touches the database, so an account opened in one timezone and
read in another orders identically everywhere.
- Feature: platform
- Files: `backend/data/tables/transactions.py`, `backend/data/tables/accounts.py`
- PR: #145 · Author: Lena Fischer · 2026-02-28 · Confidence: medium

---

## Testing & tooling

### `per-test-postgres` — Tests run against a real per-test Postgres, never sqlite
The suite spins up a fresh Postgres per test and runs `alembic upgrade head`
inside it, so the deferred balance trigger and advisory locks are exercised for
real. sqlite cannot express those, so it is deliberately not a test backend.
- Feature: testing
- Files: `tests/conftest.py`, `tests/test_transfers_idempotency.py`
- PR: #142 · Author: Sam Okoro · 2026-02-25 · Confidence: high

### `mypy-strict-money` — mypy runs strict over the whole backend
CI runs mypy in strict mode over `backend/`, excluding tests. Strict mode is what
makes the `Minor` NewType a real guarantee rather than documentation, so it is a
hard gate, not advisory.
- Feature: tooling
- Files: `pyproject.toml`
- PR: #107 · Author: Maya Chen · 2026-01-24 · Confidence: high

### `ruff-scoped-backend` — Ruff is scoped to backend source and enforces docstrings
Ruff runs over `backend/` only, excluding migrations and tests, and enforces
docstrings on public modules, classes, and functions. Migrations are generated and
tests are exempt, so scoping Ruff keeps the docstring rule meaningful where it
matters.
- Feature: tooling
- Files: `pyproject.toml`
- PR: #107 · Author: Maya Chen · 2026-01-24 · Confidence: medium

### `backend-on-syspath` — Backend imports assume backend/ is the package root
Modules import as if `backend/` is on `sys.path` (e.g. `from config.config import
settings`), configured via `pythonpath` in pyproject and `prepend_sys_path` in
alembic.ini. Imports must not be written relative to the repo root.
- Feature: tooling
- Files: `pyproject.toml`, `alembic.ini`, `backend/api/backend_setup.py`
- PR: #107 · Author: Maya Chen · 2026-01-24 · Confidence: high

---

## Conventions

### `branch-and-review-policy` — Branch naming and the two-reviewer gate
Feature branches are named `<name>/<feature>` (e.g. `priya/idempotency-postgres`).
Every PR needs two approving reviewers, one of whom must own the touched module in
`CODEOWNERS`. Money-path changes without a ledger-core owner's review are not
merged.
- Feature: conventions
- Files: `CLAUDE.md`, `CODEOWNERS`
- PR: #104 · Author: Maya Chen · 2026-01-22 · Confidence: high

### `claude-md-cap` — CLAUDE.md is capped and compacted before it grows
`CLAUDE.md` is kept to ~150 lines and must be compacted before growing; anything
derivable from `pyproject.toml` or `DECISIONS.md` does not belong in it. The cap
keeps the always-loaded guidance dense.
- Feature: conventions
- Files: `CLAUDE.md`, `DECISIONS.md`
- PR: #108 · Author: Maya Chen · 2026-01-25 · Confidence: medium
