"""Tests for ``middleware.memory_context`` (FR-15 AC2).

Related: FR-15 AC2
"""

from __future__ import annotations

from typing import Any

from conftest import ScriptedModel, run_tool_turn
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from job_hunt_agent.context import AgentContext
from job_hunt_agent.middleware.memory_context import (
    LoadMemoryContextMiddleware,
    memory_context_message,
)
from job_hunt_agent.middleware.profile_context import LoadProfileContextMiddleware
from job_hunt_agent.models import Profile
from job_hunt_agent.state import JobHuntState


def _profile() -> Profile:
    return Profile(
        skills=["Python"],
        seniority="senior",
        location="Hamburg",
        radius_km=25,
        remote_preference="hybrid",
        german_level="basic",
        english_level="native",
    )


class FakeSource:
    def search(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def get_details(self, referenznummer: str) -> Any:
        raise NotImplementedError


def _context() -> AgentContext:
    return AgentContext(
        job_source=FakeSource(), profile=_profile(), extraction_model=None, conn=None
    )


def test_memory_context_message_mentions_kind_and_value() -> None:
    message = memory_context_message([{"kind": "excluded_employer", "value": "Acme Staffing GmbH"}])
    text = str(message.content)
    assert "Acme Staffing GmbH" in text
    assert "Excluded employer" in text
    assert message.name == "memory_context"


def test_load_memory_context_middleware_injects_once_when_memories_exist() -> None:
    """A stored memory appears as one context message on the thread's first model call."""
    store = InMemoryStore()
    store.put(("memories", "alex"), "k1", {"kind": "excluded_employer", "value": "Acme GmbH"})
    result = run_tool_turn(
        [],
        ["done"],
        _context(),
        initial_state={"user_id": "alex"},
        middleware=[LoadMemoryContextMiddleware()],
        store=store,
    )
    contents = [str(m.content) for m in result["messages"]]
    assert any("Acme GmbH" in c for c in contents)
    assert sum(1 for m in result["messages"] if getattr(m, "name", None) == "memory_context") == 1


def test_load_memory_context_middleware_injects_nothing_when_no_memories_stored() -> None:
    """No stored memories at all -> no context message (not an empty one)."""
    store = InMemoryStore()
    result = run_tool_turn(
        [],
        ["done"],
        _context(),
        initial_state={"user_id": "alex"},
        middleware=[LoadMemoryContextMiddleware()],
        store=store,
    )
    assert not any(getattr(m, "name", None) == "memory_context" for m in result["messages"])


def test_load_memory_context_middleware_does_not_repeat_on_a_later_turn() -> None:
    """A second user turn in the same thread does not get a second memory message."""
    store = InMemoryStore()
    store.put(("memories", "alex"), "k1", {"kind": "preference", "value": "remote only"})
    agent = create_agent(
        model=ScriptedModel(["first reply", "second reply"]),
        tools=[],
        state_schema=JobHuntState,
        context_schema=AgentContext,
        middleware=[LoadMemoryContextMiddleware()],
        checkpointer=InMemorySaver(),
        store=store,
    )
    cfg = {"configurable": {"thread_id": "t1"}}
    ctx = _context()

    agent.invoke({"messages": [HumanMessage("hi")], "user_id": "alex"}, config=cfg, context=ctx)
    second_result = agent.invoke(
        {"messages": [HumanMessage("again")], "user_id": "alex"}, config=cfg, context=ctx
    )

    count = sum(
        1 for m in second_result["messages"] if getattr(m, "name", None) == "memory_context"
    )
    assert count == 1


def test_load_memory_context_middleware_isolates_memories_per_user() -> None:
    """A new thread for a different user_id only sees that user's own memories."""
    store = InMemoryStore()
    store.put(("memories", "alex"), "k1", {"kind": "preference", "value": "alex's pref"})
    result = run_tool_turn(
        [],
        ["done"],
        _context(),
        initial_state={"user_id": "sam"},
        middleware=[LoadMemoryContextMiddleware()],
        store=store,
        thread_id="sam-thread",
    )
    assert not any(getattr(m, "name", None) == "memory_context" for m in result["messages"])


def test_load_memory_context_middleware_still_injects_after_profile_context_middleware() -> None:
    """Regression: both "inject once" middlewares in agent.py's real order, together.

    Caught by the real-model check (scripts/wp07_memory_check.py), not by
    the tests above - each tested this middleware in isolation, so neither
    noticed that LoadProfileContextMiddleware (listed first in agent.py)
    prepends its own message before this one's before_model ever runs,
    making a naive len(messages) == 1 check miss the memory one entirely.
    """
    store = InMemoryStore()
    store.put(("memories", "alex"), "k1", {"kind": "excluded_employer", "value": "Acme GmbH"})
    result = run_tool_turn(
        [],
        ["done"],
        _context(),
        initial_state={"user_id": "alex"},
        middleware=[LoadProfileContextMiddleware(), LoadMemoryContextMiddleware()],
        store=store,
    )
    names = [getattr(m, "name", None) for m in result["messages"]]
    assert names.count("profile_context") == 1
    assert names.count("memory_context") == 1
