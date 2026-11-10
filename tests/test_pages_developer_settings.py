"""AppTest integration tests for pages/4_Developer_settings.py (FR-18 AC1, FR-18 AC2).

Mirrors ``tests/test_pages_tracker.py``'s pattern: no network call, no API
key needed (CLAUDE.md invariant 5, NFR-05) - the reachability check
(FR-19 AC3) is stubbed via ``ui_shared.ensure_developer_settings_initialized``'s
``reachability_check`` parameter, never the real BA API.

Related: FR-18 AC1, FR-18 AC2, FR-19 AC3, D-17, NFR-05
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

PAGE_PATH = str(Path(__file__).resolve().parents[1] / "pages" / "4_Developer_settings.py")
APP_PATH = str(Path(__file__).resolve().parents[1] / "app.py")

#: conftest.py's autouse ``_stub_ba_reachability_check`` stubs the page's own
#: ``ensure_developer_settings_initialized()`` call for every test here too.


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    path = str(tmp_path / f"wp09-settings-{uuid.uuid4().hex}.sqlite")
    monkeypatch.setenv("DB_PATH", path)
    return path


def new_app() -> AppTest:
    return AppTest.from_file(PAGE_PATH, default_timeout=30)


def _selectbox(at: AppTest, label: str):  # type: ignore[no-untyped-def]
    return next(sb for sb in at.selectbox if sb.label == label)


def _toggle(at: AppTest, label: str):  # type: ignore[no-untyped-def]
    return next(tg for tg in at.toggle if tg.label == label)


# ---------------------------------------------------------------------------
# Defaults (FR-18 AC1)
# ---------------------------------------------------------------------------


def test_defaults_come_from_config(db_path: str) -> None:
    from job_hunt_agent import config

    at = new_app()
    at.run()

    assert not at.exception
    assert _selectbox(at, "Chat model").value == config.CHAT_MODEL
    assert _selectbox(at, "Reasoning effort").value == config.REASONING_EFFORT
    assert _toggle(at, "Enable get_job_details tool").value is True


# ---------------------------------------------------------------------------
# Changing a setting persists in session state (FR-18 AC1)
# ---------------------------------------------------------------------------


def test_changing_model_and_effort_persists_in_session_state(db_path: str) -> None:
    from ui_shared import CHAT_MODEL_KEY, REASONING_EFFORT_KEY

    at = new_app()
    at.run()
    _selectbox(at, "Chat model").select("anthropic/claude-haiku-4.5").run()
    _selectbox(at, "Reasoning effort").select("high").run()

    assert not at.exception
    assert at.session_state[CHAT_MODEL_KEY] == "anthropic/claude-haiku-4.5"
    assert at.session_state[REASONING_EFFORT_KEY] == "high"


def test_disabling_get_job_details_persists_in_session_state(db_path: str) -> None:
    from ui_shared import GET_JOB_DETAILS_ENABLED_KEY

    at = new_app()
    at.run()
    _toggle(at, "Enable get_job_details tool").set_value(False).run()

    assert not at.exception
    assert at.session_state[GET_JOB_DETAILS_ENABLED_KEY] is False


def test_toggling_demo_mode_persists_in_session_state(db_path: str) -> None:
    from ui_shared import DEMO_MODE_KEY

    at = new_app()
    at.run()
    before = at.session_state[DEMO_MODE_KEY]
    _toggle(at, "Demo mode").set_value(not before).run()

    assert not at.exception
    assert at.session_state[DEMO_MODE_KEY] is not before


# ---------------------------------------------------------------------------
# A setting survives switching pages (Addendum 1 to WP-09)
# ---------------------------------------------------------------------------


def test_chat_model_survives_switching_to_the_main_page_and_back(
    db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression test for Addendum 1 to WP-09's bug: a widget bound directly
    to ``CHAT_MODEL_KEY`` loses that session-state entry whenever a run
    doesn't render the widget - exactly what happens visiting ``app.py``
    between two visits to this page - and
    ``ensure_developer_settings_initialized()``'s ``setdefault`` then quietly
    resets it to ``config.CHAT_MODEL``. The fix moves the setting onto a key
    no widget owns (``ui_shared.sync_setting_from_widget``), so it must
    survive the round trip through the main page unchanged.
    """
    from ui_shared import CHAT_MODEL_KEY

    monkeypatch.setenv("JOB_HUNT_FAKE_MODEL", "1")

    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception

    at.switch_page("pages/4_Developer_settings.py")
    at.run()
    assert not at.exception
    _selectbox(at, "Chat model").select("anthropic/claude-haiku-4.5").run()
    assert at.session_state[CHAT_MODEL_KEY] == "anthropic/claude-haiku-4.5"

    at.switch_page("app.py")
    at.run()
    assert not at.exception
    assert at.session_state[CHAT_MODEL_KEY] == "anthropic/claude-haiku-4.5"

    at.switch_page("pages/4_Developer_settings.py")
    at.run()
    assert not at.exception
    assert at.session_state[CHAT_MODEL_KEY] == "anthropic/claude-haiku-4.5"
    assert _selectbox(at, "Chat model").value == "anthropic/claude-haiku-4.5"


# ---------------------------------------------------------------------------
# Automatic demo mode message (FR-19 AC3)
# ---------------------------------------------------------------------------


def test_shows_the_auto_demo_mode_message_when_api_was_unreachable(db_path: str) -> None:
    from ui_shared import DEMO_MODE_AUTO_MESSAGE_KEY, DEMO_MODE_KEY

    at = new_app()
    # Simulates what app.py's ensure_developer_settings_initialized() would
    # have already written this session, had the BA API been unreachable at
    # start-up (FR-19 AC3) - this page never performs the check itself.
    at.session_state[DEMO_MODE_KEY] = True
    at.session_state[DEMO_MODE_AUTO_MESSAGE_KEY] = "Demo mode was switched on automatically: x"
    at.run()

    assert not at.exception
    assert any("switched on automatically" in str(i.value) for i in at.info)


def test_the_page_itself_switches_on_demo_mode_when_the_api_is_unreachable(
    db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-19 AC3, end to end through ``ensure_developer_settings_initialized``
    itself: overrides conftest.py's autouse "always reachable" stub for this
    one test only, so the "unreachable" branch is actually exercised."""
    from job_hunt_agent import ba_client
    from ui_shared import DEMO_MODE_KEY

    monkeypatch.setattr(ba_client, "check_reachable", lambda *args, **kwargs: False)
    at = new_app()
    at.run()

    assert not at.exception
    assert at.session_state[DEMO_MODE_KEY] is True
    assert any("reachable at start-up" in str(i.value) for i in at.info)


# ---------------------------------------------------------------------------
# Token usage and cost this session (FR-18 AC2)
# ---------------------------------------------------------------------------


def test_renders_cost_unavailable_when_no_calls_yet(db_path: str) -> None:
    at = new_app()
    at.run()

    assert not at.exception
    captions = [str(c.value) for c in at.caption]
    assert any("no model calls yet" in c for c in captions)


def test_renders_session_usage_totals(db_path: str) -> None:
    from job_hunt_agent import usage

    at = new_app()
    at.session_state["session_usage_agent_loop"] = [
        usage.LlmUsage("openai/gpt-5-mini", 100, 50, 0, 0.002)
    ]
    at.session_state["session_usage_extraction"] = [
        usage.LlmUsage("openai/gpt-5-mini", 200, 80, 0, 0.004)
    ]
    at.run()

    assert not at.exception
    captions = " ".join(str(c.value) for c in at.caption)
    assert "300" in captions  # combined prompt tokens
    assert "$0.0060" in captions  # combined cost
