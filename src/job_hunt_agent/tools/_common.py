"""Shared helpers for the tool modules: the §6.1 ``ToolResult`` <-> ``ToolMessage`` bridge.

Related: spec §6.1, §8
"""

from __future__ import annotations

from langchain_core.messages import ToolMessage

from job_hunt_agent.ba_client import BAForbiddenError, BAMalformedResponseError, BAUnavailableError
from job_hunt_agent.models import ToolResult


def tool_message(result: ToolResult, tool_call_id: str | None) -> ToolMessage:
    """Wraps a :class:`ToolResult` as the ``ToolMessage`` the model sees.

    Related: spec §6.1
    """
    return ToolMessage(
        content=result.model_dump_json(), tool_call_id=tool_call_id, name=result.tool
    )


def ba_error_reason(exc: Exception) -> str:
    """Maps a :mod:`job_hunt_agent.ba_client` exception to the spec §8 user-facing text.

    Every case ends up as a tool's ``not_applicable_reason`` - never an
    uncaught exception reaching the UI (CLAUDE.md invariant 7, FR-21 AC3).

    Related: spec §8
    """
    if isinstance(exc, BAForbiddenError):
        return "The job board rejected the request - try demo mode instead."
    if isinstance(exc, BAUnavailableError):
        return "The job board is not responding - try again or switch to demo mode."
    if isinstance(exc, BAMalformedResponseError):
        return "The job board returned an unexpected response."
    return f"Unexpected error: {type(exc).__name__}."
