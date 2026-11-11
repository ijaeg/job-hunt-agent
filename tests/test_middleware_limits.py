"""Tests for :mod:`job_hunt_agent.middleware.limits` (FR-20 AC1, FR-03 AC2, D-19).

Related: FR-20 AC1, FR-03 AC2, spec §5.3, D-19
"""

from __future__ import annotations

from typing import Any

from conftest import run_tool_turn

from job_hunt_agent import config
from job_hunt_agent.context import AgentContext
from job_hunt_agent.middleware.limits import SearchCallLimitMiddleware
from job_hunt_agent.models import JobSummary, Profile
from job_hunt_agent.tools.search import search_jobs


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
    def __init__(self) -> None:
        self.calls = 0

    def search(self, *args: Any, **kwargs: Any) -> tuple[list[JobSummary], int, list[str]]:
        self.calls += 1
        return [JobSummary(referenznummer=f"REF-{self.calls}-S", title="Python Dev")], 1, []

    def get_details(self, referenznummer: str) -> Any:
        raise NotImplementedError


def _context(source: FakeSource) -> AgentContext:
    return AgentContext(job_source=source, profile=_profile(), extraction_model=None, conn=None)


def _search_call(keywords: str = "Python", location: str = "Hamburg") -> dict[str, Any]:
    return {"name": "search_jobs", "args": {"keywords": keywords, "location": location}}


def test_four_parallel_search_calls_in_one_step_run_only_three() -> None:
    """FR-20 AC1: 4 calls proposed in one step, with none run before - only 3 run."""
    source = FakeSource()
    result = run_tool_turn(
        [search_jobs],
        [[_search_call()] * 4, "done"],
        _context(source),
        middleware=[SearchCallLimitMiddleware()],
    )
    assert source.calls == config.MAX_SEARCH_CALLS_PER_MESSAGE
    assert len(result["seen_refs"]) == config.MAX_SEARCH_CALLS_PER_MESSAGE
    ai_messages = [m for m in result["messages"] if m.__class__.__name__ == "AIMessage"]
    pruned = next(m for m in ai_messages if len(m.tool_calls) < 4)
    assert len(pruned.tool_calls) == config.MAX_SEARCH_CALLS_PER_MESSAGE
    assert "limit" in str(pruned.content).lower()


def test_two_more_after_two_already_run_this_message_only_one_more_runs() -> None:
    """FR-20 AC1: 2 earlier (sequential) calls + 2 parallel calls in one message -> 1 more runs."""
    source = FakeSource()
    run_tool_turn(
        [search_jobs],
        [
            [_search_call()],
            [_search_call()],
            [_search_call(), _search_call()],
            "done",
        ],
        _context(source),
        middleware=[SearchCallLimitMiddleware()],
    )
    assert source.calls == config.MAX_SEARCH_CALLS_PER_MESSAGE


def test_new_user_message_resets_the_limit() -> None:
    """FR-20 AC1 / FR-03 AC2: a fresh ``HumanMessage`` gets a fresh budget of 3."""
    from langchain.agents import create_agent
    from langchain_core.messages import HumanMessage
    from langgraph.checkpoint.memory import InMemorySaver

    from job_hunt_agent.state import JobHuntState

    source = FakeSource()
    model_turns = [
        [_search_call()] * 3,
        "done 1",
        [_search_call()] * 3,
        "done 2",
    ]
    from conftest import ScriptedModel

    agent = create_agent(
        model=ScriptedModel(model_turns),
        tools=[search_jobs],
        state_schema=JobHuntState,
        context_schema=AgentContext,
        middleware=[SearchCallLimitMiddleware()],
        checkpointer=InMemorySaver(),
    )
    cfg = {"configurable": {"thread_id": "t1"}}
    ctx = _context(source)
    agent.invoke({"messages": [HumanMessage("find jobs")]}, config=cfg, context=ctx)
    assert source.calls == 3
    agent.invoke({"messages": [HumanMessage("find more jobs")]}, config=cfg, context=ctx)
    assert source.calls == 6
