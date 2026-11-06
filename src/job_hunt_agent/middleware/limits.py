"""Call limits (spec §5.4 #3, FR-20): max model calls, max ``search_jobs`` calls.

The model-call limit uses the built-in ``ModelCallLimitMiddleware`` (spec
§5.4 explicitly allows "built-in or own"). The ``search_jobs`` limit is
enforced in the tool itself (``tools/search.py``, reading/writing
``JobHuntState.search_calls_this_turn``) because that field is named in
spec §5.3 and the built-in ``ToolCallLimitMiddleware`` would track its own,
differently-named counter instead; this module only resets that counter to
0 at the start of each new user turn, which the tool cannot detect on its
own (it only sees its own calls, not when a fresh ``HumanMessage` arrives).

Related: FR-20 AC1, FR-03 AC2, spec §5.3, §5.4 #3
"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware, AgentState, ModelCallLimitMiddleware
from langchain_core.messages import HumanMessage

from job_hunt_agent import config
from job_hunt_agent.state import JobHuntState


def build_model_call_limit_middleware() -> ModelCallLimitMiddleware:
    """FR-20 AC1: ends the turn with a message instead of looping past the limit."""
    return ModelCallLimitMiddleware(
        run_limit=config.MAX_MODEL_CALLS_PER_MESSAGE, exit_behavior="end"
    )


class ResetSearchCallCounterMiddleware(AgentMiddleware):
    """Resets ``search_calls_this_turn`` to 0 when a new user turn starts.

    Related: FR-20 AC1, FR-03 AC2, spec §5.3
    """

    state_schema = JobHuntState

    def before_model(self, state: AgentState[Any], runtime: Any) -> dict[str, Any] | None:
        messages = state["messages"]
        if (
            messages
            and isinstance(messages[-1], HumanMessage)
            and state.get("search_calls_this_turn", 0) != 0
        ):
            return {"search_calls_this_turn": 0}
        return None
