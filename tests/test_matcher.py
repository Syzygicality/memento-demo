"""Pure unit tests for the deterministic reconciliation matcher."""

from __future__ import annotations

import uuid
from datetime import date

from data.tables.reconciliation import ExceptionKind
from services.reconciliation_matcher import PostingCandidate, match_line


def _candidate(amount: int, d: date, ref: str = "") -> PostingCandidate:
    return PostingCandidate(uuid.uuid4(), amount, d, ref)


def test_exact_single_match() -> None:
    c = _candidate(1000, date(2026, 6, 1), "INV-1")
    result = match_line(1000, date(2026, 6, 2), "INV-1", [c])
    assert result.posting_id == c.posting_id
    assert result.exception is None


def test_no_candidate_is_unmatched() -> None:
    result = match_line(1000, date(2026, 6, 1), "", [_candidate(999, date(2026, 6, 1))])
    assert result.posting_id is None
    assert result.exception is ExceptionKind.UNMATCHED


def test_two_candidates_is_ambiguous_not_guessed() -> None:
    day = date(2026, 6, 1)
    result = match_line(1000, day, "", [_candidate(1000, day), _candidate(1000, day)])
    assert result.posting_id is None
    assert result.exception is ExceptionKind.AMBIGUOUS


def test_date_outside_window_does_not_match() -> None:
    result = match_line(
        1000, date(2026, 6, 10), "", [_candidate(1000, date(2026, 6, 1))]
    )
    assert result.exception is ExceptionKind.UNMATCHED
