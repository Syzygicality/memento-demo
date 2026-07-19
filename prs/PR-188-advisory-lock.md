# PR #188 — Replace the source row lock with a per-account advisory lock

**Author:** Priya Nair (`@priya-nair`) · **Branch:** `priya/advisory-lock`
**Merged:** 2026-04-08 · **Feature:** transfers
**Reviewers:** @diego-alvarez (ledger-core), @maya-chen

## Background

Transfers serialized writers to the source account with `SELECT ... FOR UPDATE`
on the account row (#135), held for the whole transfer transaction. Two problems
surfaced under load:

1. The row lock blocked concurrent **readers** of that account's row (balance
   reads via the account fetch), not just other writers.
2. Now that balance reads hit the snapshot (#176) rather than summing postings,
   the row lock is the only thing still forcing readers to wait on a writer —
   exactly the coupling we removed everywhere else.

## What changed

- New `transfers/locking.py`: `account_lock` takes a transaction-scoped Postgres
  advisory lock (`pg_advisory_xact_lock`) keyed by a 63-bit hash of the account
  id.
- The transfer flow takes the advisory lock around the funds-check + posting
  instead of a `FOR UPDATE` row lock.
- The lock releases automatically at commit/rollback, so a crashed request never
  leaks it.

## Why an advisory lock

We still need mutual exclusion between two transfers draining the same account,
or both could pass the funds check and overdraw it. An advisory lock gives us
exactly that mutual exclusion **without** locking the account row, so snapshot
reads of that account stay live while a transfer is in flight.

## Supersedes

- `transfer-row-lock` (#135).

## Decision

- `transfer-advisory-lock`
