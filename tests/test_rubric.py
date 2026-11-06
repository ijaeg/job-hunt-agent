"""Tests for :mod:`job_hunt_agent.rubric` (spec §7, FR-06).

Related: FR-05, FR-06 AC1-AC4, spec §7, D-9
"""

from __future__ import annotations

from job_hunt_agent.models import JobDetails, JobRequirements, JobSummary, Profile, Requirement
from job_hunt_agent.rubric import assess, hard_exclusions, skill_matches_profile


def _profile(**overrides: object) -> Profile:
    defaults: dict[str, object] = {
        "skills": ["Python", "Java", "FastAPI", "PostgreSQL", "Docker", "CI/CD"],
        "seniority": "senior",
        "location": "Hamburg",
        "radius_km": 25,
        "remote_preference": "hybrid",
        "wants_full_time": True,
        "wants_permanent": True,
        "exclude_temp_agency": True,
        "german_level": "basic",
        "english_level": "native",
    }
    defaults.update(overrides)
    return Profile.model_validate(defaults)


def _summary(**overrides: object) -> JobSummary:
    defaults: dict[str, object] = {
        "referenznummer": "19522-0068291613-S",
        "title": "Python-Entwickler",
        "distance_km": 10.0,
        "remote_type": "ANGABE_IN_PROZENT",
        "remote_percent": 50,
    }
    defaults.update(overrides)
    return JobSummary.model_validate(defaults)


def _details(**overrides: object) -> JobDetails:
    defaults: dict[str, object] = {
        "referenznummer": "19522-0068291613-S",
        "title": "Python-Entwickler",
        "employer": "Beispiel AG",
        "description": "x" * 1000,
        "is_temp_agency": False,
        "remote_type": "ANGABE_IN_PROZENT",
        "remote_percent": 50,
        "full_time": True,
        "contract_months": None,
        "low_evidence": False,
    }
    defaults.update(overrides)
    return JobDetails.model_validate(defaults)


def _requirements(**overrides: object) -> JobRequirements:
    defaults: dict[str, object] = {
        "referenznummer": "19522-0068291613-S",
        "skills": [
            Requirement(
                name="Python",
                required=True,
                evidence_de="Python-Kenntnisse",
                evidence_en="Python knowledge",
            ),
        ],
        "seniority": "senior",
        "german_level": "basic",
        "english_required": True,
        "summary_en": "A role.",
    }
    defaults.update(overrides)
    return JobRequirements.model_validate(defaults)


# ---------------------------------------------------------------------------
# skill_matches_profile
# ---------------------------------------------------------------------------


def test_skill_matches_profile_exact_match() -> None:
    """An exact match (case-insensitive) counts."""
    assert skill_matches_profile("python", ["Python", "Java"])


def test_skill_matches_profile_substring_match() -> None:
    """A verbose LLM skill phrase containing a profile token still matches."""
    assert skill_matches_profile("Programmiersprachen: Java, Python, C#", ["Python"])


def test_skill_matches_profile_no_match() -> None:
    """An unrelated skill does not match."""
    assert not skill_matches_profile("Kubernetes orchestration", ["Python", "Java"])


def test_skill_matches_profile_java_does_not_match_javascript() -> None:
    """WP-03: whole-word matching - "Java" must not match inside "JavaScript"."""
    assert not skill_matches_profile("JavaScript", ["Java"])


def test_skill_matches_profile_c_does_not_match_ci_cd() -> None:
    """WP-03: "C" must not match inside "CI/CD"."""
    assert not skill_matches_profile("CI/CD", ["C"])


def test_skill_matches_profile_r_does_not_match_docker() -> None:
    """WP-03: "R" must not match inside "Docker"."""
    assert not skill_matches_profile("Docker", ["R"])


def test_skill_matches_profile_c_sharp_matches_c_sharp_dot_net() -> None:
    """WP-03: "C#" matches "C#/.NET" - the "/" right after is a non-word boundary."""
    assert skill_matches_profile("C#/.NET", ["C#"])


def test_skill_matches_profile_c_plus_plus_does_not_match_versioned_suffix() -> None:
    """WP-03: "C++" does NOT match "C++17" - "1" right after is a word character.

    Documented, accepted asymmetry of whole-word matching (see
    ``skill_matches_profile``'s docstring): a bare version suffix with no
    separator breaks the trailing boundary, unlike "C#/.NET" above where
    the next character ("/") is non-word.
    """
    assert not skill_matches_profile("C++17", ["C++"])


def test_skill_matches_profile_ci_cd_matches_hyphenated_suffix() -> None:
    """WP-03: "CI/CD" matches "CI/CD-Pipelines" - "-" is a non-word boundary."""
    assert skill_matches_profile("CI/CD-Pipelines", ["CI/CD"])


