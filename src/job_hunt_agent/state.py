"""Custom agent state (spec §5.3).

Every field here uses plain (overwrite) semantics, not a langgraph reducer:
whichever tool or middleware updates a field is responsible for reading the
current value from :class:`langchain.tools.ToolRuntime` or the hook's
``state`` argument first and writing back the already-merged result (e.g.
``search_jobs`` unions the new reference numbers into the existing
``seen_refs`` before returning its ``Command(update=...)``). This keeps the
merge logic in one visible place per field instead of split across a
custom `Annotated[...,  reducer]` and the caller.

Related: spec §5.3, FR-02 AC5, FR-05 AC5, FR-10 AC3, FR-20 AC1
"""

from __future__ import annotations

from typing import NotRequired

from langchain.agents.middleware import AgentState

from job_hunt_agent.models import FitAssessment, JobSummary


class JobHuntState(AgentState):
    """Adds the job-hunt-specific fields of spec §5.3 to the base agent state.

    Attributes:
        user_id: The selected user (no authentication, spec §2.2).
        seen_refs: Reference numbers already returned to the model in this
            thread (FR-02 AC5); a later ``search_jobs`` call marks these
            ``seen: true`` instead of re-introducing them as new.
        summaries: Search-time :class:`JobSummary` objects keyed by
            reference number, kept for every ref in ``seen_refs``. **Not in
            §5.3's field list** - added because ``distance_km`` only exists
            on ``JobSummary`` (never on ``JobDetails``), so without this,
            ``assess_fit`` would have no way to feed FR-06 AC2's distance
            check or the rubric's location/remote dimension; FR-06 AC3
            ("missing value never excludes") already makes this degrade
            gracefully if a referenznummer was never searched for
            in this thread (e.g. the model got it from elsewhere).
        shortlist: Reference numbers currently on the shortlist.
        assessments: Fit assessments keyed by reference number (FR-05 AC5),
            read by follow-up questions without a new tool call (FR-08 AC1).
        search_calls_this_turn: Count of ``search_jobs`` calls in the
            current user turn; reset to 0 when a new ``HumanMessage``
            starts a turn (FR-20 AC1, FR-03 AC2).
        rejected_actions: Hashes of ``(tool_name, args)`` for write actions
            already rejected in this thread (FR-10 AC3); recomputed in full
            from the message history on every model call, not accumulated.
    """

    user_id: NotRequired[str]
    seen_refs: NotRequired[list[str]]
    summaries: NotRequired[dict[str, JobSummary]]
    shortlist: NotRequired[list[str]]
    assessments: NotRequired[dict[str, FitAssessment]]
    search_calls_this_turn: NotRequired[int]
    rejected_actions: NotRequired[list[str]]
