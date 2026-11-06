"""Tests for ``middleware.profile_context`` (FR-01 AC4, FR-03 AC1).

Related: FR-01 AC4, FR-03 AC1
"""

from __future__ import annotations

from typing import Any

from conftest import ScriptedModel, run_tool_turn
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from job_hunt_agent.context import AgentContext
from job_hunt_agent.middleware.profile_context import (
    LoadProfileContextMiddleware,
    profile_context_message,
)
from job_hunt_agent.models import Profile
from job_hunt_agent.state import JobHuntState


def _profile() -> Profile:
    return Profile(
        skills=["Python", "Java"],
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


def test_profile_context_message_mentions_key_profile_fields() -> None:
    message = profile_context_message(_profile())
    text = str(message.content)
    assert "Python" in text
    assert "senior" in text
    assert "25" in text
    assert message.name == "profile_context"


def test_load_profile_context_middleware_injects_once_on_first_turn() -> None:
    """The profile message appears after the very first model call of a thread."""
    result = run_tool_turn([], ["done"], _context(), middleware=[LoadProfileContextMiddleware()])
    contents = [str(m.content) for m in result["messages"]]
    assert any("Python" in c and "profile" in c.lower() for c in contents)
    # Exactly one profile-context message, not one per message in the thread.
    assert sum(1 for m in result["messages"] if getattr(m, "name", None) == "profile_context") == 1


def test_load_profile_context_middleware_does_not_repeat_on_a_later_turn() -> None:
    """A second user turn in the same thread does not get a second profile message."""
    agent = create_agent(
        model=ScriptedModel(["first reply", "second reply"]),
        tools=[],
        state_schema=JobHuntState,
        context_schema=AgentContext,
        middleware=[LoadProfileContextMiddleware()],
        checkpointer=InMemorySaver(),
    )
    cfg = {"configurable": {"thread_id": "t1"}}
    ctx = _context()

    agent.invoke({"messages": [HumanMessage("hi")]}, config=cfg, context=ctx)
    second_result = agent.invoke({"messages": [HumanMessage("again")]}, config=cfg, context=ctx)

    count = sum(
        1 for m in second_result["messages"] if getattr(m, "name", None) == "profile_context"
    )
    assert count == 1
