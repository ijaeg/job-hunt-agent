"""Tests for :mod:`job_hunt_agent.models`.

Related: FR-02, FR-04, FR-05, FR-06, FR-09, FR-14, FR-15, spec §6
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from job_hunt_agent.models import (
    FitAssessment,
    JobDetails,
    JobRequirements,
    JobSummary,
    Memory,
    Profile,
    Requirement,
    ToolResult,
    TrackerEntry,
)


def test_tool_result_defaults_to_empty_notes_and_no_reason() -> None:
    """A successful ``ToolResult`` carries a result and no exclusion reason."""
    result = ToolResult(tool="search_jobs", result={"total": 3})
    assert result.notes == []
    assert result.not_applicable_reason is None


def test_tool_result_not_applicable_reason_without_result() -> None:
    """A rejected tool call sets ``not_applicable_reason`` (spec §6.1)."""
    result = ToolResult(tool="search_jobs", not_applicable_reason="radius must be 5-200 km")
    assert result.result is None
    assert result.not_applicable_reason == "radius must be 5-200 km"


def test_job_summary_minimal_fields() -> None:
    """``JobSummary`` accepts only ``referenznummer`` and ``title`` as required."""
    summary = JobSummary(referenznummer="19522-0068291613-S", title="Python-Entwickler")
    assert summary.seen is False
    assert summary.external_url is False
    assert summary.distance_km is None


def test_job_summary_full_fields() -> None:
    """All FR-02 AC2 fields round-trip through the model."""
    summary = JobSummary(
        referenznummer="17338-c2de5ff0cd55000215-S",
        title="Python-Entwickler (w/m/d) - Hybrid",
        employer="Vertec AG",
        location="Hamburg",
        distance_km=2,
        published_date=date(2026, 11, 4),
        remote_type="ANGABE_IN_PROZENT",
        remote_percent=50,
        salary_min=60000,
        salary_max=80000,
        full_time=True,
        contract_duration="UNBEFRISTET",
        external_url=True,
        seen=True,
    )
    assert summary.employer == "Vertec AG"
    assert summary.seen is True


def test_job_details_requires_description() -> None:
    """``JobDetails`` requires the cleaned ad text; everything else is optional."""
    with pytest.raises(ValidationError):
        JobDetails(referenznummer="19522-0068291613-S", title="Python-Entwickler")  # type: ignore[call-arg]


def test_job_details_low_evidence_flag_is_set_by_the_caller() -> None:
    """``low_evidence`` is a plain field - not computed in the model (FR-04 AC5)."""
    details = JobDetails(
        referenznummer="19522-0068291613-S",
        title="Python-Entwickler",
        description="Kurzer Teaser-Text.",
        low_evidence=True,
    )
    assert details.low_evidence is True


def test_requirement_round_trips() -> None:
    """A ``Requirement`` carries both the German evidence and its translation."""
    req = Requirement(
        name="Python",
        required=True,
        evidence_de="mehrjährige Erfahrung mit Python",
        evidence_en="several years of experience with Python",
    )
    assert req.required is True


def test_job_requirements_allows_not_mentioned_enums() -> None:
    """Seniority and German level accept the ``not_mentioned`` sentinel (spec §6.2)."""
    reqs = JobRequirements(
        referenznummer="19522-0068291613-S",
        skills=[],
        seniority="not_mentioned",
        german_level="not_mentioned",
        english_required=None,
        summary_en="No details given.",
    )
    assert reqs.seniority == "not_mentioned"
    assert reqs.skills == []


def test_job_requirements_rejects_unknown_seniority() -> None:
    """An invalid seniority literal is rejected, not silently coerced."""
    with pytest.raises(ValidationError):
        JobRequirements(
            referenznummer="19522-0068291613-S",
            seniority="principal",  # type: ignore[arg-type]
            german_level="none",
            summary_en="x",
        )


def test_fit_assessment_category_is_a_closed_set() -> None:
    """``FitAssessment.category`` only accepts the four §6.3 categories."""
    with pytest.raises(ValidationError):
        FitAssessment(referenznummer="x", category="great")  # type: ignore[arg-type]


def test_fit_assessment_rubric_dict_defaults_to_empty() -> None:
    """A fresh ``FitAssessment`` has an empty rubric map, not ``None``."""
    assessment = FitAssessment(referenznummer="19522-0068291613-S", category="poor")
    assert assessment.rubric == {}
    assert assessment.exclusion_reasons == []


def test_tracker_entry_requires_timestamps() -> None:
    """A ``TrackerEntry`` needs both ``created_at`` and ``updated_at`` (spec §6.4)."""
    now = datetime(2026, 11, 6, 12, 0, 0)
    entry = TrackerEntry(
        user_id="alex",
        referenznummer="19522-0068291613-S",
        title="Python-Entwickler",
        status="saved",
        created_at=now,
        updated_at=now,
    )
    assert entry.status == "saved"
    assert entry.note is None


def test_memory_kind_is_restricted() -> None:
    """``Memory.kind`` only accepts the two spec §6.4 kinds."""
    with pytest.raises(ValidationError):
        Memory(
            user_id="alex",
            kind="note",  # type: ignore[arg-type]
            value="x",
            created_at=datetime(2026, 11, 6),
        )


def test_memory_excluded_employer() -> None:
    """A valid ``excluded_employer`` memory item round-trips."""
    memory = Memory(
        user_id="alex",
        kind="excluded_employer",
        value="Acme Staffing GmbH",
        created_at=datetime(2026, 11, 6),
    )
    assert memory.kind == "excluded_employer"


def test_profile_has_no_personal_identifier_fields() -> None:
    """FR-14 AC3: the profile model exposes no name, e-mail, phone or address field."""
    forbidden = {
        "name",
        "email",
        "phone",
        "address",
        "street",
        "postal_code",
        "first_name",
        "last_name",
    }
    assert forbidden.isdisjoint(Profile.model_fields.keys())


def test_profile_matches_persona_alex() -> None:
    """A profile shaped like the Alex persona (spec §3.1) validates."""
    profile = Profile(
        skills=["Python", "Java"],
        seniority="senior",
        location="Hamburg",
        radius_km=25,
        remote_preference="hybrid",
        exclude_temp_agency=True,
        german_level="basic",
        english_level="native",
    )
    assert profile.radius_km == 25
    assert profile.exclude_temp_agency is True


def test_profile_radius_out_of_range_is_rejected() -> None:
    """The radius bounds mirror FR-02's ``radius_km`` range (5-200 km)."""
    with pytest.raises(ValidationError):
        Profile(
            skills=[],
            seniority="mid",
            location="Hamburg",
            radius_km=1,
            remote_preference="onsite",
            german_level="none",
            english_level="native",
        )
