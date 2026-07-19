# PR ledger

A machine-readable history of the pull requests that built Ledger, alongside a
few full write-ups. This is the raw material Memento distills into the memory
graph — each PR resolves to a **PR** node and its **engineer**, `introduced` the
**decision** nodes it recorded, and (where `supersedes` is non-empty) creates a
`superseded_by` edge from the old decision to the new one.

## Files

- [`index.jsonl`](./index.jsonl) — one JSON object per merged PR:
  `number, title, author, handle, branch, merged_at, feature, files, decisions,
  supersedes`. This is the authoritative index; the demo's git history is seeded
  from it (`scripts/seed_history.sh`).
- `PR-<n>-*.md` — full write-ups for the PRs where the *why* is richest (the
  three that supersede an earlier decision). Real PRs should read like these:
  state the background, the change, and why — not just what.

## Supersede chains (the `superseded_by` edges)

| Old decision | New decision | PR |
|---|---|---|
| `balance-on-read` | `balance-snapshot` | #176 |
| `idempotency-redis` | `idempotency-postgres` | #181 |
| `transfer-row-lock` | `transfer-advisory-lock` | #188 |
