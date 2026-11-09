"""Tests for :mod:`job_hunt_agent.tracker_view` (FR-11).

Related: FR-11 AC1
"""

from __future__ import annotations

from datetime import date, datetime

from job_hunt_agent.models import TrackerEntry
from job_hunt_agent.tracker_view import is_overdue, order_entries

_TODAY = date(2026, 11, 9)


def _entry(**overrides: object) -> TrackerEntry:
    defaults: dict[str, object] = {
        "user_id": "alex",
        "referenznummer": "19522-0068291613-S",
        "title": "Python-Entwickler",
        "employer": "Beispiel AG",
        "url": None,
        "status": "saved",
        "follow_up_date": None,
        "note": None,
        "created_at": datetime(2026, 11, 1, 12, 0, 0),
        "updated_at": datetime(2026, 11, 1, 12, 0, 0),
    }
    defaults.update(overrides)
    return TrackerEntry.model_validate(defaults)


# ---------------------------------------------------------------------------
# is_overdue
# ---------------------------------------------------------------------------


def test_is_overdue_true_for_a_past_date() -> None:
    assert is_overdue(date(2026, 11, 1), _TODAY) is True


def test_is_overdue_false_for_today() -> None:
    assert is_overdue(_TODAY, _TODAY) is False


def test_is_overdue_false_for_a_future_date() -> None:
    assert is_overdue(date(2026, 12, 1), _TODAY) is False


def test_is_overdue_false_when_unset() -> None:
    assert is_overdue(None, _TODAY) is False


# ---------------------------------------------------------------------------
# order_entries (FR-11 AC1): overdue first, then by updated_at, newest first
# ---------------------------------------------------------------------------


def test_order_entries_puts_overdue_rows_first() -> None:
    not_overdue = _entry(
        referenznummer="A-1-S",
        follow_up_date=date(2026, 12, 1),
        updated_at=datetime(2026, 11, 8, 12, 0, 0),
    )
    overdue = _entry(
        referenznummer="B-2-S",
        follow_up_date=date(2026, 11, 1),
        updated_at=datetime(2026, 11, 2, 12, 0, 0),
    )
    ordered = order_entries([not_overdue, overdue], _TODAY)
    assert [e.referenznummer for e in ordered] == ["B-2-S", "A-1-S"]


def test_order_entries_sorts_each_group_by_updated_at_newest_first() -> None:
    older = _entry(referenznummer="A-1-S", updated_at=datetime(2026, 11, 1, 12, 0, 0))
    newer = _entry(referenznummer="B-2-S", updated_at=datetime(2026, 11, 8, 12, 0, 0))
    ordered = order_entries([older, newer], _TODAY)
    assert [e.referenznummer for e in ordered] == ["B-2-S", "A-1-S"]


def test_order_entries_with_no_follow_up_date_is_not_overdue() -> None:
    no_date = _entry(
        referenznummer="A-1-S",
        follow_up_date=None,
        updated_at=datetime(2026, 11, 8, 12, 0, 0),
    )
    overdue = _entry(
        referenznummer="B-2-S",
        follow_up_date=date(2026, 11, 1),
        updated_at=datetime(2026, 11, 1, 12, 0, 0),
    )
    ordered = order_entries([no_date, overdue], _TODAY)
    assert [e.referenznummer for e in ordered] == ["B-2-S", "A-1-S"]
