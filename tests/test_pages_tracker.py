"""AppTest integration tests for pages/1_Tracker.py (FR-11).

Mirrors ``tests/test_app.py``'s pattern: no network call, no API key
needed (CLAUDE.md invariant 5, NFR-05) - this page never touches the
agent or the model at all.

Related: FR-11 AC1, FR-11 AC2, FR-09 AC1, NFR-05
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from job_hunt_agent import storage
from job_hunt_agent.models import TrackerEntry

PAGE_PATH = str(Path(__file__).resolve().parents[1] / "pages" / "1_Tracker.py")

#: Shared by every seeded entry unless overridden; used to assert created_at
#: survives a status change untouched.
_CREATED_AT = datetime(2026, 11, 5, 9, 0, 0)


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    path = str(tmp_path / f"wp06-{uuid.uuid4().hex}.sqlite")
    monkeypatch.setenv("DB_PATH", path)
    return path


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
        "created_at": _CREATED_AT,
        "updated_at": _CREATED_AT,
    }
    defaults.update(overrides)
    return TrackerEntry.model_validate(defaults)


def _seed_three_entries(db_path: str) -> None:
    """Two non-overdue entries and one overdue one (FR-11 AC1)."""
    conn = storage.get_connection(db_path)
    storage.save_tracker_entry(
        conn,
        _entry(
            referenznummer="A-1-S",
            title="Strong Match",
            employer="Acme",
            follow_up_date=date(2026, 12, 1),
            updated_at=datetime(2026, 11, 5, 9, 0, 0),
        ),
    )
    storage.save_tracker_entry(
        conn,
        _entry(
            referenznummer="B-2-S",
            title="Overdue Match",
            employer="Beta",
            follow_up_date=date(2020, 1, 1),
            updated_at=datetime(2026, 11, 4, 9, 0, 0),
        ),
    )
    storage.save_tracker_entry(
        conn,
        _entry(
            referenznummer="C-3-S",
            title="No Date Match",
            employer="Gamma",
            follow_up_date=None,
            note="worth a follow-up call",
            updated_at=datetime(2026, 11, 6, 9, 0, 0),
        ),
    )


def new_app() -> AppTest:
    return AppTest.from_file(PAGE_PATH, default_timeout=30)


# ---------------------------------------------------------------------------
# Rows render in the right order, overdue one marked (FR-11 AC1)
# ---------------------------------------------------------------------------


def test_rows_render_in_order_and_overdue_is_marked(db_path: str) -> None:
    _seed_three_entries(db_path)
    at = new_app()
    at.run()

    assert not at.exception
    titles = [str(m.value) for m in at.markdown if str(m.value).startswith("**[")]
    # Overdue first, then the rest by updated_at, newest first (FR-11 AC1).
    assert titles == [
        "**[Overdue Match](https://www.arbeitsagentur.de/jobsuche/jobdetail/B-2-S)**",
        "**[No Date Match](https://www.arbeitsagentur.de/jobsuche/jobdetail/C-3-S)**",
        "**[Strong Match](https://www.arbeitsagentur.de/jobsuche/jobdetail/A-1-S)**",
    ]
    assert any("Overdue" in str(m.value) for m in at.markdown)
    assert any("worth a follow-up call" in str(c.value) for c in at.caption)


# ---------------------------------------------------------------------------
# Changing status (FR-11 AC2): row updates in SQLite, created_at unchanged
# ---------------------------------------------------------------------------


def test_changing_status_updates_sqlite_and_keeps_created_at(db_path: str) -> None:
    _seed_three_entries(db_path)
    at = new_app()
    at.run()
    assert not at.exception

    at.selectbox(key="status_A-1-S").set_value("applied").run()
    assert not at.exception

    conn = storage.get_connection(db_path)
    entry = storage.get_tracker_entry(conn, "alex", "A-1-S")
    assert entry is not None
    assert entry.status == "applied"
    assert entry.created_at == _CREATED_AT


# ---------------------------------------------------------------------------
# Delete needs a second click to confirm (FR-11 AC2)
# ---------------------------------------------------------------------------


def test_delete_requires_a_second_click_to_confirm(db_path: str) -> None:
    _seed_three_entries(db_path)
    at = new_app()
    at.run()

    at.button(key="delete_C-3-S").click().run()
    assert not at.exception
    assert any("Delete this entry?" in str(w.value) for w in at.warning)

    conn = storage.get_connection(db_path)
    assert storage.get_tracker_entry(conn, "alex", "C-3-S") is not None  # not deleted yet

    at.button(key="delete_yes_C-3-S").click().run()
    assert not at.exception
    assert storage.get_tracker_entry(conn, "alex", "C-3-S") is None


def test_delete_cancel_keeps_the_row(db_path: str) -> None:
    _seed_three_entries(db_path)
    at = new_app()
    at.run()

    at.button(key="delete_C-3-S").click().run()
    at.button(key="delete_cancel_C-3-S").click().run()
    assert not at.exception

    conn = storage.get_connection(db_path)
    assert storage.get_tracker_entry(conn, "alex", "C-3-S") is not None


# ---------------------------------------------------------------------------
# Empty state (no entries saved yet)
# ---------------------------------------------------------------------------


def test_empty_state_renders_a_hint(db_path: str) -> None:
    at = new_app()
    at.run()

    assert not at.exception
    assert any("save a listing from the shortlist" in str(c.value) for c in at.caption)
