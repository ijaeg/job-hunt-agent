"""AppTest integration tests for pages/3_Profile.py (FR-14, D-16).

Mirrors ``tests/test_pages_tracker.py``'s pattern: no network call, no API
key needed (CLAUDE.md invariant 5, NFR-05) - this page never touches the
agent or the model at all.

Related: FR-14 AC1-AC3, D-16, NFR-05
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml
from streamlit.testing.v1 import AppTest

from job_hunt_agent import storage
from job_hunt_agent.models import Profile

PAGE_PATH = str(Path(__file__).resolve().parents[1] / "pages" / "3_Profile.py")

_DEMO_PROFILE_PATH = Path(__file__).resolve().parents[1] / "data" / "samples" / "profile_alex.yaml"


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    path = str(tmp_path / f"wp08-profile-{uuid.uuid4().hex}.sqlite")
    monkeypatch.setenv("DB_PATH", path)
    return path


def new_app(user_id: str = "alex") -> AppTest:
    at = AppTest.from_file(PAGE_PATH, default_timeout=30)
    at.query_params["user"] = user_id
    return at


def _text_input(at: AppTest, label: str) -> Any:
    return next(ti for ti in at.text_input if ti.label == label)


def _number_input(at: AppTest, label: str) -> Any:
    return next(ni for ni in at.number_input if ni.label == label)


def _button(at: AppTest, label: str) -> Any:
    return next(b for b in at.button if b.label == label)


# ---------------------------------------------------------------------------
# Renders the stored profile (FR-14 AC1)
# ---------------------------------------------------------------------------


def test_renders_the_stored_profile(db_path: str) -> None:
    conn = storage.get_connection(db_path)
    storage.save_profile(
        conn,
        "alex",
        Profile(
            skills=["Python", "Go"],
            seniority="senior",
            location="Hamburg",
            radius_km=30,
            remote_preference="remote",
            wants_full_time=False,
            wants_permanent=False,
            exclude_temp_agency=False,
            german_level="fluent",
            english_level="native",
        ),
    )
    at = new_app()
    at.run()

    assert not at.exception
    assert _text_input(at, "Skills (comma-separated)").value == "Python, Go"
    assert _text_input(at, "Location").value == "Hamburg"
    assert _number_input(at, "Search radius (km)").value == 30
    assert any(sb.value == "senior" for sb in at.selectbox)
    assert any(sb.value == "remote" for sb in at.selectbox)
    assert all(cb.value is False for cb in at.checkbox)


# ---------------------------------------------------------------------------
# No profile yet: the form still renders, with defaults (not an exception)
# ---------------------------------------------------------------------------


def test_renders_defaults_when_no_profile_is_stored(db_path: str) -> None:
    at = new_app("brand-new-user")
    at.run()

    assert not at.exception
    assert _text_input(at, "Skills (comma-separated)").value == ""
    assert _number_input(at, "Search radius (km)").value == 25


# ---------------------------------------------------------------------------
# Save updates SQLite (FR-14 AC1)
# ---------------------------------------------------------------------------


def test_save_updates_sqlite(db_path: str) -> None:
    at = new_app("brand-new-user")
    at.run()

    _text_input(at, "Skills (comma-separated)").set_value("Python, Rust")
    _text_input(at, "Location").set_value("Berlin")
    at.form_submit_button[0].click().run()

    assert not at.exception
    conn = storage.get_connection(db_path)
    saved = storage.load_profile(conn, "brand-new-user")
    assert saved is not None
    assert saved.skills == ["Python", "Rust"]
    assert saved.location == "Berlin"


# ---------------------------------------------------------------------------
# Invalid radius shows a friendly message, no exception (FR-14 AC1)
# ---------------------------------------------------------------------------


def test_invalid_radius_shows_a_message_not_an_exception(db_path: str) -> None:
    at = new_app("brand-new-user")
    at.run()

    _text_input(at, "Location").set_value("Berlin")
    _number_input(at, "Search radius (km)").set_value(1)  # below Profile's ge=5 (FR-14 AC1)
    at.form_submit_button[0].click().run()

    assert not at.exception
    assert any("Could not save the profile" in str(e.value) for e in at.error)
    conn = storage.get_connection(db_path)
    assert storage.load_profile(conn, "brand-new-user") is None


# ---------------------------------------------------------------------------
# "Load demo profile" stores the YAML values (FR-14 AC2)
# ---------------------------------------------------------------------------


def test_load_demo_profile_stores_the_yaml_values(db_path: str) -> None:
    at = new_app("brand-new-user")
    at.run()

    _button(at, "Load demo profile").click().run()

    assert not at.exception
    conn = storage.get_connection(db_path)
    saved = storage.load_profile(conn, "brand-new-user")
    assert saved is not None
    demo_data = yaml.safe_load(_DEMO_PROFILE_PATH.read_text(encoding="utf-8"))
    assert saved == Profile.model_validate(demo_data)
