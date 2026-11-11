"""``search_jobs`` tool (FR-02).

The per-message call limit (FR-20 AC1) is enforced by
``middleware.limits.SearchCallLimitMiddleware`` before this tool ever runs,
not here - counting proposed calls from the message history instead of a
state counter sidesteps the parallel-call race a counter field would have
(two calls in one step would both read the same pre-increment count, D-19).

Related: FR-02 AC1-AC7, FR-03 AC2, FR-20 AC1, spec §6.1, §8, D-19
"""

from __future__ import annotations

from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from langgraph.types import Command

from job_hunt_agent.ba_client import BAClientError
from job_hunt_agent.context import AgentContext
from job_hunt_agent.models import ToolResult
from job_hunt_agent.state import JobHuntState
from job_hunt_agent.tools._common import ba_error_reason, tool_message


@tool
def search_jobs(
    keywords: str,
    location: str,
    radius_km: int = 25,
    published_within_days: int = 28,
    exclude_temp_agency: bool = True,
    page: int = 1,
    *,
    runtime: ToolRuntime[AgentContext, JobHuntState],
) -> Command:
    """Searches the BA job board for software-developer listings.

    Use plain keywords (e.g. "Python Entwickler") - do not use boolean
    operators like AND/OR/NOT or quoted phrases; they are removed before
    the search runs. At most 3 calls per message; after that, work with
    what you already have and say so.

    Args:
        keywords: Plain search keywords (German or English job titles/skills).
        location: City or region name.
        radius_km: Search radius in km (5-200; out-of-range values are
            clamped).
        published_within_days: Maximum listing age in days (1-100; clamped).
        exclude_temp_agency: Exclude temporary agency work
            (Arbeitnehmerüberlassung).
        page: 1-based page number for paging through more results.

    Related: FR-02 AC1-AC7, FR-03 AC2, FR-20 AC1
    """
    state = runtime.state

    try:
        summaries, total, notes = runtime.context.job_source.search(
            keywords=keywords,
            location=location,
            radius_km=radius_km,
            published_within_days=published_within_days,
            exclude_temp_agency=exclude_temp_agency,
            page=page,
        )
    except BAClientError as exc:
        result = ToolResult(tool="search_jobs", not_applicable_reason=ba_error_reason(exc))
        return Command(update={"messages": [tool_message(result, runtime.tool_call_id)]})

    seen_refs = set(state.get("seen_refs", []))
    summaries_cache = dict(state.get("summaries", {}))
    listings = []
    for summary in summaries:
        marked = summary.model_copy(update={"seen": summary.referenznummer in seen_refs})
        listings.append(marked)
        seen_refs.add(marked.referenznummer)
        summaries_cache[marked.referenznummer] = marked

    result = ToolResult(
        tool="search_jobs",
        result={"total": total, "listings": [s.model_dump(mode="json") for s in listings]},
        notes=notes,
    )
    return Command(
        update={
            "messages": [tool_message(result, runtime.tool_call_id)],
            "seen_refs": sorted(seen_refs),
            "summaries": summaries_cache,
        }
    )
