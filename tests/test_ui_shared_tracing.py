"""Unit tests for ``ui_shared.build_run_callbacks`` (FR-18 AC1, spec §9.5, D-18).

Plain unit tests, not ``AppTest`` - ``st.session_state`` works outside a real
script run too (Streamlit's "bare mode"), which is enough here since these
tests only read/write it directly and never render a widget. No test reaches
LangSmith (CLAUDE.md invariant 5): ``ui_shared.get_langsmith_client`` and
``job_hunt_agent.tracing.build_tracer`` are monkeypatched.

Related: FR-18 AC1, spec §8, §9.5, D-18, NFR-05
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ui_shared  # noqa: E402
from job_hunt_agent import tracing  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_tracing_session_state() -> None:
    st.session_state.pop(ui_shared.LANGSMITH_TRACING_KEY, None)


def test_no_callbacks_when_tracing_is_off() -> None:
    st.session_state[ui_shared.LANGSMITH_TRACING_KEY] = False
    assert ui_shared.build_run_callbacks("thread-1", demo_mode=True) == []


def test_no_callbacks_when_tracing_defaults_off() -> None:
    assert ui_shared.build_run_callbacks("thread-1", demo_mode=True) == []


def test_no_callbacks_when_the_client_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """No key (or any other client-build failure, spec §8) -> no tracer, no crash."""
    st.session_state[ui_shared.LANGSMITH_TRACING_KEY] = True
    monkeypatch.setattr(ui_shared, "get_langsmith_client", lambda: None)
    assert ui_shared.build_run_callbacks("thread-1", demo_mode=True) == []


def test_no_callbacks_when_tracer_construction_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """spec §8: a tracer build failure is swallowed, never raised to the caller."""
    st.session_state[ui_shared.LANGSMITH_TRACING_KEY] = True
    monkeypatch.setattr(ui_shared, "get_langsmith_client", lambda: object())
    monkeypatch.setattr(tracing, "build_tracer", lambda *args, **kwargs: None)
    assert ui_shared.build_run_callbacks("thread-1", demo_mode=True) == []


def test_tracer_attached_when_tracing_is_on_and_usable(monkeypatch: pytest.MonkeyPatch) -> None:
    st.session_state[ui_shared.LANGSMITH_TRACING_KEY] = True
    client_sentinel = object()
    captured: dict[str, Any] = {}

    def _fake_build_tracer(client: Any, **kwargs: Any) -> Any:
        captured["client"] = client
        captured.update(kwargs)
        return "tracer-object"

    monkeypatch.setattr(ui_shared, "get_langsmith_client", lambda: client_sentinel)
    monkeypatch.setattr(tracing, "build_tracer", _fake_build_tracer)

    result = ui_shared.build_run_callbacks("thread-1", demo_mode=True, scenario="S1")

    assert result == ["tracer-object"]
    assert captured == {
        "client": client_sentinel,
        "demo_mode": True,
        "thread_id": "thread-1",
        "scenario": "S1",
    }
