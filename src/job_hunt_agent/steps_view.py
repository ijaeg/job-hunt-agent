"""Pure view helpers for the agent steps panel (FR-17). No Streamlit import here.

Like ``ui_view.py``, this module has no LLM or network calls (CLAUDE.md
"Architecture and dependency direction") - ``app.py`` reads the thread's
``messages`` from the checkpointer and calls these functions; it only
renders the result.

Related: FR-17 AC1, NFR-04, D-19
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

#: HumanMessages injected by middleware as context (middleware/profile_context.py,
#: middleware/memory_context.py) - never something the user actually said, so
#: never a turn boundary and never a chat bubble.
_CONTEXT_MESSAGE_NAMES = {"profile_context", "memory_context"}

#: Per-tool short-result text for a successful call (decided in WP-12): built
#: from the ``result`` dict inside its ``ToolResult`` envelope, never from ad
#: text - none of these templates touch a free-text ad field.
_SUCCESS_TEMPLATES: dict[str, object] = {
    "search_jobs": lambda r: f"{r.get('total', 0)} results, {len(r.get('listings', []))} returned",
    "get_job_details": lambda r: "details loaded",
    "assess_fit": lambda r: f"{len(r.get('assessed', []))} listings assessed",
    "save_to_tracker": lambda r: str(r.get("status", "saved")),
    "remember": lambda r: "saved",
    "list_tracker": lambda r: f"{len(r.get('entries', []))} entries",
}

#: Longest a compact argument summary or a fallback ToolMessage text is shown as.
_MAX_TEXT_LEN = 100


def is_user_turn_message(message: BaseMessage) -> bool:
    """True for a ``HumanMessage`` the user actually sent, not an injected context one.

    Related: FR-17 AC1
    """
    return (
        isinstance(message, HumanMessage)
        and bool(message.content)
        and message.name not in _CONTEXT_MESSAGE_NAMES
    )


def split_into_turns(messages: list[BaseMessage]) -> list[list[BaseMessage]]:
    """Groups a thread's full message history into one list per user turn.

    Every message up to (but not including) the next real user message
    belongs to the turn that starts at the previous one. Anything before
    the first real user message (e.g. a context message that happens to
    come first) is dropped - there is no answer to attach it to.

    Related: FR-17 AC1
    """
    turns: list[list[BaseMessage]] = []
    for message in messages:
        if is_user_turn_message(message):
            turns.append([message])
        elif turns:
            turns[-1].append(message)
    return turns


@dataclass
class StepRow:
    """One row of the "Agent steps" expander (FR-17 AC1).

    ``duration_seconds`` is ``None`` for a turn not just run in this
    session (``app.py``'s stream loop is the only source of durations);
    the caller renders that as "-" rather than a number.
    """

    tool: str
    args_text: str
    short_result: str | None
    duration_seconds: float | None
    parallel: bool


def _truncate(text: str, max_len: int = _MAX_TEXT_LEN) -> str:
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def compact_args(args: dict[str, object]) -> str:
    """One-line, length-capped rendering of a tool call's arguments."""
    return _truncate(json.dumps(args, default=str, separators=(", ", ": "), ensure_ascii=False))


def short_result_for_message(message: ToolMessage) -> str:
    """The short, never-ad-text result for one tool call (decided in WP-12).

    A ``not_applicable_reason`` (any tool) is shown verbatim; otherwise a
    per-tool template built from the ``result`` dict. HITL's own rejection
    ``ToolMessage`` (plain text, not the ``ToolResult`` JSON envelope,
    spec §6.1) is recognised separately. Any other plain-text content
    (e.g. a disabled tool's "not a valid tool" message from LangGraph's
    ``ToolNode``) is shown truncated, as a last resort.

    Related: FR-17 AC1
    """
    content = str(message.content)
    try:
        payload = json.loads(content)
    except (TypeError, ValueError):
        if "User rejected the tool call" in content:
            return "rejected"
        return _truncate(content)
    if not isinstance(payload, dict):
        return _truncate(content)

    reason = payload.get("not_applicable_reason")
    if reason:
        return str(reason)

    result = payload.get("result")
    if result is None:
        return "done"
    template = _SUCCESS_TEMPLATES.get(message.name or "")
    if template is None:
        return "done"
    return template(result)  # type: ignore[operator]


def build_turn_steps(
    turn_messages: list[BaseMessage], durations: dict[str, float] | None = None
) -> list[StepRow]:
    """Builds one :class:`StepRow` per tool call proposed in one user turn, in order.

    Parallel calls (several ``tool_calls`` on one ``AIMessage``, D-19) each
    get their own row, flagged ``parallel=True``. A tool call with no
    matching ``ToolMessage`` yet (e.g. a pending approval) gets
    ``short_result=None``.

    Args:
        turn_messages: One turn's slice of the thread's messages, as
            produced by :func:`split_into_turns` (or any list containing
            the turn's ``AIMessage``/``ToolMessage`` instances).
        durations: Wall-clock seconds per tool-call id, for turns just run
            in this session; ``None`` (the default) or a missing id both
            mean "unknown", not "zero".

    Related: FR-17 AC1, D-19
    """
    durations = durations or {}
    tool_messages_by_id: dict[str | None, ToolMessage] = {
        message.tool_call_id: message
        for message in turn_messages
        if isinstance(message, ToolMessage)
    }

    rows: list[StepRow] = []
    for message in turn_messages:
        if not isinstance(message, AIMessage) or not message.tool_calls:
            continue
        parallel = len(message.tool_calls) > 1
        for call in message.tool_calls:
            call_id = call.get("id")
            tool_message = tool_messages_by_id.get(call_id)
            short_result = (
                short_result_for_message(tool_message) if tool_message is not None else None
            )
            rows.append(
                StepRow(
                    tool=call["name"],
                    args_text=compact_args(call["args"]),
                    short_result=short_result,
                    duration_seconds=durations.get(call_id) if call_id else None,
                    parallel=parallel,
                )
            )
    return rows
