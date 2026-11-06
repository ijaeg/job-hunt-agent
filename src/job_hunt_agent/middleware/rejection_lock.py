"""Rejection lock (spec §5.4 #4, FR-10 AC3), proven in spike D-5 (``spikes/hitl_app.py``).

Must be listed **after** ``HumanInTheLoopMiddleware`` in ``middleware=[...]``:
`after_model` hooks run in *reverse* middleware-list order (the last-listed
middleware's `after_model` runs first, an undocumented behaviour found in
`langchain/agents/factory.py` during D-5), so listing this one last makes
its `after_model` strip a repeated rejected call *before* HITL's own
`after_model` would otherwise raise a second interrupt for it.

Related: FR-10 AC3, spec §5.3, §5.4 #4, D-5
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any, cast

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from job_hunt_agent.state import JobHuntState


def hash_call(name: str, args: dict[str, Any]) -> str:
    """Stable hash of a tool name and its arguments, for the rejection lock."""
    payload = json.dumps({"name": name, "args": args}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


class RejectionLockMiddleware(AgentMiddleware):
    """Drops a tool call identical to one already rejected in this thread.

    ``before_model`` scans the message history for HITL's reject
    ``ToolMessage``s (``status == "error"``, content starting with "User
    rejected the tool call for") and records a hash of the original call
    into ``rejected_actions``. ``after_model`` then strips any later
    proposal with a matching hash from the newest ``AIMessage.tool_calls``,
    replacing it with the same message (same id, so the state reducer
    updates it in place) carrying an explanatory note instead - the agent
    explains rather than re-asking (FR-10 AC3).

    Dropping the tool call entirely (not just answering it with a
    ``ToolMessage``) is required: HITL's ``after_model`` decides whether to
    interrupt purely from ``AIMessage.tool_calls``, with no check for an
    existing answer, so leaving the call in place - even if answered -
    would still trigger a second interrupt.

    Related: FR-10 AC3, spec §5.3, §5.4 #4, D-5
    """

    state_schema = JobHuntState

    def before_model(self, state: AgentState[Any], runtime: Any) -> dict[str, Any] | None:
        messages: Sequence[BaseMessage] = state["messages"]
        call_by_id: dict[str, tuple[str, dict[str, Any]]] = {}
        for msg in messages:
            if isinstance(msg, AIMessage):
                for tc in msg.tool_calls:
                    if tc["id"] is not None:
                        call_by_id[tc["id"]] = (tc["name"], tc["args"])

        rejected_actions = cast("list[str]", state.get("rejected_actions", []))
        rejected = set(rejected_actions)
        before = set(rejected)
        for msg in messages:
            if (
                isinstance(msg, ToolMessage)
                and msg.status == "error"
                and "User rejected the tool call for" in str(msg.content)
                and msg.tool_call_id is not None
            ):
                call = call_by_id.get(msg.tool_call_id)
                if call:
                    rejected.add(hash_call(*call))

        if rejected == before:
            return None
        return {"rejected_actions": sorted(rejected)}

    def after_model(self, state: AgentState[Any], runtime: Any) -> dict[str, Any] | None:
        messages: Sequence[BaseMessage] = state["messages"]
        last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        if not last_ai or not last_ai.tool_calls:
            return None

        rejected_actions = cast("list[str]", state.get("rejected_actions", []))
        rejected = set(rejected_actions)
        if not rejected:
            return None

        kept, dropped_names = [], []
        for tc in last_ai.tool_calls:
            if hash_call(tc["name"], tc["args"]) in rejected:
                dropped_names.append(tc["name"])
            else:
                kept.append(tc)

        if not dropped_names:
            return None

        note = (
            f"\n\n(Not repeating {', '.join(dropped_names)}: this exact action was "
            "already rejected in this conversation.)"
        )
        new_ai = AIMessage(
            content=str(last_ai.content or "") + note, tool_calls=kept, id=last_ai.id
        )
        return {"messages": [new_ai]}
