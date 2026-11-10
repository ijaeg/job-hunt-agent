"""Shared test helpers: a scripted chat model and a minimal tool-testing agent.

Mirrors the pattern proven in ``spikes/hitl_app.py``/``spikes/test_hitl_app.py``
(D-5): a model that pops pre-scripted turns instead of calling a real API, so
every test here is network-free (CLAUDE.md invariant 5, NFR-05).

Related: NFR-05, D-5
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from job_hunt_agent import ba_client
from job_hunt_agent.context import AgentContext
from job_hunt_agent.state import JobHuntState

#: Default thread id for tests that don't care about a specific value.
TEST_THREAD_ID = "test-thread"


@pytest.fixture(autouse=True)
def _stub_ba_reachability_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every AppTest run of ``app.py``/the developer settings page triggers
    ``ensure_developer_settings_initialized()``'s once-per-session BA
    reachability check (FR-19 AC3) unless demo mode is already in session
    state - this global, autouse stub keeps every test network-free (CLAUDE.md
    invariant 5) without every test file having to remember its own.
    ``tests/test_ba_client.py`` tests ``check_reachable`` itself directly
    (imported by name, unaffected by this attribute patch) with its own
    ``httpx.MockTransport``.
    """
    monkeypatch.setattr(ba_client, "check_reachable", lambda *args, **kwargs: True)


class ScriptedModel:
    """Deterministic chat model stand-in: pops one scripted turn per call.

    A turn is either a plain string (a final ``AIMessage``) or a list of
    ``{"name": ..., "args": ...}`` dicts (one or more tool calls on a
    single ``AIMessage``, for parallel-tool-call scenarios).
    """

    def __init__(self, turns: list[Any]) -> None:
        self.turns = list(turns)

    def bind_tools(self, _tools: Any, **_kwargs: Any) -> ScriptedModel:
        return self

    def bind(self, **_kwargs: Any) -> ScriptedModel:
        """Used when the agent has no tools (binds model settings only)."""
        return self

    def invoke(self, _messages: list[BaseMessage], **_kwargs: Any) -> AIMessage:
        if not self.turns:
            return AIMessage(content="(scripted model: no more turns)")
        spec = self.turns.pop(0)
        if isinstance(spec, str):
            return AIMessage(content=spec)
        tool_calls = [
            {"name": call["name"], "args": call["args"], "id": f"call_{i}_{call['name']}"}
            for i, call in enumerate(spec)
        ]
        return AIMessage(content="", tool_calls=tool_calls)


def run_tool_turn(
    tools: list[Any],
    turns: list[Any],
    context: AgentContext,
    *,
    initial_state: dict[str, Any] | None = None,
    thread_id: str = TEST_THREAD_ID,
    middleware: list[Any] | None = None,
    store: Any = None,
    checkpointer: Any = None,
    human_message: str = "(test input)",
) -> dict[str, Any]:
    """Builds a minimal agent with the given tools/middleware, runs one turn.

    Args:
        tools: Tools available to the scripted model.
        turns: Pre-scripted model turns (see :class:`ScriptedModel`).
        context: The ``AgentContext`` for this run.
        initial_state: Extra state fields to seed (e.g. ``seen_refs``).
        thread_id: Thread id for the checkpointer.
        middleware: Agent middleware, in the order ``create_agent`` should
            apply them.
        store: Long-term memory store (``ToolRuntime.store``), if needed.
        checkpointer: A pre-built checkpointer, e.g. to resume a thread
            across two separate ``run_tool_turn`` calls; defaults to a
            fresh ``InMemorySaver`` (so this helper alone cannot test
            "resume after restart" - callers needing that build and reuse
            their own checkpointer explicitly).
        human_message: The user message for this turn.

    Returns:
        The final graph state after this turn (including any interrupt).
    """
    agent = create_agent(
        model=ScriptedModel(turns),
        tools=tools,
        state_schema=JobHuntState,
        context_schema=AgentContext,
        middleware=middleware or [],
        checkpointer=checkpointer or InMemorySaver(),
        store=store,
    )
    state = {"messages": [HumanMessage(human_message)], **(initial_state or {})}
    return agent.invoke(state, config={"configurable": {"thread_id": thread_id}}, context=context)