def test_skill_matches_profile_python_in_compound_german_phrase() -> None:
    """WP-03: "Python" matches inside a comma-separated German skill list."""
    assert skill_matches_profile("Programmiersprachen: Java, Python, C#", ["Python"])


# ---------------------------------------------------------------------------
# hard_exclusions (FR-06 AC1-AC4)
# ---------------------------------------------------------------------------


def test_hard_exclusion_temp_agency_when_profile_excludes_it() -> None:
    """FR-06 AC1: temp-agency listing is excluded when the profile excludes it."""
    reasons = hard_exclusions(_details(is_temp_agency=True), _profile(), [])
    assert any("agency" in r.lower() for r in reasons)


def test_no_exclusion_for_temp_agency_when_profile_allows_it() -> None:
    """FR-06 AC1: a profile that does not exclude temp agency work is not excluded."""
    reasons = hard_exclusions(
        _details(is_temp_agency=True), _profile(exclude_temp_agency=False), []
    )
    assert reasons == []


def test_missing_temp_agency_value_never_excludes() -> None:
    """FR-06 AC3: a missing structured value never excludes on its own."""
    reasons = hard_exclusions(_details(is_temp_agency=None), _profile(), [])
    assert reasons == []


def test_hard_exclusion_distance_exceeds_radius_without_full_remote() -> None:
    """FR-06 AC2: too far away, and not fully remote, is excluded."""
    reasons = hard_exclusions(
        _details(remote_percent=50), _profile(radius_km=25), [], distance_km=100.0
    )
    assert any("distance" in r.lower() for r in reasons)


def test_no_distance_exclusion_when_fully_remote() -> None:
    """FR-06 AC2: full remote work overrides an out-of-radius distance."""
    reasons = hard_exclusions(
        _details(remote_percent=100), _profile(radius_km=25), [], distance_km=500.0
    )
    assert reasons == []


def test_missing_distance_never_excludes() -> None:
    """FR-06 AC3: an unknown distance never excludes."""
    reasons = hard_exclusions(_details(), _profile(radius_km=25), [], distance_km=None)
    assert reasons == []


def test_excluded_employer_from_memory() -> None:
    """FR-15 AC4: an employer in long-term memory is excluded by code."""
    reasons = hard_exclusions(
        _details(employer="Acme Staffing GmbH"), _profile(), ["acme staffing gmbh"]
    )
    assert any("excluded by you" in r for r in reasons)


def test_employer_not_in_exclusion_list_is_not_excluded() -> None:
    """An employer not on the list is not excluded."""
    reasons = hard_exclusions(_details(employer="Beispiel AG"), _profile(), ["Acme Staffing GmbH"])
    assert reasons == []


def test_multiple_exclusion_reasons_can_combine() -> None:
    """Several hard-exclusion rules can fire for the same listing."""
    reasons = hard_exclusions(
        _details(is_temp_agency=True, employer="Acme Staffing GmbH", remote_percent=0),
        _profile(radius_km=10),
        ["Acme Staffing GmbH"],
        distance_km=50.0,
    )
    assert len(reasons) == 3


# ---------------------------------------------------------------------------
# assess: skills dimension (spec §7 "Skills")
# ---------------------------------------------------------------------------


def _skill(name: str, required: bool = True) -> Requirement:
    return Requirement(name=name, required=required, evidence_de=name, evidence_en=name)


def test_skills_met_when_at_least_70_percent_match() -> None:
    """met: >= 70% of required skills found in the profile."""
    reqs = _requirements(skills=[_skill("Python"), _skill("Java"), _skill("FastAPI")])
    result = assess(_summary(), _details(), reqs, _profile())
    assert result.rubric["skills"] == "met"


def test_skills_partly_between_40_and_69_percent() -> None:
    """partly: 40-69% of required skills found."""
    reqs = _requirements(
        skills=[_skill("Python"), _skill("Java"), _skill("Rust"), _skill("Go"), _skill("Scala")]
    )
    result = assess(_summary(), _details(), reqs, _profile())
    assert result.rubric["skills"] == "partly"


def test_skills_not_met_below_40_percent() -> None:
    """not_met: < 40% of required skills found."""
    reqs = _requirements(
        skills=[
            _skill("Rust"),
            _skill("Go"),
            _skill("Scala"),
            _skill("Elixir"),
            _skill("Haskell"),
            _skill("Erlang"),
        ]
    )
    result = assess(_summary(), _details(), reqs, _profile())
    assert result.rubric["skills"] == "not_met"


