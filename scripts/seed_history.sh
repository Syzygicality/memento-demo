#!/usr/bin/env bash
# Seed a realistic, multi-author git history from prs/index.jsonl.
#
# Each merged PR becomes one commit, authored by the PR's engineer on its merge
# date, touching the files it changed and naming the decisions it introduced /
# superseded in the commit message. This is what gives Memento real PR and
# engineer nodes to attach the distilled decisions to.
#
# Idempotent-ish: run on a fresh repo (or after `git checkout --orphan`). Safe to
# re-read; it does not force-push anything.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 - <<'PY' > /tmp/ledger_prs.tsv
import json
rows = []
for line in open("prs/index.jsonl"):
    line = line.strip()
    if not line:
        continue
    pr = json.loads(line)
    rows.append(pr)
rows.sort(key=lambda p: (p["merged_at"], p["number"]))
for p in rows:
    files = " ".join(p["files"])
    dec = ",".join(p["decisions"])
    sup = ",".join(p.get("supersedes", []))
    print("\t".join([
        str(p["number"]), p["title"], p["author"], p["handle"],
        p["merged_at"], p["feature"], files, dec, sup,
    ]))
PY

while IFS=$'\t' read -r number title author handle date feature files decisions supersedes; do
  # Stage the PR's files (they already exist in the tree); allow-empty so a PR
  # that only re-touches already-committed files still lands as its own commit.
  # shellcheck disable=SC2086
  git add $files 2>/dev/null || true

  msg="PR #${number}: ${title}

Feature: ${feature}
Author: ${author} (@${handle})
Decisions: ${decisions:-none}"
  if [ -n "${supersedes}" ]; then
    msg="${msg}
Supersedes: ${supersedes}"
  fi

  email="${handle}@ledger.dev"
  GIT_AUTHOR_NAME="${author}" GIT_AUTHOR_EMAIL="${email}" \
  GIT_AUTHOR_DATE="${date}T12:00:00" \
  GIT_COMMITTER_NAME="${author}" GIT_COMMITTER_EMAIL="${email}" \
  GIT_COMMITTER_DATE="${date}T12:00:00" \
    git commit --allow-empty -q -m "${msg}"
  echo "seeded PR #${number} by ${author} (${date})"
done < /tmp/ledger_prs.tsv

# Capture everything the PR list didn't explicitly touch (routes, schemas,
# __init__, docs, this script) as a final tech-lead scaffolding commit.
git add -A
if ! git diff --cached --quiet; then
  GIT_AUTHOR_NAME="Maya Chen" GIT_AUTHOR_EMAIL="maya-chen@ledger.dev" \
  GIT_AUTHOR_DATE="2026-04-25T12:00:00" \
  GIT_COMMITTER_NAME="Maya Chen" GIT_COMMITTER_EMAIL="maya-chen@ledger.dev" \
  GIT_COMMITTER_DATE="2026-04-25T12:00:00" \
    git commit -q -m "chore: scaffold remainder (routes, schemas, docs, tooling)"
  echo "seeded final scaffold commit by Maya Chen"
fi

rm -f /tmp/ledger_prs.tsv
echo "done: $(git rev-list --count HEAD) commits across $(git log --format='%an' | sort -u | wc -l | tr -d ' ') authors"
