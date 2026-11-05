"""Automated checks for the D-5 HITL spike (`spikes/hitl_app.py`).

Uses `streamlit.testing.v1.AppTest` with the scripted model
(`HITL_FAKE_MODEL=1`) - no network call, no API key needed. Each test gets
its own SQLite file (`HITL_DB_PATH`), removed afterwards.

Not part of the package's coverage-tracked test suite (`pyproject.toml`
`testpaths` is `tests/`); run explicitly:
    uv run pytest spikes/test_hitl_app.py

Related: FR-10, spec §5.4 #4, NFR-06
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).resolve().parent / "hitl_app.py")


def _load_hitl_app_module() -> ModuleType:
    """Load hitl_app.py by path so its `st.cache_resource`-wrapped functions
    (keyed by source hash, not module identity) can be reached from the test.
    """
    spec = importlib.util.spec_from_file_location("hitl_app_under_test", APP_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _fake_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HITL_FAKE_MODEL", "1")


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    path = str(tmp_path / f"d5-{uuid.uuid4().hex}.sqlite")
    monkeypatch.setenv("HITL_DB_PATH", path)
    return path


def new_app(scripted_turns: list[Any]) -> AppTest:
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.session_state["_scripted_turns"] = scripted_turns
    return at


def test_approve_runs_the_tool(db_path: str) -> None:
    """Approving a gated proposal lets the tool run (FR-10 AC1)."""
    at = new_app(
        [
            [{"name": "save_item", "args": {"name": "widget", "note": "n1"}}],
            "Saved it.",
        ]
    )
    at.run()
    at.chat_input[0].set_value("please save the widget").run()
    assert not at.exception
    assert len(at.button) == 3  # Approve, Reject, Edit note

    at.button(key="approve").click().run()
    assert not at.exception
    assert len(at.button) == 0  # no more pending interrupt
    assert any("Saved it." in str(m.value) for m in at.markdown)


def test_reject_does_not_run_the_tool(db_path: str) -> None:
    """Rejecting a gated proposal never executes it (FR-10 AC3)."""
    at = new_app(
        [
            [{"name": "save_item", "args": {"name": "widget", "note": "n1"}}],
            "Understood, I will not save it.",
        ]
    )
    at.run()
    at.chat_input[0].set_value("please save the widget").run()
    at.button(key="reject").click().run()
    assert not at.exception
    assert len(at.button) == 0
    assert any("User rejected the tool call" in str(m.value) for m in at.caption)


def test_repeated_proposal_after_reject_is_dropped_without_a_second_interrupt(
    db_path: str,
) -> None:
    """The rejection lock drops a repeated identical proposal (FR-10 AC3, spec §5.4 #4).

    This is the central D-5 finding: `RejectionLockMiddleware` must be listed
    AFTER `HumanInTheLoopMiddleware` for its `after_model` to run first
    (after_model hooks run in reverse list order) and strip the repeat
    before HITL's own `after_model` would otherwise interrupt again.
    """
    at = new_app(
        [
            [{"name": "save_item", "args": {"name": "widget", "note": "n1"}}],
            # The model "misbehaves" and proposes the exact same call again -
            # this must be dropped by the lock, not re-interrupted.
            [{"name": "save_item", "args": {"name": "widget", "note": "n1"}}],
        ]
    )
    at.run()
    at.chat_input[0].set_value("please save the widget").run()
    assert len(at.button) == 3

    at.button(key="reject").click().run()
    # The scripted model immediately re-proposed the same call; the lock must
    # have stripped it before any second interrupt reached the UI.
    assert not at.exception
    assert len(at.button) == 0
    assert any("already rejected in this conversation" in str(m.value) for m in at.markdown)


def test_rerun_keeps_the_pending_interrupt(db_path: str) -> None:
    """A Streamlit rerun (`.run()` again, no new input) does not lose the interrupt."""
    at = new_app([[{"name": "save_item", "args": {"name": "widget", "note": "n1"}}]])
    at.run()
    at.chat_input[0].set_value("please save the widget").run()
    assert len(at.button) == 3

    at.run()  # simulate a rerun with no new user input
    assert not at.exception
    assert len(at.button) == 3  # still pending, same proposal


def test_restart_resumes_the_same_thread_from_sqlite(db_path: str) -> None:
    """A brand-new AppTest (simulated app restart) resumes the same thread (FR-13 AC3).

    Clears `get_connection`'s `st.cache_resource` cache so the second
    `AppTest` opens a genuinely fresh `sqlite3.Connection`, instead of
    reusing the first one still held by this process.
    """
    at1 = new_app([[{"name": "save_item", "args": {"name": "widget", "note": "n1"}}]])
    at1.run()
    at1.chat_input[0].set_value("please save the widget").run()
    assert len(at1.button) == 3

    hitl_app = _load_hitl_app_module()
    hitl_app.get_connection.clear()

    at2 = new_app([])  # no further replies queued; approving needs no new model call
    at2.run()
    assert not at2.exception
    assert len(at2.button) == 3  # the interrupt survived the simulated restart

    at2.button(key="approve").click().run()
    assert not at2.exception
    assert len(at2.button) == 0


def test_find_item_is_never_gated(db_path: str) -> None:
    """A read-only tool call never raises an interrupt."""
    at = new_app(
        [
            [{"name": "find_item", "args": {"query": "widget"}}],
            "It's a small plastic widget.",
        ]
    )
    at.run()
    at.chat_input[0].set_value("what is a widget?").run()
    assert not at.exception
    assert len(at.button) == 0
    assert any("widget" in str(m.value) for m in at.markdown)
