"""Shared scripted turn/resume runner (WP-10's run_safety_tests.py, WP-15a's
eval/run_trajectory_eval.py both drive the agent through a list of scripted
user/resume turns on a fresh thread; extracted here so both call the exact
same loop instead of maintaining two copies - CLAUDE.md: reuse where clean).

Turn dict shape: ``{"user": "<message>"}`` for a ``HumanMessage`` turn, or
``{"resume": "approve"|"reject"|...}`` for a resume turn - skipped (no
``agent.invoke`` call at all) if no interrupt is actually pending, since the
model is free not to propose a write action in the first place.

Related: spec §9.2, §9.4, FR-10, D-5, WP-10, WP-15a
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.types import Command


def run_one_turn(
    agent: Any,
    cfg: dict[str, Any],
    ctx: Any,
    user_id: str,
    turn: dict[str, str],
    messages_before: int,
) -> tuple[list[Any], dict[str, Any] | None]:
    """Runs one scripted turn.

    Args:
        agent: Compiled agent (``build_agent``).
        cfg: ``{"configurable": {"thread_id": ...}}``.
        ctx: ``AgentContext`` for this run.
        user_id: Synthetic per-run user id.
        turn: ``{"user": ...}`` or ``{"resume": "approve"|"reject"}``.
        messages_before: Message count going in, so the caller can slice out
            only the messages this turn added.

    Returns:
        A tuple of the new messages this turn added (empty if skipped) and
        the full ``agent.invoke`` result dict, or ``None`` if a resume turn
        was skipped because no interrupt was pending.
    """
    if "resume" in turn:
        if not agent.get_state(cfg).interrupts:
            return [], None
        payload: Any = Command(resume={"decisions": [{"type": turn["resume"]}]})
    else:
        payload = {"messages": [HumanMessage(turn["user"])], "user_id": user_id}
    result = agent.invoke(payload, config=cfg, context=ctx)
    return result["messages"][messages_before:], result


def run_turns(
    agent: Any, ctx: Any, user_id: str, thread_id: str, turns: list[dict[str, str]]
) -> tuple[list[Any], Any]:
    """Runs a full scripted sequence of turns on one fresh thread.

    Args:
        agent: Compiled agent (``build_agent``).
        ctx: ``AgentContext`` for this run.
        user_id: Synthetic per-run user id.
        thread_id: Fresh thread id for this run.
        turns: Scripted turns, see :func:`run_one_turn`.

    Returns:
        A tuple of the final cumulative message list and the resulting
        ``agent.get_state(cfg)`` (for reading pending interrupts).

    Related: FR-10, D-5, WP-10
    """
    cfg = {"configurable": {"thread_id": thread_id}}
    messages: list[Any] = []
    for turn in turns:
        new_messages, result = run_one_turn(agent, cfg, ctx, user_id, turn, len(messages))
        del new_messages  # unused here; run_trajectory_eval.py wants it, this caller doesn't
        if result is None:
            continue
        messages = result["messages"]
    return messages, agent.get_state(cfg)
