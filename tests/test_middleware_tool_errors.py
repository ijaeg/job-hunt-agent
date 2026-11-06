"""Tests for ``middleware.tool_errors`` (FR-21 AC3, spec §5.4 #6).

Related: FR-21 AC3, spec §8
"""

from __future__ import annotations

import json
from typing import Any

from conftest import ScriptedModel
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from job_hunt_agent.middleware.tool_errors import tool_error_middleware


@tool
def flaky_tool(should_fail: bool) -> str:
    """Raises on demand (test double, not a real tool)."""
    if should_fail:
        raise RuntimeError("boom")
    return "ok"


def _run(should_fail: bool) -> ToolMessage:
    agent = create_agent(
        model=ScriptedModel(
            [[{"name": "flaky_tool", "args": {"should_fail": should_fail}}], "done"]
        ),
        tools=[flaky_tool],
        middleware=[tool_error_middleware],
        checkpointer=InMemorySaver(),
    )
    result: dict[str, Any] = agent.invoke(
        {"messages": [HumanMessage("go")]}, config={"configurable": {"thread_id": "t1"}}
    )
    return next(m for m in result["messages"] if isinstance(m, ToolMessage))


def test_tool_error_middleware_converts_an_exception_to_not_applicable_reason() -> None:
    """FR-21 AC3 / CLAUDE.md invariant 7: an unexpected exception never raises into the UI."""
    message = _run(should_fail=True)
    assert message.status == "error"
    content = json.loads(message.content)
    assert content["result"] is None
    assert "RuntimeError" in content["not_applicable_reason"]


def test_tool_error_middleware_leaves_a_successful_call_untouched() -> None:
    message = _run(should_fail=False)
    assert message.status != "error"
    assert message.content == "ok"
