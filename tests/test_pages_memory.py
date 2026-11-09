"""AppTest integration tests for pages/2_Memory.py (FR-15 AC3).

Mirrors ``tests/test_pages_tracker.py``'s pattern: no network call, no API
key needed (CLAUDE.md invariant 5, NFR-05) - this page never touches the
agent or the model at all.

Related: FR-15 AC3, FR-15 AC4, NFR-05
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from job_hunt_agent import storage

PAGE_PATH = str(Path(__file__).resolve().parents[1] / "pages" / "2_Memory.py")


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    path = str(tmp_path / f"wp07-{uuid.uuid4().hex}.sqlite")
    monkeypatch.setenv("DB_PATH", path)
    return path


def _seed_two_memories(db_path: str) -> None:
    conn = storage.get_connection(db_path)
    store = storage.get_store(conn)
    store.put(("memories", "alex"), "k1", {"kind": "excluded_employer", "value": "Acme GmbH"})
    store.put(("memories", "alex"), "k2", {"kind": "preference", "value": "remote only"})


def new_app() -> AppTest:
    return AppTest.from_file(PAGE_PATH, default_timeout=30)


# ---------------------------------------------------------------------------
# Items render (FR-15 AC3)
# ---------------------------------------------------------------------------


def test_items_render_kind_and_value(db_path: str) -> None:
    _seed_two_memories(db_path)
    at = new_app()
    at.run()

    assert not at.exception
    texts = [str(m.value) for m in at.markdown]
    assert any("Excluded employer" in t and "Acme GmbH" in t for t in texts)
    assert any("Preference" in t and "remote only" in t for t in texts)


# ---------------------------------------------------------------------------
# Delete needs a second click to confirm (FR-15 AC3)
# ---------------------------------------------------------------------------


def test_delete_requires_a_second_click_to_confirm(db_path: str) -> None:
    _seed_two_memories(db_path)
    at = new_app()
    at.run()

    at.button(key="delete_k1").click().run()
    assert not at.exception
    assert any("Delete this memory?" in str(w.value) for w in at.warning)

    conn = storage.get_connection(db_path)
    assert len(storage.list_memories(conn, "alex")) == 2  # not deleted yet

    at.button(key="delete_yes_k1").click().run()
    assert not at.exception
    remaining = storage.list_memories(conn, "alex")
    assert len(remaining) == 1
    assert remaining[0]["key"] == "k2"


def test_delete_cancel_keeps_the_item(db_path: str) -> None:
    _seed_two_memories(db_path)
    at = new_app()
    at.run()

    at.button(key="delete_k1").click().run()
    at.button(key="delete_cancel_k1").click().run()
    assert not at.exception

    conn = storage.get_connection(db_path)
    assert len(storage.list_memories(conn, "alex")) == 2


# ---------------------------------------------------------------------------
# Empty state (no memories saved yet)
# ---------------------------------------------------------------------------


def test_empty_state_renders_a_hint(db_path: str) -> None:
    at = new_app()
    at.run()

    assert not at.exception
    assert any("ask the agent" in str(c.value) for c in at.caption)
