"""Fit rubric and hard exclusions (spec §7, FR-06).

Pure functions, no LLM or network calls (CLAUDE.md "Architecture"). The
language model only extracts :class:`JobRequirements` from the free text;
every exclusion, verdict, weight and category here is code, never
overridden by the model (invariant 2, CLAUDE.md).

Weights and thresholds are **start values** confirmed/adjusted in
``docs/decisions/D-9-rubric-start-values.md`` - change them there, not by
editing this module ad hoc, so the decision record stays the source of
truth for *why* a number is what it is.

Related: FR-06 AC1-AC4, spec §7, D-9
"""

from __future__ import annotations

from job_hunt_agent.models import (
    FitAssessment,
    FitCategory,
    GermanLevel,
    GermanLevelOrUnmentioned,
    JobDetails,
    JobRequirements,
    JobSummary,
    Profile,
    RubricVerdict,
    SeniorityLevel,
    SeniorityOrUnmentioned,
)

# ---------------------------------------------------------------------------
# Start values (spec §7) - see docs/decisions/D-9-rubric-start-values.md
# ---------------------------------------------------------------------------

#: Dimension weights (spec §7 table). Keys match ``FitAssessment.rubric``.
DIMENSION_WEIGHTS: dict[str, int] = {
    "skills": 2,
    "location_remote": 1,
    "seniority": 1,
    "language": 1,
    "employment_type": 1,
}

#: Points per verdict; "unknown" is excluded from both sides of the share
#: computation, not scored as 0 (spec §7 "Scoring").
VERDICT_POINTS: dict[RubricVerdict, int] = {"met": 2, "partly": 1, "not_met": 0}

#: Overall category thresholds, as a share of reached points (spec §7).
STRONG_THRESHOLD = 0.75
PARTIAL_THRESHOLD = 0.45

#: Skills-dimension thresholds: share of required skills found in the
#: profile (spec §7 "Skills" row).
SKILLS_STRONG_THRESHOLD = 0.70
SKILLS_PARTIAL_THRESHOLD = 0.40

#: More than this many "unknown" dimensions caps the category at "partial"
#: and sets ``low_evidence`` (spec §7, last sentence).
MAX_UNKNOWN_DIMENSIONS_BEFORE_CAP = 2

SENIORITY_ORDER: list[SeniorityLevel] = ["junior", "mid", "senior", "lead"]
GERMAN_LEVEL_ORDER: list[GermanLevel] = ["none", "basic", "fluent", "native"]

#: A listing is treated as fully remote - the FR-06 AC2 "no full remote
#: work" escape clause - at this ``remote_percent`` or above.
FULL_REMOTE_PERCENT_THRESHOLD = 100


def _normalize(text: str) -> str:
    return text.strip().lower()


def skill_matches_profile(requirement_name: str, profile_skills: list[str]) -> bool:
    """Whether an extracted skill counts as present in the profile.

    **Start value, open in D-9.** LLM-extracted skill names are often
    verbose compound phrases (e.g. "Programmiersprachen: Java, Python, C#"),
    not the short tokens a profile uses ("Python"). An *exact* name match
    would almost never fire on real extractions (confirmed on the 5 D-4
    listings, see D-9); this implementation instead matches if a profile
    skill token appears as a case-insensitive substring of the requirement
    name, or vice versa for a short requirement name. D-9 shows where this
    differs from exact matching and from a small synonym list.

    Related: FR-05 AC1, spec §7 "Skills", D-9
    """
    req = _normalize(requirement_name)
    return any(_normalize(skill) in req or req in _normalize(skill) for skill in profile_skills)


