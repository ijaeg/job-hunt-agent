"""AppTest integration tests for user selection (D-16), driven through app.py.

Mirrors ``tests/test_app.py``'s pattern: a scripted model
(``JOB_HUNT_FAKE_MODEL=1``), no network call, no API key needed (CLAUDE.md
invariant 5, NFR-05).

Related: FR-14, D-16, NFR-05
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from job_hunt_agent import storage
from job_hunt_agent.models import Profile

APP_PATH = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture(autouse=True)
def _fake_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOB_HUNT_FAKE_MODEL", "1")


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    path = str(tmp_path / f"wp08-user-{uuid.uuid4().hex}.sqlite")
    monkeypatch.setenv("DB_PATH", path)
    return path


def new_app(user_id: str | None = None) -> AppTest:
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.session_state["_scripted_turns"] = []
    if user_id:
        at.query_params["user"] = user_id
    return at


def _save_profile(db_path: str, user_id: str) -> None:
    conn = storage.get_connection(db_path)
    storage.save_profile(
        conn,
        user_id,
        Profile(
            skills=["Java"],
            seniority="mid",
            location="Berlin",
            radius_km=15,
            remote_preference="onsite",
            german_level="fluent",
            english_level="fluent",
        ),
    )


# ---------------------------------------------------------------------------
# Default on first start (D-16)
# ---------------------------------------------------------------------------


def test_default_user_is_alex_with_the_demo_profile(db_path: str) -> None:
    at = new_app()
    at.run()

    assert not at.exception
    assert at.query_params["user"] == "alex"
    conn = storage.get_connection(db_path)
    assert storage.load_profile(conn, "alex") is not None
    assert at.chat_input  # the chat renders - alex always has a profile


# ---------------------------------------------------------------------------
# A user without a profile sees the hint, not the chat (WP-08 goal 2)
# ---------------------------------------------------------------------------


def test_user_without_a_profile_sees_a_hint_not_the_chat(db_path: str) -> None:
    at = new_app("brand-new-user")
    at.run()

    assert not at.exception
    assert any("no profile yet" in str(i.value) for i in at.info)
    assert not at.chat_input
    conn = storage.get_connection(db_path)
    assert storage.load_profile(conn, "brand-new-user") is None  # nothing seeded silently


# ---------------------------------------------------------------------------
# Switching to an existing user (D-16)
# ---------------------------------------------------------------------------


def test_switching_to_an_existing_user_shows_their_own_chat(db_path: str) -> None:
    _save_profile(db_path, "sam")
    at = new_app("alex")
    at.run()
    previous_thread_id = at.query_params["thread_id"]

    at.selectbox(key="user_select").set_value("sam").run()

    assert not at.exception
    assert at.query_params["user"] == "sam"
    assert at.chat_input  # sam has a profile, so the chat renders
    # Switching users opens a new empty thread (D-16).
    assert at.query_params["thread_id"] != previous_thread_id


# ---------------------------------------------------------------------------
# Adding a new user (D-16)
# ---------------------------------------------------------------------------


def test_adding_a_new_user_selects_its_slug_and_shows_the_hint(db_path: str) -> None:
    at = new_app("alex")
    at.run()

    at.text_input(key="new_user_name").set_value("Jane Doe").run()
    at.button(key="add_user_button").click().run()

    assert not at.exception
    assert at.query_params["user"] == "jane-doe"
    assert any("no profile yet" in str(i.value) for i in at.info)


def test_adding_a_user_with_an_invalid_name_shows_a_message(db_path: str) -> None:
    at = new_app("alex")
    at.run()

    at.text_input(key="new_user_name").set_value("sam@example.com").run()
    at.button(key="add_user_button").click().run()

    assert not at.exception
    assert any("Name may only contain" in str(e.value) for e in at.error)
    assert at.query_params["user"] == "alex"  # selection unchanged


# ---------------------------------------------------------------------------
# Per-user isolation of threads (D-15, FR-13 AC2)
# ---------------------------------------------------------------------------


def test_each_user_sees_only_their_own_threads(db_path: str) -> None:
    _save_profile(db_path, "sam")
    conn = storage.get_connection(db_path)
    _touch_now(conn, "alex", "alex-thread", "alex's search")
    _touch_now(conn, "sam", "sam-thread", "sam's search")

    at = new_app("sam")
    at.run()

    assert not at.exception
    captions = [str(c.value) for c in at.caption]
    assert "sam's search" in captions
    assert "alex's search" not in captions


def _touch_now(conn: Any, user_id: str, thread_id: str, title: str) -> None:
    storage.touch_thread(conn, user_id, thread_id, title, datetime.now(UTC))
