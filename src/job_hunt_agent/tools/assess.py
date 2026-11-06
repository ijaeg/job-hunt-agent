"""``assess_fit`` tool (FR-05): extraction call + code-only rubric.

Related: FR-05 AC1-AC6, FR-06, FR-15 AC4, spec §6.1, §7, D-4
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any

from langchain.tools import ToolRuntime
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langgraph.types import Command

from job_hunt_agent import config
from job_hunt_agent.ba_client import BAClientError
from job_hunt_agent.context import AgentContext
from job_hunt_agent.models import JobDetails, JobRequirements, JobSummary, ToolResult
from job_hunt_agent.rubric import assess as rubric_assess
from job_hunt_agent.state import JobHuntState
from job_hunt_agent.tools._common import ba_error_reason, tool_message

if TYPE_CHECKING:
    from job_hunt_agent.models import FitAssessment

_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "extract_requirements.md"


def load_extraction_prompt_template() -> str:
    """Reads the extraction prompt template (based on the D-4 spike prompt).

    Related: D-4, FR-05 AC1, FR-23 AC1
    """
    return _PROMPT_PATH.read_text(encoding="utf-8")


def drop_non_verbatim_evidence(
    requirements: JobRequirements, ad_text: str
) -> tuple[JobRequirements, int]:
    """Drops any skill whose ``evidence_de`` is not a verbatim substring of the ad text.

    Args:
        requirements: Raw extraction output.
        ad_text: The cleaned ad text the extraction ran against.

    Returns:
        A tuple of the filtered :class:`JobRequirements` and the number of
        skills dropped (``dropped_evidence``, FR-05 AC2).

    Related: FR-05 AC2
    """
    kept = [r for r in requirements.skills if r.evidence_de in ad_text]
    dropped = len(requirements.skills) - len(kept)
    if dropped:
        requirements = requirements.model_copy(update={"skills": kept})
    return requirements, dropped


def _excluded_employers(runtime: ToolRuntime[AgentContext, JobHuntState]) -> list[str]:
    """Employer names from long-term memory (FR-15 AC4)."""
    if runtime.store is None:
        return []
    user_id = runtime.state.get("user_id", "")
    items = runtime.store.search(("memories", user_id))
    return [
        item.value["value"]
        for item in items
        if isinstance(item.value, dict) and item.value.get("kind") == "excluded_employer"
    ]


def _fallback_summary(referenznummer: str, details: JobDetails) -> JobSummary:
    """A minimal ``JobSummary`` when no prior ``search_jobs`` call cached one.

    ``distance_km`` stays unknown here; the rubric treats that as "never
    excludes" (FR-06 AC3), not as a failure.
    """
    return JobSummary(
        referenznummer=referenznummer,
        title=details.title,
        employer=details.employer,
        full_time=details.full_time,
        remote_type=details.remote_type,
        remote_percent=details.remote_percent,
        salary_min=details.salary_min,
        salary_max=details.salary_max,
    )


def _extract_one(
    model: Any, template: str, referenznummer: str, ad_text: str
) -> tuple[JobRequirements, int] | None:
    prompt = template.format(referenznummer=referenznummer, ad_text=ad_text)
    structured_model = model.with_structured_output(JobRequirements)
    raw: JobRequirements = structured_model.invoke([HumanMessage(prompt)])
    return drop_non_verbatim_evidence(raw, ad_text)


@tool
def assess_fit(
    referenznummern: list[str],
    runtime: ToolRuntime[AgentContext, JobHuntState],
) -> Command:
    """Assesses the fit of up to 8 listings against the user's profile.

    One structured-extraction call per listing (run in parallel) reads
    skills, seniority and language level from the ad text; the fit
    category is then computed by code from that extraction, the profile
    and the listing's structured fields - never by the model. Call
    get_job_details for each listing first.

    Args:
        referenznummern: Up to 8 reference numbers to assess.

    Related: FR-05 AC1-AC6, FR-06, spec §7
    """

    if len(referenznummern) > config.MAX_LISTINGS_PER_ASSESS_FIT_CALL:
        result = ToolResult(
            tool="assess_fit",
            not_applicable_reason=(
                f"Assess at most {config.MAX_LISTINGS_PER_ASSESS_FIT_CALL} listings at once."
            ),
        )
        return Command(update={"messages": [tool_message(result, runtime.tool_call_id)]})

    notes: list[str] = []
    details_by_ref: dict[str, JobDetails] = {}
    for ref in referenznummern:
        try:
            details_by_ref[ref] = runtime.context.job_source.get_details(ref)
        except BAClientError as exc:
            notes.append(f"{ref}: {ba_error_reason(exc)}")

    template = load_extraction_prompt_template()
    model = runtime.context.extraction_model
    total_dropped_evidence = 0
    extracted: dict[str, JobRequirements] = {}

    def run_extraction(ref: str) -> tuple[str, JobRequirements | None, int]:
        try:
            outcome = _extract_one(model, template, ref, details_by_ref[ref].description)
        except Exception:  # noqa: BLE001 - any failure is reported, never raised
            return ref, None, 0
        if outcome is None:
            return ref, None, 0
        requirements, dropped = outcome
        return ref, requirements, dropped

    refs_with_details = list(details_by_ref)
    extraction_started = time.perf_counter()
    if refs_with_details:
        with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_EXTRACTIONS) as pool:
            for ref, requirements, dropped in pool.map(run_extraction, refs_with_details):
                total_dropped_evidence += dropped
                if requirements is None:
                    notes.append(f"{ref}: could not be assessed (extraction failed)")
                    continue
                extracted[ref] = requirements

    extraction_elapsed = time.perf_counter() - extraction_started
    if refs_with_details:
        notes.append(
            f"assess_fit extraction: {extraction_elapsed:.1f}s for {len(refs_with_details)} "
            "listing(s) (spec §9 NFR-03/R-4 latency tracking)"
        )

    profile = runtime.context.profile
    excluded_employers = _excluded_employers(runtime)
    summaries_cache = runtime.state.get("summaries", {})

    assessments: dict[str, FitAssessment] = dict(runtime.state.get("assessments", {}))
    shortlist = list(runtime.state.get("shortlist", []))
    for ref, requirements in extracted.items():
        details = details_by_ref[ref]
        summary = summaries_cache.get(ref) or _fallback_summary(ref, details)
        assessment = rubric_assess(summary, details, requirements, profile, excluded_employers)
        assessments[ref] = assessment
        if ref not in shortlist:
            shortlist.append(ref)

    result = ToolResult(
        tool="assess_fit",
        result={
            "assessed": [assessments[ref].model_dump(mode="json") for ref in extracted],
            "dropped_evidence": total_dropped_evidence,
        },
        notes=notes,
    )
    return Command(
        update={
            "messages": [tool_message(result, runtime.tool_call_id)],
            "assessments": assessments,
            "shortlist": shortlist,
        }
    )
