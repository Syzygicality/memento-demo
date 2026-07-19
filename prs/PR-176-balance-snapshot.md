# PR #176 — Materialize balances in a snapshot updated in-transaction

**Author:** Tomás Reyes (`@tomas-reyes`) · **Branch:** `tomas/balance-snapshot`
**Merged:** 2026-03-25 · **Feature:** balances
**Reviewers:** @diego-alvarez (ledger-core), @maya-chen

## Background

Balances were summed from postings on every read (#114). That was correct and
had zero write cost, but the read cost grew linearly with an account's posting
count. Our largest operating account crossed ~400k postings this month and a
single balance read started taking >200ms; the transfer funds-check does this
read while holding the source lock, so slow reads were widening the lock window
too.

## What changed

- New `account_balances` snapshot table: one row per account, `balance` in minor
  units, plus a `version` / `as_of_posting_id` watermark (`0002` migration).
- The posting engine folds each posting into the account's snapshot **inside the
  same transaction** that writes the posting, so a committed balance can never
  disagree with its postings.
- `balances.service.current_balance` reads the snapshot (O(1)); `recompute` keeps
  the authoritative summation for reconciliation and tests.

## Why in-transaction, not a trigger or async job

A trigger could keep the snapshot current, but we already have one deferred
trigger doing the balance check and wanted the balance-maintenance logic in
Python where it is testable. An async updater would make balances eventually
consistent, which the funds check cannot tolerate. Updating in the posting's own
transaction keeps the snapshot exactly as durable as the postings.

## Supersedes

- `balance-on-read` (#114). On-read summation is now dead; the decision record
  keeps it as the rationale for this change.

## Decision

- `balance-snapshot`
