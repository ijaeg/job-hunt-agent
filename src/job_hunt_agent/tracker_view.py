"""Pure view helpers for the tracker page (FR-11). No Streamlit import here.

Like ``ui_view.py``, ``rubric.py`` and ``pii.py``, this module has no LLM,
network or Streamlit calls (CLAUDE.md "Architecture and dependency
direction") - ``pages/1_Tracker.py`` calls these functions with
:class:`TrackerEntry` rows already loaded from ``storage`` and renders the
result.

Related: FR-11 AC1
"""

from __future__ import annotations

from datetime import date

from job_hunt_agent.models import TrackerEntry


def is_overdue(follow_up_date: date | None, today: date) -> bool:
    """Whether a follow-up date is in the past relative to ``today`` (FR-11 AC1).

    Args:
        follow_up_date: The entry's follow-up date, or ``None`` if unset.
        today: The caller's notion of "today" - never read from the system
            clock in here, so this stays deterministic and testable.

    Related: FR-11 AC1
    """
    return follow_up_date is not None and follow_up_date < today


def order_entries(entries: list[TrackerEntry], today: date) -> list[TrackerEntry]:
    """Orders tracker rows: overdue first, then by ``updated_at``, newest first (FR-11 AC1).

    Args:
        entries: The user's tracker entries, in any order.
        today: Passed through to :func:`is_overdue`.

    Related: FR-11 AC1
    """
    return sorted(
        entries,
        key=lambda e: (not is_overdue(e.follow_up_date, today), -e.updated_at.timestamp()),
    )
