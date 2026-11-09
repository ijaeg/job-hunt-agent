"""Pydantic models for the structured formats of spec §6.

Every shape that crosses a tool boundary, is computed by the rubric, or is
persisted (tracker, memory, profile) is defined once here so that
``tools/``, ``ba_client.py``, ``rubric.py`` and ``storage.py`` share the same
contract instead of passing loose dicts around.

Related: FR-02, FR-04, FR-05, FR-06, FR-09, FR-14, FR-15, spec §6
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

SeniorityLevel = Literal["junior", "mid", "senior", "lead"]
SeniorityOrUnmentioned = Literal["junior", "mid", "senior", "lead", "not_mentioned"]
GermanLevel = Literal["none", "basic", "fluent", "native"]
GermanLevelOrUnmentioned = Literal["none", "basic", "fluent", "native", "not_mentioned"]
RemotePreference = Literal["onsite", "hybrid", "remote"]
FitCategory = Literal["strong", "partial", "poor", "excluded"]
TrackerStatus = Literal["saved", "applied", "rejected"]
MemoryKind = Literal["excluded_employer", "preference"]
RubricVerdict = Literal["met", "partly", "not_met", "unknown"]


class ToolResult(BaseModel):
    """Envelope every tool call returns, so the agent sees a uniform shape.

    ``result`` is ``None`` exactly when ``not_applicable_reason`` is set
    (spec §6.1); a tool never raises an exception into the agent loop.

    Related: spec §6.1, FR-21 AC3
    """

    tool: str
    result: dict[str, object] | None = None
    notes: list[str] = Field(default_factory=list)
    not_applicable_reason: str | None = None


class JobSummary(BaseModel):
    """One listing as returned by ``search_jobs`` (spec FR-02 AC2).

    Fields are the compact subset of the BA search response the model is
    allowed to see; the full API response is never passed through.

    Related: FR-02 AC2, FR-02 AC5, D-1
    """

    referenznummer: str
    title: str
    employer: str | None = None
    location: str | None = None
    distance_km: float | None = None
    published_date: date | None = None
    remote_type: str | None = None
    remote_percent: int | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    full_time: bool | None = None
    contract_duration: str | None = None
    external_url: bool = False
    seen: bool = False


class JobDetails(BaseModel):
    """One listing as returned by ``get_job_details`` (spec FR-04 AC2).

    ``description`` has already passed :func:`job_hunt_agent.pii.clean_ad_text`
    (FR-22 AC1) by the time it reaches this model; callers never see raw ad
    text. ``low_evidence`` is set by the caller for texts under 600
    characters (FR-04 AC5), not computed here.

    Related: FR-04 AC2, FR-04 AC5, FR-22 AC1, D-1, D-2
    """

    referenznummer: str
    title: str
    employer: str | None = None
    description: str
    is_temp_agency: bool | None = None
    is_private_recruiter: bool | None = None
    remote_type: str | None = None
    remote_percent: int | None = None
    contract_months: int | None = None
    full_time: bool | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    low_evidence: bool = False


class Requirement(BaseModel):
    """One skill requirement extracted from the free text (spec §6.2).

    ``evidence_de`` must be a verbatim substring of the cleaned ad text;
    callers (``assess_fit``) drop requirements whose evidence fails that
    check (FR-05 AC2) before constructing this model.

    Related: FR-05 AC2, spec §6.2
    """

    name: str
    required: bool
    evidence_de: str
    evidence_en: str


class JobRequirements(BaseModel):
    """Per-listing extraction output of the LLM (spec §6.2).

    Purely descriptive: nothing here is a fit decision. ``rubric.assess``
    turns this, the structured API fields and the profile into a
    :class:`FitAssessment` (FR-05 AC3 - the model never sets the category).

    Related: FR-05 AC1, FR-05 AC3, FR-05 AC4, spec §6.2
    """

    referenznummer: str
    skills: list[Requirement] = Field(default_factory=list)
    seniority: SeniorityOrUnmentioned
    seniority_evidence: str | None = None
    german_level: GermanLevelOrUnmentioned
    german_level_evidence: str | None = None
    english_required: bool | None = None
    summary_en: str


class MatchEvidence(BaseModel):
    """One matched or missing skill, with its bilingual evidence (spec §6.3).

    ``evidence_de``/``evidence_en`` are carried over verbatim from the
    :class:`Requirement` ``rubric.assess`` matched or failed to match against
    the profile; the UI shows both (FR-07 AC1), and a follow-up answer
    (FR-08 AC2) can cite them without a new tool call.

    Related: FR-05 AC4, FR-07 AC1, FR-08 AC2, spec §6.3, D-11
    """

    name: str
    evidence_de: str
    evidence_en: str


class FitAssessment(BaseModel):
    """Fit result computed by code from :class:`JobRequirements` (spec §6.3).

    ``category`` and ``exclusion_reasons`` are never set by the LLM
    (invariant 2, CLAUDE.md); they are the output of
    :func:`job_hunt_agent.rubric.assess` and
    :func:`job_hunt_agent.rubric.hard_exclusions`.

    Related: FR-05 AC3, FR-05 AC5, FR-06 AC4, spec §6.3, §7, D-11
    """

    referenznummer: str
    category: FitCategory
    exclusion_reasons: list[str] = Field(default_factory=list)
    matches: list[MatchEvidence] = Field(default_factory=list)
    gaps: list[MatchEvidence] = Field(default_factory=list)
    unknown: list[str] = Field(default_factory=list)
    low_evidence: bool = False
    rubric: dict[str, RubricVerdict] = Field(default_factory=dict)


class TrackerEntry(BaseModel):
    """One row of the ``tracker`` table (spec §6.4).

    Idempotent by ``(user_id, referenznummer)`` (FR-09 AC1); never holds ad
    text, only the fields needed to find the listing again.

    Related: FR-09 AC1, FR-09 AC2, spec §6.4
    """

    user_id: str
    referenznummer: str
    title: str
    employer: str | None = None
    url: str | None = None
    status: TrackerStatus
    follow_up_date: date | None = None
    note: str | None = None
    created_at: datetime
    updated_at: datetime


class Memory(BaseModel):
    """One item in the long-term memory store (spec §6.4).

    Related: FR-15 AC1, FR-15 AC4, spec §6.4
    """

    user_id: str
    kind: MemoryKind
    value: str
    created_at: datetime


class Profile(BaseModel):
    """User profile edited in the settings form (spec FR-14).

    Deliberately has **no** name, e-mail, phone or address field (FR-14
    AC3): the agent only ever needs skills, seniority, location, search
    radius, remote preference, the temporary-agency exclusion and language
    levels to run the rubric (§7) and the search tool (FR-02).

    Related: FR-14 AC1, FR-14 AC3, spec §3.1, §7
    """

    skills: list[str] = Field(default_factory=list)
    seniority: SeniorityLevel
    location: str
    radius_km: int = Field(ge=5, le=200)
    remote_preference: RemotePreference
    wants_full_time: bool = True
    wants_permanent: bool = True
    exclude_temp_agency: bool = True
    german_level: GermanLevel
    english_level: GermanLevel
