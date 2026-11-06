"""``save_to_tracker`` tool (FR-09). Approval is middleware, not this tool's job.

Related: FR-09 AC1-AC3, FR-10, spec §6.1, §8
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from langgraph.types import Command

from job_hunt_agent import storage
from job_hunt_agent.context import AgentContext
from job_hunt_agent.models import ToolResult, TrackerEntry
from job_hunt_agent.state import JobHuntState
from job_hunt_agent.tools._common import tool_message

_VALID_STATUSES = {"saved", "applied", "rejected"}


def validate_follow_up_date(value: str | None) -> tuple[date | None, str | None]:
    """Parses and validates ``follow_up_date`` (FR-09 AC2): today or later.

    Args:
        value: An ISO date string (``YYYY-MM-DD``), or ``None``.

    Returns:
        A tuple of the parsed date (or ``None``) and an error message (or
        ``None`` if valid).

    Related: FR-09 AC2
    """
    if value is None:
        return None, None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None, f"follow_up_date {value!r} is not a valid date (expected YYYY-MM-DD)."
    if parsed < datetime.now(UTC).date():
        return None, f"follow_up_date {value!r} must be today or later."
    return parsed, None


@tool
def save_to_tracker(
    referenznummer: str,
    status: str,
    follow_up_date: str | None = None,
    note: str | None = None,
    *,
    runtime: ToolRuntime[AgentContext, JobHuntState],
) -> Command:
    """Saves or updates a listing in the application tracker.

    This call is gated by approval outside the conversation - propose it
    directly when the user wants to save, apply to or reject a listing; do
    not ask for permission in text first.

    Args:
        referenznummer: The listing to save.
        status: One of "saved", "applied", "rejected".
        follow_up_date: Optional reminder date (``YYYY-MM-DD``), today or
            later.
        note: Optional free-text note.

    Related: FR-09 AC1-AC3, FR-10 AC6
    """

    if status not in _VALID_STATUSES:
        result = ToolResult(
            tool="save_to_tracker",
            not_applicable_reason=f"Unknown status {status!r}; use saved, applied or rejected.",
        )
        return Command(update={"messages": [tool_message(result, runtime.tool_call_id)]})

    parsed_date, error = validate_follow_up_date(follow_up_date)
    if error:
        result = ToolResult(tool="save_to_tracker", not_applicable_reason=error)
        return Command(update={"messages": [tool_message(result, runtime.tool_call_id)]})

    summary = runtime.state.get("summaries", {}).get(referenznummer)
    if summary is not None:
        title, employer = summary.title, summary.employer
    else:
        details = runtime.context.job_source.get_details(referenznummer)
        title, employer = details.title, details.employer

    now = datetime.now(UTC)
    entry = TrackerEntry(
        user_id=runtime.state.get("user_id", ""),
        referenznummer=referenznummer,
        title=title,
        employer=employer,
        # The public BA jobsuche web URL scheme is unverified (D-1 only
        # tested the JSON API); left unset rather than fabricated. FR-07's
        # "link to the listing" is a later, UI work package's concern.
        url=None,
        status=status,  # type: ignore[arg-type]
        follow_up_date=parsed_date,
        note=note,
        created_at=now,
        updated_at=now,
    )
    stored = storage.save_tracker_entry(runtime.context.conn, entry)

    result = ToolResult(tool="save_to_tracker", result=stored.model_dump(mode="json"))
    return Command(update={"messages": [tool_message(result, runtime.tool_call_id)]})
