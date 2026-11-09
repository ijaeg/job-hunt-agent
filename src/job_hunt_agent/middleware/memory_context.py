"""Loads the user's stored memories into the agent's context at thread start (FR-15 AC2).

A sibling of ``middleware/profile_context.py`` rather than a change to it:
the profile comes from ``AgentContext.profile``, already in hand at
``create_agent`` build time, while memories live in the long-term store
(``runtime.store``, D-6) and are read at call time, keyed by
``state["user_id"]`` - a different data source with a different "is there
anything to show" case (no memories yet is the common case for a new
user, unlike the profile, which always exists once seeded). Two small
middlewares, one per source, keep the "inject once, nothing if empty"
test for this one isolated from the profile's own tests.

Related: FR-15 AC2, FR-15 AC4, D-6
"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage

from job_hunt_agent import storage
from job_hunt_agent.state import JobHuntState

_KIND_LABELS: dict[str, str] = {
    "excluded_employer": "Excluded employer",
    "preference": "Preference",
}


def memory_context_message(memories: list[dict[str, Any]]) -> HumanMessage:
    """Builds the one-off context message listing the user's stored memories.

    Args:
        memories: Items as stored by ``tools.memory.remember`` - each a
            dict with ``kind`` and ``value``.

    Related: FR-15 AC2
    """
    lines = [
        f"- {_KIND_LABELS.get(item.get('kind', ''), item.get('kind', ''))}: {item.get('value')}"
        for item in memories
    ]
    text = (
        "[Context, not a message from the user - memories the user already told you "
        "about in an earlier thread (stored via remember, after approval). They apply "
        "automatically: excluded employers are already filtered out of the fit "
        "assessment by code, so you do not need to ask about any of this again - just "
        "mention it if it is relevant.]\n" + "\n".join(lines)
    )
    return HumanMessage(content=text, name="memory_context")


class LoadMemoryContextMiddleware(AgentMiddleware):
    """Injects :func:`memory_context_message` once, on a thread's first model call.

    Detected by the absence of any ``AIMessage`` yet in ``state["messages"]``
    - the model has not replied in this thread yet - rather than
    ``LoadProfileContextMiddleware``'s ``len(messages) == 1``: this
    middleware is listed *after* that one in ``agent.py``, so by the time
    its own ``before_model`` runs on the thread's first model call, the
    profile context message has already been prepended and the length
    check would be off by one. Unlike the profile (always present once
    seeded), no stored memories at all means no message: there is nothing
    to label as context, and an empty list would only read as noise.

    Related: FR-15 AC2
    """

    state_schema = JobHuntState

    def before_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        messages = state["messages"]
        if any(isinstance(m, AIMessage) for m in messages):
            return None
        if runtime.store is None:
            return None
        user_id = state.get("user_id", "")
        memories = storage.search_memories(runtime.store, user_id)
        if not memories:
            return None
        memories.sort(key=lambda m: m.get("created_at", ""), reverse=True)
        return {"messages": [memory_context_message(memories)]}
