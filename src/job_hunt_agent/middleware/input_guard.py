"""Input guard: length and known injection patterns, before any model call (FR-21 AC1).

Related: FR-21 AC1, FR-23, spec §5.4 #1
"""

from __future__ import annotations

import re
from typing import Any

from langchain.agents.middleware import AgentMiddleware, AgentState, hook_config
from langchain_core.messages import AIMessage, HumanMessage

from job_hunt_agent import config
from job_hunt_agent.state import JobHuntState

#: Known prompt-injection phrases (case-insensitive), checked on the raw
#: user message before it ever reaches the model. Deliberately narrow and
#: literal - this is a fast backstop, not a general jailbreak classifier;
#: FR-23's "ad texts are data" system-prompt instruction is the main
#: defence against injection arriving via a *listing*, not the user's own
#: message.
INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore (all |any )?(previous|prior|above) instructions",
        r"disregard (all |any )?(previous|prior|above) instructions",
        r"you are now",
        r"act as (if )?(you are )?(a |an )?(dan|jailbreak)",
        r"system prompt",
        r"reveal your (instructions|prompt)",
    )
)

LENGTH_REJECTION_MESSAGE = (
    f"Your message is too long (over {config.MAX_MESSAGE_LENGTH} characters). "
    "Please shorten it and try again."
)
INJECTION_REJECTION_MESSAGE = (
    "I can't follow instructions embedded in a message like that. "
    "Please rephrase your job search request."
)


def _violation_message(text: str) -> str | None:
    if len(text) > config.MAX_MESSAGE_LENGTH:
        return LENGTH_REJECTION_MESSAGE
    if any(pattern.search(text) for pattern in INJECTION_PATTERNS):
        return INJECTION_REJECTION_MESSAGE
    return None


class InputGuardMiddleware(AgentMiddleware):
    """Rejects an over-long or known-injection user message before any model call.

    Only checks the *newest* ``HumanMessage`` (i.e. the one that starts this
    turn) - ``before_model`` also runs again for every later step of the
    same turn's tool-calling loop, where the last message is a
    ``ToolMessage``, not the user's input, and should not be re-checked.

    Related: FR-21 AC1
    """

    state_schema = JobHuntState

    @hook_config(can_jump_to=["end"])
    def before_model(self, state: AgentState[Any], runtime: Any) -> dict[str, Any] | None:
        messages = state["messages"]
        if not messages or not isinstance(messages[-1], HumanMessage):
            return None

        violation = _violation_message(str(messages[-1].content))
        if violation is None:
            return None
        return {"jump_to": "end", "messages": [AIMessage(content=violation)]}
