"""Call limits (spec §5.4 #3, FR-20): max model calls, max ``search_jobs`` calls.

The model-call limit uses the built-in ``ModelCallLimitMiddleware`` (spec
§5.4 explicitly allows "built-in or own"). The ``search_jobs`` limit is its
own middleware (``SearchCallLimitMiddleware``) rather than the built-in
``ToolCallLimitMiddleware`` (checked under D-19/WP-11): that middleware's
``run_limit`` is meant to reset "per invocation", but in this app one user
message can span several separate ``agent.invoke()`` calls whenever a
``save_to_tracker``/``remember`` approval interrupts the turn (FR-10), and
measuring against the real ``langchain`` 1.4.9 package showed
``run_tool_call_count`` does *not* reset across either of those boundaries
the way "per user message" (FR-20 AC1, FR-03 AC2) needs: it survives an
interrupt/resume pair (so a resumed turn correctly keeps its remaining
budget - that part is fine), but it also survives into the *next* user
message with no interrupt at all, which is wrong (a fresh message should
get a fresh budget of 3). ``thread_limit`` does not fit either (thread
lifetime, not per-message).

Related: FR-20 AC1, FR-03 AC2, spec §5.3, §5.4 #3, D-19
"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware, AgentState, ModelCallLimitMiddleware
from langchain_core.messages import AIMessage, HumanMessage

from job_hunt_agent import config
from job_hunt_agent.state import JobHuntState


def build_model_call_limit_middleware() -> ModelCallLimitMiddleware:
    """FR-20 AC1: ends the turn with a message instead of looping past the limit."""
    return ModelCallLimitMiddleware(
        run_limit=config.MAX_MODEL_CALLS_PER_MESSAGE, exit_behavior="end"
    )


def _search_calls_in_turn(messages: list[Any]) -> int:
    """Counts ``search_jobs`` tool calls proposed since the last ``HumanMessage``.

    Scans every ``AIMessage`` in that span, not just completed ones: each
    earlier step's ``AIMessage`` already had any excess ``search_jobs``
    calls stripped by this middleware when it ran for that step, so the
    history itself never holds more than the allowed count - a plain count
    is enough, no separate counter field is needed (and a counter field
    would itself race under parallel calls, D-19).
    """
    count = 0
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            break
        if isinstance(message, AIMessage):
            count += sum(1 for tc in message.tool_calls if tc["name"] == "search_jobs")
    return count


class SearchCallLimitMiddleware(AgentMiddleware):
    """Caps ``search_jobs`` calls per user message at ``MAX_SEARCH_CALLS_PER_MESSAGE``.

    Counts every proposed call since the last ``HumanMessage``, including
    several in the same step (parallel tool calls, D-19): if the newest
    ``AIMessage`` would push the total over the limit, the excess
    ``search_jobs`` tool calls are dropped from it (same technique as
    ``RejectionLockMiddleware`` - a new ``AIMessage`` with the same id and
    a shorter ``tool_calls`` list) before the tool node ever runs, with a
    short note instead. A new user message naturally resets the count to 0
    since the scan stops at the preceding ``HumanMessage``.

    Related: FR-20 AC1, FR-03 AC2, spec §5.3, D-19
    """

    state_schema = JobHuntState

    def after_model(self, state: AgentState[Any], runtime: Any) -> dict[str, Any] | None:
        messages: list[Any] = state["messages"]
        last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        if not last_ai or not last_ai.tool_calls:
            return None

        already = _search_calls_in_turn(messages[:-1])
        remaining = max(0, config.MAX_SEARCH_CALLS_PER_MESSAGE - already)

        kept, kept_search_calls, dropped = [], 0, 0
        for tc in last_ai.tool_calls:
            if tc["name"] != "search_jobs":
                kept.append(tc)
            elif kept_search_calls < remaining:
                kept.append(tc)
                kept_search_calls += 1
            else:
                dropped += 1

        if not dropped:
            return None

        note = (
            f"\n\n(Not calling search_jobs again this message: the limit of "
            f"{config.MAX_SEARCH_CALLS_PER_MESSAGE} calls per message is already reached. "
            "Work with the existing results and tell the user.)"
        )
        new_ai = AIMessage(
            content=str(last_ai.content or "") + note, tool_calls=kept, id=last_ai.id
        )
        return {"messages": [new_ai]}