def hard_exclusions(
    details: JobDetails,
    profile: Profile,
    excluded_employers: list[str],
    distance_km: float | None = None,
) -> list[str]:
    """Hard exclusions, computed by code (FR-06 AC1-AC4).

    ``distance_km`` is not part of :class:`JobDetails` (it is only on the
    search-time :class:`JobSummary`), so it is accepted as its own
    parameter - the full listing-plus-summary shape ``assess`` works with,
    narrowed to what this one check needs.

    A missing structured value (``details.is_temp_agency is None``, or
    ``distance_km is None``) never excludes on its own (FR-06 AC3); it is
    simply not evaluated for that rule.

    Args:
        details: The listing's cleaned details.
        profile: The user's profile.
        excluded_employers: Employer names from the user's long-term
            memory (FR-15 AC4), matched case-insensitively.
        distance_km: Distance from the search location, if known.

    Returns:
        Exclusion reasons, in English, empty if none apply. Kept separate
        from the fit category by the caller (FR-06 AC4).

    Related: FR-06 AC1, FR-06 AC2, FR-06 AC3, FR-06 AC4, FR-15 AC4
    """
    reasons: list[str] = []

    if profile.exclude_temp_agency and details.is_temp_agency is True:
        reasons.append("temporary agency work (Arbeitnehmerüberlassung)")

    full_remote = (
        details.remote_percent is not None
        and details.remote_percent >= FULL_REMOTE_PERCENT_THRESHOLD
    )
    if distance_km is not None and distance_km > profile.radius_km and not full_remote:
        reasons.append(
            f"distance {distance_km:g} km exceeds the profile's radius of "
            f"{profile.radius_km} km, and the listing is not fully remote"
        )

    if details.employer:
        employer_norm = _normalize(details.employer)
        if any(employer_norm == _normalize(excluded) for excluded in excluded_employers):
            reasons.append(f"excluded by you: {details.employer}")

    return reasons


def _skills_verdict(requirements: JobRequirements, profile: Profile) -> RubricVerdict:
    """Share of the ad's extracted skills found in the profile.

    **D-9 (2026-11-06):** counts every extracted skill, not only ones the
    model flagged ``required: true``. The literal spec §7 reading ("no
    required skills extracted" -> unknown) made this dimension - the
    heaviest-weighted one - drop out as unknown on 4 of 5 real D-4 listings,
    because gpt-5-mini rarely sets that flag; D-9 confirmed scoring all
    extracted skills instead, since the ad still states skills either way.

    Related: FR-05 AC1, spec §7 "Skills", D-9
    """
    skills = requirements.skills
    if not skills:
        return "unknown"
    matched = sum(1 for r in skills if skill_matches_profile(r.name, profile.skills))
    share = matched / len(skills)
    if share >= SKILLS_STRONG_THRESHOLD:
        return "met"
    if share >= SKILLS_PARTIAL_THRESHOLD:
        return "partly"
    return "not_met"


def _location_remote_verdict(
    summary: JobSummary, details: JobDetails, profile: Profile
) -> RubricVerdict:
    remote_percent = (
        details.remote_percent if details.remote_percent is not None else (summary.remote_percent)
    )
    remote_type = details.remote_type if details.remote_type is not None else summary.remote_type
    full_remote = remote_percent is not None and remote_percent >= FULL_REMOTE_PERCENT_THRESHOLD

    distance = summary.distance_km
    within_radius = distance is None or distance <= profile.radius_km

    remote_stated = remote_percent is not None or remote_type is not None
    if profile.remote_preference == "onsite":
        remote_satisfied = True
    elif profile.remote_preference == "hybrid":
        remote_satisfied = full_remote or (remote_percent is not None and remote_percent > 0)
    else:  # "remote"
        remote_satisfied = full_remote

    if full_remote:
        return "met"
    if within_radius and remote_satisfied:
        return "met"
    if within_radius and not remote_stated:
        return "partly"
    if not within_radius:
        return "not_met"
    return "not_met"


def _seniority_verdict(requirements: JobRequirements, profile: Profile) -> RubricVerdict:
    ad_level: SeniorityOrUnmentioned = requirements.seniority
    if ad_level == "not_mentioned":
        return "unknown"
    distance = abs(SENIORITY_ORDER.index(ad_level) - SENIORITY_ORDER.index(profile.seniority))
    if distance == 0:
        return "met"
    if distance == 1:
        return "partly"
    return "not_met"


