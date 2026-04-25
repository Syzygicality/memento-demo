# Team

The people behind Ledger. Handles match `CODEOWNERS` and the git authorship used
to seed the demo history, so Memento resolves each PR to the right engineer node.

| Name | Handle | Role | Owns |
|---|---|---|---|
| Maya Chen | `@maya-chen` | Tech Lead | invariants, tooling, decision record, reviews |
| Diego Alvarez | `@diego-alvarez` | Backend — Ledger Core | postings engine, money types, accounts, tables |
| Priya Nair | `@priya-nair` | Backend — Transfers | transfers, idempotency, concurrency |
| Tomás Reyes | `@tomas-reyes` | Backend — Balances | balances, statements, rounding |
| Sam Okoro | `@sam-okoro` | Backend — Reconciliation | reconciliation, matcher, test harness |
| Lena Fischer | `@lena-fischer` | Platform | config, db engine, api wiring, migrations |
| Aiko Tanaka | `@aiko-tanaka` | Backend — API/Docs | API surface, OpenAPI, docs |

## How ownership maps to the graph

Each engineer's merged PRs become `made` edges from their **engineer** node to the
**decision** nodes distilled from those PRs; `CODEOWNERS` describes which
**feature** areas they own. The tech lead reviews every money-path change, which
is why Maya co-owns the core paths without authoring most of them.
