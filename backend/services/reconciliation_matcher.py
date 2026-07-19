"""Deterministic statement matcher.

Matching runs a strict pass before anything fuzzy: a statement line matches a
posting only when the amount is exactly equal, the value date falls inside a
small window, and the external reference agrees (when present). A line with more
than one candidate is reported ``AMBIGUOUS`` rather than guessed; a line with
none is ``UNMATCHED``. Nothing here writes to the ledger — matching only proposes
links; unmatched lines become exceptions for a human (see DECISIONS.md →
reconciliation-deterministic-first).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from data.tables.reconciliation import ExceptionKind

MATCH_WINDOW = timedelta(days=2)


@dataclass(frozen=True)
class PostingCandidate:
    """A posting the matcher may link a statement line to."""

    posting_id: uuid.UUID
    amount: int
    effective_date: date
    external_ref: str = ""


@dataclass(frozen=True)
class MatchResult:
    """Either a matched posting id or the reason it could not be matched."""

    posting_id: uuid.UUID | None
    exception: ExceptionKind | None


def match_line(
    amount: int,
    value_date: date,
    external_ref: str,
    candidates: list[PostingCandidate],
) -> MatchResult:
    """Match one statement line against candidate postings, deterministically."""
    hits = [
        c
        for c in candidates
        if c.amount == amount
        and abs((c.effective_date - value_date).days) <= MATCH_WINDOW.days
        and (not external_ref or not c.external_ref or c.external_ref == external_ref)
    ]
    if len(hits) == 1:
        return MatchResult(hits[0].posting_id, None)
    if len(hits) > 1:
        return MatchResult(None, ExceptionKind.AMBIGUOUS)
    return MatchResult(None, ExceptionKind.UNMATCHED)
