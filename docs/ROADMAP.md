# Ledger — Roadmap

The base structure (accounts, postings, transfers, idempotency, balances,
reconciliation, statements, platform) is in place. This is the feature backlog a
5+ engineer team would work through over the next two quarters. Each feature is
sized to force real, documented decisions — several of which will *supersede*
today's — so the Memento graph keeps growing new decision, PR, and
`superseded_by` nodes as the product matures.

Each item notes: the new **feature** area, the **decisions** it will force, and
the graph edges it adds.

## Q3 — correctness & scale

### 1. Holds & authorizations
Two-phase money movement: place a **hold** that reserves funds, then capture or
release it. Balances gain an `available` vs `posted` split.
- Decisions: hold expiry policy; whether a hold is a posting or a separate
  reservation row; how `available` interacts with the funds check (likely
  **supersedes** part of `transfer-advisory-lock`'s funds logic).
- Files: `backend/holds/*`, `backend/balances/service.py`, `backend/data/tables/holds.py`
- Graph: new `holds` feature hub; a `superseded_by` edge into the funds-check chain.

### 2. Multi-currency & FX conversion accounts
Lift the single-currency restriction by introducing explicit conversion accounts
and a rate source, replacing outright rejection of cross-currency transfers.
- Decisions: rate provenance & rounding at conversion; **supersedes**
  `currency-fixed-per-account`'s "reject cross-currency" stance.
- Files: `backend/fx/*`, `backend/money/types.py`, `backend/transfers/service.py`
- Graph: `fx` feature; `superseded_by` from `currency-fixed-per-account`.

### 3. Double-entry partitioning & sharding
Partition `postings`/`transactions` by tenant + time to keep hot tables small;
introduce a routing layer.
- Decisions: partition key; whether the balance trigger survives partitioning
  (it may need to move to a per-partition trigger — **supersedes** `balance-trigger`
  mechanics); backfill strategy.
- Files: `backend/data/database/partitioning.py`, `migrations/versions/00XX_*`
- Graph: new migration file nodes; a supersede on the trigger decision.

### 4. Outbox & event publishing
A transactional outbox so every committed transaction emits a durable event
(webhooks, downstream ledgers) without a second commit.
- Decisions: outbox-in-same-transaction vs CDC; at-least-once delivery contract;
  ordering guarantees.
- Files: `backend/outbox/*`, `backend/data/tables/outbox.py`
- Graph: `outbox` feature; edges to `postings` decisions.

## Q4 — product surface

### 5. Reversals & adjustments API
A first-class endpoint for compensating entries (today `corrects_id` exists but
has no API), with guardrails so a reversal cannot itself unbalance.
- Decisions: who may reverse; reversal window; partial vs full.
- Files: `backend/reversals/*`, `backend/postings/engine.py`
- Graph: `reversals` feature; edges into `append-only-ledger`.

### 6. Scheduled & recurring transfers
Cron-like scheduled transfers with idempotent execution per occurrence.
- Decisions: occurrence idempotency key derivation (reuses `idempotency-fingerprint`);
  missed-run catch-up policy; timezone handling (reuses `utc-timestamptz`).
- Files: `backend/schedules/*`, `backend/job_queue/*`
- Graph: `schedules` feature; reuse edges to idempotency decisions.

### 7. Reporting & trial balance
Roll-up reports over the materialized-path chart: trial balance, P&L, balance
sheet, as-of any instant.
- Decisions: report reads from snapshots vs `recompute`; as-of via effective_at
  windowing (reuses `effective-at-distinct-from-created-at`).
- Files: `backend/reporting/*`
- Graph: `reporting` feature hub; heavy `governs` fan-in on `accounts` files.

### 8. Fuzzy reconciliation (opt-in second pass)
A confidence-scored matcher that runs only after the deterministic pass and only
*proposes* matches for human approval.
- Decisions: scoring model; approval workflow; never auto-post (reaffirms
  `reconciliation-exceptions-not-auto`).
- Files: `backend/reconciliation/fuzzy.py`
- Graph: extends the `reconciliation` feature; edges to the matcher decisions.

## Platform & operability (continuous)

### 9. API authentication & tenant provisioning
Replace the demo HMAC token with real API keys / OAuth client credentials and a
tenant onboarding flow.
- Files: `backend/api_auth/*`, `backend/api/middleware/request_context.py`
- Graph: `api-auth` feature; **supersedes** the demo `tenant-from-auth-context`
  token mechanism.

### 10. Observability: structured logs, metrics, traces
Per-request tracing, money-movement metrics, and a balance-drift alert (snapshot
vs `recompute`).
- Files: `backend/platform/observability.py`, `backend/balances/service.py`
- Graph: `observability` feature; edges into `balances`.

### 11. Idempotency sweeper as a background job
Promote the sweep from a helper to a scheduled job with metrics on reclaimed vs
retained keys (builds on `idempotency-sweep-min-age`).
- Files: `backend/idempotency/sweeper.py`, `backend/job_queue/*`

### 12. Admin & audit surface
Read-only endpoints over the append-only history for support and compliance:
per-account journal, decision-anchored change log.
- Files: `backend/admin/*`
- Graph: `admin` feature; broad `governs` links across the schema.

### 13. Idempotency key inspection endpoint
A read-only lookup so support can answer "did this key already run, and what
will it replay?" without shell access to Postgres — the first slice of the
admin surface (12), scoped to what the sweeper (11) is about to reclaim.
- Decisions: exposes stored status/response metadata but never the raw
  response body over an unauthenticated-by-tenant channel; surfaces
  `swept_at` computed from the sweeper's `min_age` rather than a stored column,
  so the two can't drift.
- Files: `backend/routers/idempotency_routes.py`, `backend/schemas/idempotency_schemas.py`,
  `backend/services/idempotency_store.py`
- Graph: extends `idempotency-sweep-min-age`; seeds the `admin` feature hub
  that item 12 will grow into.

---

### How this grows the graph

Every feature above lands as one or more PRs (new **PR** nodes) authored by a
team member (**engineer** edges), recording decisions (**decision** nodes)
anchored to the files it touches (**governs** edges) under its feature
(**belongs_to** edges). Items 1, 2, 3, and 9 each **supersede** an existing
decision, so the graph's `superseded_by` chains lengthen over time — which is the
whole point of the demo: a living memory of *why*, not a snapshot.
