"""Tool error handling (spec §5.4 #6, FR-21 AC3): exceptions -> ``not_applicable_reason``.

Each tool already converts its own *expected* failures (a bad argument, a
BA API error) into a ``ToolResult.not_applicable_reason`` without raising.
This middleware is the last-resort backstop for anything a tool did *not*
anticipate (a bug, an unexpected exception type) - so that CLAUDE.md
invariant 7 ("no stack trace in the UI") holds even then.

Related: FR-21 AC3, spec §5.4 #6, §8
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain.agents.middleware import wrap_tool_call
from langchain_core.messages import ToolMessage
from langgraph.errors import GraphBubbleUp

from job_hunt_agent.models import ToolResult

if TYPE_CHECKING:
    from collections.abc import Callable

    from langchain.agents.middleware import ToolCallRequest


@wrap_tool_call
def tool_error_middleware(
    request: ToolCallRequest, handler: Callable[[ToolCallRequest], Any]
) -> Any:
    """Catches any exception a tool call did not already handle itself.

    Langgraph control-flow signals (interrupts, parent commands) must
    propagate - never caught here, matching the built-in
    ``ToolErrorMiddleware``'s own rule.

    Related: FR-21 AC3, spec §8
    """
    try:
        return handler(request)
    except GraphBubbleUp:
        raise
    except Exception as exc:  # noqa: BLE001 - last-resort backstop, never raise into the UI
        tool_name = request.tool.name if request.tool else request.tool_call["name"]
        result = ToolResult(
            tool=tool_name, not_applicable_reason=f"Unexpected error: {type(exc).__name__}."
        )
        return ToolMessage(
            content=result.model_dump_json(),
            tool_call_id=request.tool_call["id"],
            name=tool_name,
            status="error",
        )
