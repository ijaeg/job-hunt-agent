"""``remember`` tool (FR-15). Approval is middleware, not this tool's job.

Related: FR-15 AC1, FR-10, spec §6.1, D-6
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from langgraph.types import Command

from job_hunt_agent.context import AgentContext
from job_hunt_agent.models import ToolResult
from job_hunt_agent.state import JobHuntState
from job_hunt_agent.tools._common import tool_message

_VALID_KINDS = {"excluded_employer", "preference"}


def memory_key(kind: str, value: str) -> str:
    """Stable key for one memory item - saving the same item twice updates it, not duplicates."""
    return hashlib.sha256(f"{kind}:{value.strip().lower()}".encode()).hexdigest()[:16]


@tool
def remember(
    kind: str,
    value: str,
    runtime: ToolRuntime[AgentContext, JobHuntState],
) -> Command:
    """Stores a preference or an excluded employer for future sessions.

    This call is gated by approval outside the conversation - propose it
    directly when the user asks to be reminded of a preference or to never
    see a given employer again; do not ask for permission in text first.

    Args:
        kind: "excluded_employer" or "preference".
        value: The employer name (for "excluded_employer") or the
            preference text (for "preference").

    Related: FR-15 AC1, FR-10 AC6, D-6
    """

    if kind not in _VALID_KINDS:
        result = ToolResult(
            tool="remember",
            not_applicable_reason=f"Unknown kind {kind!r}; use excluded_employer or preference.",
        )
        return Command(update={"messages": [tool_message(result, runtime.tool_call_id)]})

    assert runtime.store is not None  # noqa: S101 - wired at create_agent(..., store=...) time
    user_id = runtime.state.get("user_id", "")
    runtime.store.put(
        ("memories", user_id),
        memory_key(kind, value),
        {"kind": kind, "value": value, "created_at": datetime.now(UTC).isoformat()},
    )

    result = ToolResult(tool="remember", result={"kind": kind, "value": value})
    return Command(update={"messages": [tool_message(result, runtime.tool_call_id)]})