def _language_verdict(requirements: JobRequirements, profile: Profile) -> RubricVerdict:
    ad_level: GermanLevelOrUnmentioned = requirements.german_level
    if ad_level == "not_mentioned":
        return "unknown"
    distance = GERMAN_LEVEL_ORDER.index(ad_level) - GERMAN_LEVEL_ORDER.index(profile.german_level)
    if distance <= 0:
        return "met"
    if distance == 1:
        return "partly"
    return "not_met"


def _employment_type_verdict(details: JobDetails, profile: Profile) -> RubricVerdict:
    if details.full_time is None and details.contract_months is None:
        return "unknown"
    full_time_ok = details.full_time is None or details.full_time == profile.wants_full_time
    is_permanent = details.contract_months is None
    permanent_ok = is_permanent == profile.wants_permanent
    return "met" if full_time_ok and permanent_ok else "not_met"


def assess(
    summary: JobSummary,
    details: JobDetails,
    requirements: JobRequirements,
    profile: Profile,
    excluded_employers: list[str] | None = None,
) -> FitAssessment:
    """Computes the fit category from the rubric (spec §7), never from the model.

    Args:
        summary: The listing's search-time fields (distance, remote share).
        details: The listing's cleaned details (ad text already removed by
            the caller; only its structured fields and ``low_evidence`` are
            used here).
        requirements: The LLM's extraction for this listing (FR-05 AC1).
        profile: The user's profile.
        excluded_employers: Employer names from long-term memory
            (FR-15 AC4); defaults to none.

    Returns:
        A :class:`FitAssessment` with the category, exclusion reasons kept
        separate (FR-06 AC4), per-dimension rubric verdicts, matches, gaps
        and unknown dimensions.

    Related: FR-05 AC3, FR-05 AC5, FR-06, spec §7
    """
    exclusion_reasons = hard_exclusions(
        details, profile, excluded_employers or [], distance_km=summary.distance_km
    )

    rubric: dict[str, RubricVerdict] = {
        "skills": _skills_verdict(requirements, profile),
        "location_remote": _location_remote_verdict(summary, details, profile),
        "seniority": _seniority_verdict(requirements, profile),
        "language": _language_verdict(requirements, profile),
        "employment_type": _employment_type_verdict(details, profile),
    }

    known_dimensions = {dim: verdict for dim, verdict in rubric.items() if verdict != "unknown"}
    unknown_dimensions = [dim for dim, verdict in rubric.items() if verdict == "unknown"]

    numerator = sum(
        VERDICT_POINTS[verdict] * DIMENSION_WEIGHTS[dim]
        for dim, verdict in known_dimensions.items()
    )
    denominator = sum(DIMENSION_WEIGHTS[dim] for dim in known_dimensions) * max(
        VERDICT_POINTS.values()
    )
    share = numerator / denominator if denominator else 0.0

    category: FitCategory
    if share >= STRONG_THRESHOLD:
        category = "strong"
    elif share >= PARTIAL_THRESHOLD:
        category = "partial"
    else:
        category = "poor"

    too_many_unknowns = len(unknown_dimensions) > MAX_UNKNOWN_DIMENSIONS_BEFORE_CAP
    low_evidence = details.low_evidence or too_many_unknowns
    if too_many_unknowns and category == "strong":
        category = "partial"

    if exclusion_reasons:
        category = "excluded"

    matches = [
        f"{r.name} — {r.evidence_en}"
        for r in requirements.skills
        if skill_matches_profile(r.name, profile.skills)
    ]
    gaps = [
        f"{r.name} — {r.evidence_en}"
        for r in requirements.skills
        if not skill_matches_profile(r.name, profile.skills)
    ]
    unknown_labels = {
        "skills": "skills: none extracted",
        "location_remote": "location/remote: not mentioned in the ad",
        "seniority": "seniority: not mentioned in the ad",
        "language": "German level: not mentioned in the ad",
        "employment_type": "employment type: not mentioned in the ad",
    }
    unknown = [unknown_labels[dim] for dim in unknown_dimensions]

    return FitAssessment(
        referenznummer=requirements.referenznummer,
        category=category,
        exclusion_reasons=exclusion_reasons,
        matches=matches,
        gaps=gaps,
        unknown=unknown,
        low_evidence=low_evidence,
        rubric=rubric,
    )