def test_skills_unknown_when_none_extracted_at_all() -> None:
    """unknown: no skills extracted at all (spec §7, as revised by D-9)."""
    reqs = _requirements(skills=[])
    result = assess(_summary(), _details(), reqs, _profile())
    assert result.rubric["skills"] == "unknown"


def test_skills_counts_non_required_skills_too() -> None:
    """D-9: a skill not flagged ``required`` still counts (gpt-5-mini rarely sets it)."""
    reqs = _requirements(
        skills=[
            _skill("Python", required=False),
            _skill("Java", required=False),
            _skill("FastAPI", required=False),
        ]
    )
    result = assess(_summary(), _details(), reqs, _profile())
    assert result.rubric["skills"] == "met"


def test_matches_and_gaps_list_required_skills() -> None:
    """Matched required skills go to ``matches``, missing ones to ``gaps``."""
    reqs = _requirements(skills=[_skill("Python"), _skill("Rust")])
    result = assess(_summary(), _details(), reqs, _profile())
    assert any("Python" in m for m in result.matches)
    assert any("Rust" in g for g in result.gaps)


# ---------------------------------------------------------------------------
# assess: location/remote dimension (spec §7 "Location / remote")
# ---------------------------------------------------------------------------


def test_location_met_within_radius_and_remote_satisfied() -> None:
    """met: within radius and remote preference satisfied."""
    summary = _summary(distance_km=10.0, remote_percent=60)
    result = assess(summary, _details(remote_percent=60), _requirements(), _profile())
    assert result.rubric["location_remote"] == "met"


def test_location_partly_within_radius_remote_not_stated() -> None:
    """partly: within radius, remote not stated at all."""
    summary = _summary(distance_km=10.0, remote_percent=None, remote_type=None)
    result = assess(
        summary, _details(remote_percent=None, remote_type=None), _requirements(), _profile()
    )
    assert result.rubric["location_remote"] == "partly"


def test_location_not_met_outside_radius_without_full_remote() -> None:
    """not_met: outside radius without full remote work."""
    summary = _summary(distance_km=100.0, remote_percent=20)
    result = assess(summary, _details(remote_percent=20), _requirements(), _profile(radius_km=25))
    assert result.rubric["location_remote"] == "not_met"


def test_location_met_outside_radius_with_full_remote() -> None:
    """Full remote work satisfies the dimension even outside the radius."""
    summary = _summary(distance_km=500.0, remote_percent=100)
    result = assess(summary, _details(remote_percent=100), _requirements(), _profile(radius_km=25))
    assert result.rubric["location_remote"] == "met"


def test_location_onsite_preference_never_needs_remote() -> None:
    """An onsite-preferring profile is satisfied by proximity alone."""
    summary = _summary(distance_km=5.0, remote_percent=None, remote_type=None)
    result = assess(
        summary,
        _details(remote_percent=None, remote_type=None),
        _requirements(),
        _profile(remote_preference="onsite"),
    )
    assert result.rubric["location_remote"] == "met"


# ---------------------------------------------------------------------------
# assess: seniority dimension (spec §7 "Seniority")
# ---------------------------------------------------------------------------


def test_seniority_met_same_level() -> None:
    """met: same seniority level."""
    result = assess(_summary(), _details(), _requirements(seniority="senior"), _profile())
    assert result.rubric["seniority"] == "met"


def test_seniority_partly_one_level_apart() -> None:
    """partly: one level apart."""
    result = assess(_summary(), _details(), _requirements(seniority="mid"), _profile())
    assert result.rubric["seniority"] == "partly"


def test_seniority_not_met_two_levels_apart() -> None:
    """not_met: two or more levels apart."""
    result = assess(_summary(), _details(), _requirements(seniority="junior"), _profile())
    assert result.rubric["seniority"] == "not_met"


def test_seniority_unknown_when_not_mentioned() -> None:
    """unknown: seniority not mentioned in the ad."""
    result = assess(_summary(), _details(), _requirements(seniority="not_mentioned"), _profile())
    assert result.rubric["seniority"] == "unknown"


# ---------------------------------------------------------------------------
# assess: language dimension (spec §7 "Language")
# ---------------------------------------------------------------------------


def test_language_met_when_requirement_at_or_below_user_level() -> None:
    """met: requirement <= user's level."""
    result = assess(
        _summary(), _details(), _requirements(german_level="basic"), _profile(german_level="basic")
    )
    assert result.rubric["language"] == "met"


def test_language_met_when_user_level_exceeds_requirement() -> None:
    """met: the user's level comfortably exceeds the requirement."""
    result = assess(
        _summary(), _details(), _requirements(german_level="none"), _profile(german_level="native")
    )
    assert result.rubric["language"] == "met"


