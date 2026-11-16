"""Fit rubric and hard exclusions (spec §7, FR-06).

Pure functions, no LLM or network calls (CLAUDE.md "Architecture"). The
language model only extracts :class:`JobRequirements` from the free text;
every exclusion, verdict, weight and category here is code, never
overridden by the model (invariant 2, CLAUDE.md).

Weights and thresholds are **start values** confirmed/adjusted in
``docs/decisions/D-9-rubric-start-values.md`` - change them there, not by
editing this module ad hoc, so the decision record stays the source of
truth for *why* a number is what it is.

Related: FR-06 AC1-AC4, spec §7, D-9, D-21, D-23, D-25, D-26, D-27
"""

from __future__ import annotations

import re

from job_hunt_agent.models import (
    FitAssessment,
    FitCategory,
    GermanLevel,
    GermanLevelOrUnmentioned,
    JobDetails,
    JobRequirements,
    JobSummary,
    MatchEvidence,
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

#: Skills-dimension threshold: number of distinct profile skills the ad
#: names (WP-14b, D-26, D-27 - replaces D-9's "share of all extracted
#: skills" metric; see ``_skills_verdict``'s docstring).
SKILLS_MATCHED_THRESHOLD = 3

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


def _whole_word_pattern(token: str) -> re.Pattern[str]:
    """A case-insensitive "whole word" pattern for ``token`` inside a larger string.

    Plain ``\\b`` fails on tokens that end or start with a non-word
    character (``C#``, ``C++``, ``CI/CD``): ``\\b`` only fires at a
    word/non-word transition, so ``\\bC#\\b`` never matches at all (``#``
    is non-word on both sides, so there is no trailing word boundary to
    anchor on). Lookarounds anchored on "not a word character" give the
    same whole-word guarantee without that failure mode.
    """
    return re.compile(rf"(?<!\w){re.escape(token)}(?!\w)", re.IGNORECASE)


def skill_matches_profile(requirement_name: str, profile_skills: list[str]) -> bool:
    """Whether an extracted skill counts as present in the profile.

    **D-9 (2026-11-06, revised in WP-03):** whole-word, case-insensitive
    matching of a profile skill token against the requirement name, exactly
    as spec §7 describes ("required skills in profile"). The previous
    implementation matched on a plain substring, which let "Java" match
    "JavaScript", "C" match "CI/CD" and "R" match "Docke**r**" - false
    matches that overstated fit. Whole-word matching fixes those while
    still matching "Python" inside "Programmiersprachen: Java, Python, C#"
    (comma/space on both sides count as non-word).

    **Known limitation, by design of the whole-word rule:** a version
    suffix directly after the token with no separator breaks the trailing
    boundary - "C++" does **not** match "C++17" (the "1" right after "++"
    is a word character, so ``(?!\\w)`` fails), while "C#" **does** match
    "C#/.NET" (the "/" right after is non-word). This asymmetry is an
    accepted consequence of using a word-character boundary, not a bug;
    revisit only if real extractions turn out to append bare version
    numbers to skill tokens often enough to matter (none of the 5 D-4
    listings did).

    Related: FR-05 AC1, spec §7 "Skills", D-9
    """
    return any(
        _whole_word_pattern(skill.strip()).search(requirement_name)
        for skill in profile_skills
        if skill.strip()
    )


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


def _matched_profile_skills(requirements: JobRequirements, profile: Profile) -> set[str]:
    """Distinct profile skills found (whole-word, D-9) among the ad's extracted skills."""
    return {
        skill
        for skill in profile.skills
        if any(
            skill_matches_profile(requirement.name, [skill]) for requirement in requirements.skills
        )
    }


def _skills_verdict(requirements: JobRequirements, profile: Profile) -> RubricVerdict:
    """Number of distinct profile skills the ad names (WP-14b, D-26, D-27).

    **D-27 (2026-11-16):** replaces D-9's "share of all extracted skills"
    metric. That metric made ``skills: not_met`` fire on all 12 WP-14 round-1
    test listings - real ads name 10-60 technologies, so even 2-3 genuine
    matches to Alex's 6-skill profile rarely reached the 40% share floor
    (``docs/fit_evaluation.md`` "Limitations"). This metric instead counts
    how many *distinct profile skills* the ad names, independent of how many
    unrelated skills it also lists: ``unknown`` if no skill was extracted at
    all (D-21 unchanged - a missing evidence must never count against a
    listing); ``not_met`` if none of the profile's skills are found;
    ``partly`` if 1 or 2 are found; ``met`` if 3 or more are found
    (``SKILLS_MATCHED_THRESHOLD``). N=3 was chosen over N=2 on the 20
    development listings (D-27): N=3 reached 14/20 and 15/20 category
    accuracy across two runs vs. N=2's 10/20 in both runs.

    Related: FR-05 AC1, spec §7 "Skills", D-9, D-21, D-26, D-27
    """
    if not requirements.skills:
        return "unknown"
    matched = len(_matched_profile_skills(requirements, profile))
    if matched == 0:
        return "not_met"
    if matched < SKILLS_MATCHED_THRESHOLD:
        return "partly"
    return "met"


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
        # D-23 (2026-11-16): a stated remote type without a percentage (e.g.
        # "NACH_VEREINBARUNG" - by arrangement) satisfies a hybrid preference;
        # it does not guarantee fully remote work, so it does not satisfy a
        # "remote" preference (the "else" branch below is unchanged).
        remote_satisfied = (
            full_remote
            or remote_type is not None
            or (remote_percent is not None and remote_percent > 0)
        )
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


def category_from_rubric(
    rubric: dict[str, RubricVerdict],
    exclusion_reasons: list[str],
    low_evidence: bool,
    *,
    apply_skills_not_met_cap: bool = True,
) -> tuple[FitCategory, bool]:
    """Computes the fit category from rubric verdicts alone (spec §7, D-25).

    Pulled out of :func:`assess` (WP-14b, D-26) so a re-scoring script can
    recompute the category from *stored* verdicts (e.g. with a different
    skills metric) without re-running extraction or rubric dimension logic.

    Args:
        rubric: One verdict per dimension (``skills``, ``location_remote``,
            ``seniority``, ``language``, ``employment_type``).
        exclusion_reasons: Hard-exclusion reasons (FR-06); non-empty forces
            ``excluded`` regardless of the score (FR-06 AC4).
        low_evidence: Whether the extraction itself was low-evidence (short
            ad text, FR-04 AC5) - combined here with the unknown-dimensions
            cap into the final flag.
        apply_skills_not_met_cap: Whether D-25's cap applies. Defaults to
            ``True`` (production behaviour, unchanged); ``assess`` never
            passes ``False`` - the flag exists only so WP-14b's dev-set
            re-scoring can compare the "with cap" / "without cap" variants
            D-26 asks for, without a second, duplicated function.

    Returns:
        A tuple of the category and the final ``low_evidence`` flag (input
        OR-ed with the unknown-dimensions cap).

    Related: FR-06 AC4, spec §7, D-25
    """
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
    low_evidence = low_evidence or too_many_unknowns
    if too_many_unknowns and category == "strong":
        category = "partial"

    # D-25 (2026-11-16): a clear skill mismatch caps the category at "poor"
    # regardless of the weighted share - mirrors the unknown-dimensions cap
    # above (a specific dimension outcome overriding the weighted average).
    if apply_skills_not_met_cap and rubric["skills"] == "not_met" and category != "poor":
        category = "poor"

    if exclusion_reasons:
        category = "excluded"

    return category, low_evidence


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

    Related: FR-05 AC3, FR-05 AC5, FR-06, spec §7, D-25
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

    category, low_evidence = category_from_rubric(rubric, exclusion_reasons, details.low_evidence)
    unknown_dimensions = [dim for dim, verdict in rubric.items() if verdict == "unknown"]

    matches = [
        MatchEvidence(name=r.name, evidence_de=r.evidence_de, evidence_en=r.evidence_en)
        for r in requirements.skills
        if skill_matches_profile(r.name, profile.skills)
    ]
    gaps = [
        MatchEvidence(name=r.name, evidence_de=r.evidence_de, evidence_en=r.evidence_en)
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
