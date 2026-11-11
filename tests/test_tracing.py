"""Unit tests for ``job_hunt_agent.tracing`` (spec §8, §9.5, D-18).

No test reaches LangSmith (CLAUDE.md invariant 5): every ``Client``/
``LangChainTracer`` construction is monkeypatched at the same module-level
seam ``tracing.py`` itself calls through.

Related: FR-18 AC1, spec §8, §9.5, D-18, NFR-05
"""

from __future__ import annotations

from typing import Any

import pytest

from job_hunt_agent import config, tracing


@pytest.fixture(autouse=True)
def _no_real_langsmith_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """The local machine's real ``LANGSMITH_API_KEY`` must never leak into a
    test; every test that needs a key sets its own fake one."""
    monkeypatch.delenv(config.LANGSMITH_API_KEY_ENV, raising=False)


# ---------------------------------------------------------------------------
# langsmith_key_present
# ---------------------------------------------------------------------------


def test_langsmith_key_present_is_false_without_a_key() -> None:
    assert tracing.langsmith_key_present() is False


def test_langsmith_key_present_is_false_for_a_blank_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(config.LANGSMITH_API_KEY_ENV, "   ")
    assert tracing.langsmith_key_present() is False


def test_langsmith_key_present_is_true_with_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(config.LANGSMITH_API_KEY_ENV, "fake-key")
    assert tracing.langsmith_key_present() is True


# ---------------------------------------------------------------------------
# build_client
# ---------------------------------------------------------------------------


def test_build_client_returns_none_without_a_key() -> None:
    assert tracing.build_client() is None


def test_build_client_returns_none_when_construction_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """spec §8: a tracing failure (here: an unreachable LangSmith) never raises."""
    monkeypatch.setenv(config.LANGSMITH_API_KEY_ENV, "fake-key")

    def _raise(**kwargs: Any) -> Any:
        raise RuntimeError("network unreachable")

    monkeypatch.setattr(tracing, "Client", _raise)
    assert tracing.build_client() is None


def test_build_client_returns_the_client_when_it_builds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(config.LANGSMITH_API_KEY_ENV, "fake-key")
    sentinel = object()
    captured: dict[str, Any] = {}

    def _fake_client(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(tracing, "Client", _fake_client)

    assert tracing.build_client() is sentinel
    assert captured["api_url"] == config.LANGSMITH_ENDPOINT
    assert captured["api_key"] == "fake-key"
    assert captured["timeout_ms"] == config.LANGSMITH_CLIENT_TIMEOUT_SECONDS * 1000


# ---------------------------------------------------------------------------
# build_tracer
# ---------------------------------------------------------------------------


def test_build_tracer_returns_none_without_a_client() -> None:
    assert tracing.build_tracer(None, demo_mode=True, thread_id="t1") is None


def test_build_tracer_returns_none_when_construction_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(**kwargs: Any) -> Any:
        raise RuntimeError("boom")

    monkeypatch.setattr(tracing, "LangChainTracer", _raise)
    assert tracing.build_tracer(object(), demo_mode=True, thread_id="t1") is None


def test_build_tracer_tags_demo_and_scenario(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def _fake_tracer(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return "tracer"

    monkeypatch.setattr(tracing, "LangChainTracer", _fake_tracer)
    result = tracing.build_tracer(object(), demo_mode=True, thread_id="t1", scenario="S1")

    assert result == "tracer"
    assert captured["project_name"] == config.LANGSMITH_PROJECT
    assert captured["tags"] == ["demo", "S1"]
    assert captured["metadata"] == {"thread_id": "t1"}


def test_build_tracer_tags_live_without_a_scenario(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        tracing, "LangChainTracer", lambda **kwargs: captured.update(kwargs) or "tracer"
    )
    tracing.build_tracer(object(), demo_mode=False, thread_id="t2")
    assert captured["tags"] == ["live"]