def test_language_partly_one_level_above() -> None:
    """partly: requirement one level above the user's."""
    result = assess(
        _summary(), _details(), _requirements(german_level="fluent"), _profile(german_level="basic")
    )
    assert result.rubric["language"] == "partly"


def test_language_not_met_two_or_more_levels_above() -> None:
    """not_met: requirement two or more levels above the user's."""
    result = assess(
        _summary(), _details(), _requirements(german_level="native"), _profile(german_level="basic")
    )
    assert result.rubric["language"] == "not_met"


def test_language_unknown_when_not_mentioned() -> None:
    """unknown: German level not mentioned in the ad."""
    result = assess(_summary(), _details(), _requirements(german_level="not_mentioned"), _profile())
    assert result.rubric["language"] == "unknown"


# ---------------------------------------------------------------------------
# assess: employment-type dimension (spec §7 "Employment type")
# ---------------------------------------------------------------------------


def test_employment_type_matches() -> None:
    """matches: full-time and permanent, as the profile wants."""
    result = assess(
        _summary(),
        _details(full_time=True, contract_months=None),
        _requirements(),
        _profile(wants_full_time=True, wants_permanent=True),
    )
    assert result.rubric["employment_type"] == "met"


def test_employment_type_does_not_match_fixed_term() -> None:
    """does not match: a fixed-term contract when the profile wants permanent."""
    result = assess(
        _summary(),
        _details(full_time=True, contract_months=12),
        _requirements(),
        _profile(wants_full_time=True, wants_permanent=True),
    )
    assert result.rubric["employment_type"] == "not_met"


def test_employment_type_unknown_when_nothing_stated() -> None:
    """not stated: neither full-time nor contract duration is given."""
    result = assess(
        _summary(),
        _details(full_time=None, contract_months=None),
        _requirements(),
        _profile(),
    )
    assert result.rubric["employment_type"] == "unknown"


# ---------------------------------------------------------------------------
# Overall category thresholds and the unknown-dimension cap (spec §7)
# ---------------------------------------------------------------------------


def test_category_strong_at_or_above_75_percent() -> None:
    """strong: share of reached points >= 75%."""
    reqs = _requirements(
        skills=[_skill("Python"), _skill("Java")], seniority="senior", german_level="basic"
    )
    result = assess(
        _summary(distance_km=5.0, remote_percent=80),
        _details(remote_percent=80, full_time=True, contract_months=None),
        reqs,
        _profile(),
    )
    assert result.category == "strong"


def test_category_poor_below_45_percent() -> None:
    """poor: share of reached points < 45%."""
    reqs = _requirements(
        skills=[_skill("Rust"), _skill("Go"), _skill("Scala")],
        seniority="junior",
        german_level="native",
    )
    result = assess(
        _summary(distance_km=20.0, remote_percent=0),
        _details(remote_percent=0, full_time=False, contract_months=12),
        reqs,
        _profile(radius_km=25, wants_full_time=True, wants_permanent=True),
    )
    assert result.category == "poor"
    assert result.exclusion_reasons == []


def test_hard_exclusion_overrides_a_high_score() -> None:
    """Any hard exclusion forces "excluded", even with an otherwise strong score."""
    reqs = _requirements(skills=[_skill("Python"), _skill("Java")])
    result = assess(
        _summary(distance_km=5.0, remote_percent=80),
        _details(is_temp_agency=True, remote_percent=80, full_time=True, contract_months=None),
        reqs,
        _profile(),
    )
    assert result.category == "excluded"
    assert result.exclusion_reasons != []


def test_more_than_two_unknown_dimensions_caps_category_at_partial() -> None:
    """More than 2 unknown dimensions caps the category at "partial" (spec §7)."""
    reqs = _requirements(
        skills=[_skill("Python", required=False)],
        seniority="not_mentioned",
        german_level="not_mentioned",
    )
    result = assess(
        _summary(distance_km=5.0, remote_percent=80),
        _details(remote_percent=80, full_time=None, contract_months=None),
        reqs,
        _profile(),
    )
    # skills, seniority, language, employment_type are all unknown here (4 > 2)
    assert result.category == "partial"
    assert result.low_evidence is True


def test_low_evidence_flag_from_details_is_carried_through() -> None:
    """``details.low_evidence`` (short ad text, FR-04 AC5) is carried into the assessment."""
    result = assess(_summary(), _details(low_evidence=True), _requirements(), _profile())
    assert result.low_evidence is True


def test_referenznummer_comes_from_requirements() -> None:
    """The assessment's ID is the requirement extraction's reference number."""
    result = assess(_summary(), _details(), _requirements(), _profile())
    assert result.referenznummer == "19522-0068291613-S"
