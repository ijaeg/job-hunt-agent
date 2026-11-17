"""Unit tests for eval/explanation_checks.py's C1-C5 rules (D-13 Option 2, WP-15c).

Fixed fake data only - no model call, no agent, no SQLite (CLAUDE.md invariant 5,
NFR-05), matching the pattern of tests/test_run_trajectory_eval.py.

Related: D-13, FR-08 AC1, FR-08 AC2, spec §6.3, §9, invariant 2, WP-15c
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from job_hunt_agent.models import FitAssessment, MatchEvidence

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "eval" / "explanation_checks.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("explanation_checks_under_test", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checks = _load_module()

MATCH_MARKERS = [
    "match",
    "matches",
    "matched",
    "met",
    "meets",
    "satisfies",
    "satisfied",
    "covers",
    "covered",
    "present",
    "you have",
    "you already have",
    "your profile",
    "in your profile",
    "you know",
]
GAP_MARKERS = [
    "gap",
    "gaps",
    "missing",
    "miss",
    "lack",
    "lacks",
    "lacking",
    "absent",
    "not met",
    "not mentioned",
    "not in your profile",
    "don't have",
    "do not have",
    "no experience",
    "you would need",
]


def _assessment(
    referenznummer: str = "11119-4964515256-S",
    category: str = "partial",
    matches: list[MatchEvidence] | None = None,
    gaps: list[MatchEvidence] | None = None,
) -> FitAssessment:
    return FitAssessment(
        referenznummer=referenznummer,
        category=category,  # type: ignore[arg-type]
        matches=matches or [],
        gaps=gaps or [],
    )


# ---------------------------------------------------------------------------
# C1: quote fidelity
# ---------------------------------------------------------------------------


def test_extract_quotes_finds_all_three_quote_styles() -> None:
    text = 'He said "straight quote here" and „German quote here“ and also “curly quote here”.'
    assert checks.extract_quotes(text) == [
        "straight quote here",
        "German quote here",
        "curly quote here",
    ]


def test_quote_fidelity_passes_for_verbatim_substring_quote() -> None:
    assessment = _assessment(
        matches=[
            MatchEvidence(
                name="Python",
                evidence_de="Erfahrung mit Python und FastAPI gewünscht",
                evidence_en="Experience with Python and FastAPI desired",
            )
        ]
    )
    answer = 'The ad says "Erfahrung mit Python und FastAPI gewünscht" for this role.'
    assert checks.check_quote_fidelity(answer, [assessment]) == []


def test_quote_fidelity_ignores_case_and_whitespace_differences() -> None:
    assessment = _assessment(
        matches=[
            MatchEvidence(
                name="Python",
                evidence_de="Erfahrung mit Python und FastAPI gewünscht",
                evidence_en="Experience with Python and FastAPI desired",
            )
        ]
    )
    answer = 'The ad says "erfahrung  mit python   und fastapi gewünscht" here.'
    assert checks.check_quote_fidelity(answer, [assessment]) == []


def test_quote_fidelity_flags_quote_stitched_from_two_evidence_entries() -> None:
    assessment = _assessment(
        matches=[
            MatchEvidence(
                name="Python", evidence_de="Python-Kenntnisse erforderlich", evidence_en="x"
            )
        ],
        gaps=[MatchEvidence(name="Java", evidence_de="Java von Vorteil", evidence_en="y")],
    )
    answer = 'The ad combines this: "Python-Kenntnisse erforderlich Java von Vorteil" overall.'
    flags = checks.check_quote_fidelity(answer, [assessment])
    assert len(flags) == 1
    assert "not a verbatim substring" in flags[0]["reason"]


def test_quote_fidelity_ignores_short_quotes_under_four_words() -> None:
    assessment = _assessment()
    answer = 'It mentions "cloud native" briefly.'
    assert checks.check_quote_fidelity(answer, [assessment]) == []


def test_quote_fidelity_checks_against_all_thread_assessments() -> None:
    first = _assessment(
        referenznummer="A",
        matches=[
            MatchEvidence(name="Docker", evidence_de="Docker Kenntnisse notwendig", evidence_en="x")
        ],
    )
    second = _assessment(referenznummer="B")
    answer = 'Earlier I noted the ad said "Docker Kenntnisse notwendig" for listing A.'
    assert checks.check_quote_fidelity(answer, [first, second]) == []


# ---------------------------------------------------------------------------
# C2: match/gap consistency
# ---------------------------------------------------------------------------


def test_match_gap_consistency_flags_match_presented_as_gap() -> None:
    assessment = _assessment(matches=[MatchEvidence(name="Java", evidence_de="x", evidence_en="y")])
    answer = "Java is missing from this listing."
    flags = checks.check_match_gap_consistency(answer, assessment, MATCH_MARKERS, GAP_MARKERS)
    assert len(flags) == 1
    assert flags[0]["type"] == "match_presented_as_gap"
    assert flags[0]["skill"] == "Java"


def test_match_gap_consistency_flags_gap_presented_as_match() -> None:
    assessment = _assessment(
        gaps=[MatchEvidence(name="Kubernetes", evidence_de="x", evidence_en="y")]
    )
    answer = "Kubernetes is matched by your profile."
    flags = checks.check_match_gap_consistency(answer, assessment, MATCH_MARKERS, GAP_MARKERS)
    assert len(flags) == 1
    assert flags[0]["type"] == "gap_presented_as_match"


def test_match_gap_consistency_no_flag_when_consistent() -> None:
    assessment = _assessment(
        matches=[MatchEvidence(name="Java", evidence_de="x", evidence_en="y")],
        gaps=[MatchEvidence(name="Kubernetes", evidence_de="x", evidence_en="y")],
    )
    answer = "Java is a match. Kubernetes is a gap - it is missing from the ad."
    assert checks.check_match_gap_consistency(answer, assessment, MATCH_MARKERS, GAP_MARKERS) == []


def test_match_gap_consistency_only_flags_same_sentence() -> None:
    assessment = _assessment(matches=[MatchEvidence(name="Java", evidence_de="x", evidence_en="y")])
    answer = "Java is a match. Something else is missing."
    assert checks.check_match_gap_consistency(answer, assessment, MATCH_MARKERS, GAP_MARKERS) == []


def test_match_gap_consistency_not_met_is_not_also_read_as_met() -> None:
    """Coach review: a gap phrase containing "met" as a substring must not trigger
    the "met" match marker and so must not be flagged as gap_presented_as_match."""
    assessment = _assessment(
        gaps=[MatchEvidence(name="Kubernetes", evidence_de="x", evidence_en="y")]
    )
    answer = "The Kubernetes requirement is not met by your experience."
    assert checks.check_match_gap_consistency(answer, assessment, MATCH_MARKERS, GAP_MARKERS) == []


def test_match_gap_consistency_not_in_your_profile_is_not_also_read_as_your_profile() -> None:
    """Coach review: "not in your profile" contains "your profile" as a substring
    and must not be flagged as gap_presented_as_match either."""
    assessment = _assessment(gaps=[MatchEvidence(name="Scala", evidence_de="x", evidence_en="y")])
    answer = "Scala is not in your profile, so this is a gap."
    assert checks.check_match_gap_consistency(answer, assessment, MATCH_MARKERS, GAP_MARKERS) == []


def test_match_gap_consistency_new_match_marker_phrase() -> None:
    assessment = _assessment(gaps=[MatchEvidence(name="Scala", evidence_de="x", evidence_en="y")])
    answer = "Scala - you already have this skill in your profile."
    flags = checks.check_match_gap_consistency(answer, assessment, MATCH_MARKERS, GAP_MARKERS)
    assert len(flags) == 1
    assert flags[0]["type"] == "gap_presented_as_match"


def test_match_gap_consistency_new_gap_marker_phrase() -> None:
    assessment = _assessment(matches=[MatchEvidence(name="Java", evidence_de="x", evidence_en="y")])
    answer = "Java - you would need this, it's not in your profile."
    flags = checks.check_match_gap_consistency(answer, assessment, MATCH_MARKERS, GAP_MARKERS)
    assert len(flags) == 1
    assert flags[0]["type"] == "match_presented_as_gap"


# ---------------------------------------------------------------------------
# C3: category consistency
# ---------------------------------------------------------------------------


def test_category_consistency_passes_when_stated_category_matches() -> None:
    assessment = _assessment(category="poor")
    answer = "Referenznummer 11119-4964515256-S got a poor fit."
    flags = checks.check_category_consistency(
        answer, "11119-4964515256-S", "Some Title", "Some Employer", assessment
    )
    assert flags == []


def test_category_consistency_flags_mismatch() -> None:
    assessment = _assessment(category="poor")
    answer = "Referenznummer 11119-4964515256-S is a strong fit."
    flags = checks.check_category_consistency(
        answer, "11119-4964515256-S", "Some Title", "Some Employer", assessment
    )
    assert len(flags) == 1
    assert flags[0]["stated_category"] == "strong"
    assert flags[0]["stored_category"] == "poor"


def test_category_consistency_ignores_sentences_about_other_listings() -> None:
    assessment = _assessment(category="poor")
    answer = "Some other listing is a strong fit, but I won't name it here."
    flags = checks.check_category_consistency(
        answer, "11119-4964515256-S", "Unmentioned Title", "Unmentioned Employer", assessment
    )
    assert flags == []


def test_category_consistency_matches_by_employer_name() -> None:
    assessment = _assessment(category="excluded")
    answer = "DEKRA Arbeit GmbH is excluded because it is a temp agency."
    flags = checks.check_category_consistency(
        answer, "11119-4964515256-S", "Some Title", "DEKRA Arbeit GmbH", assessment
    )
    assert flags == []


def test_category_consistency_matches_by_title() -> None:
    """Coach review: a sentence naming only the stored title (no referenznummer or
    employer) must still be checked, not silently skipped."""
    assessment = _assessment(category="poor")
    answer = "The senior ai data engineer role is a strong fit for you."
    flags = checks.check_category_consistency(
        answer,
        "13635-d780e451_JB5286154-S",
        "Senior AI Data Engineer",
        "DYMATRIX GmbH",
        assessment,
    )
    assert len(flags) == 1
    assert flags[0]["stated_category"] == "strong"
    assert flags[0]["stored_category"] == "poor"


# ---------------------------------------------------------------------------
# C4: no new tool call
# ---------------------------------------------------------------------------


def test_no_new_tool_call_passes_on_empty_calls() -> None:
    assert checks.check_no_new_tool_call([]) is True


def test_no_new_tool_call_fails_when_a_tool_was_called() -> None:
    assert checks.check_no_new_tool_call([{"name": "assess_fit", "args": {}}]) is False


# ---------------------------------------------------------------------------
# C5: turn d (unassessed listing)
# ---------------------------------------------------------------------------


def test_turn_d_passes_when_assess_fit_called_for_the_listing() -> None:
    tool_calls = [{"name": "assess_fit", "args": {"referenznummern": ["X-1"]}}]
    passed, _ = checks.check_turn_d("It is a partial fit.", tool_calls, "X-1")
    assert passed is True


def test_turn_d_passes_when_answer_declines() -> None:
    passed, _ = checks.check_turn_d("I have not assessed that listing yet.", [], "X-1")
    assert passed is True


def test_turn_d_fails_when_answer_states_category_without_tool_call() -> None:
    passed, detail = checks.check_turn_d("That listing looks like a strong fit.", [], "X-1")
    assert passed is False
    assert "strong" in detail


def test_turn_d_passes_when_answer_is_neutral_and_vague() -> None:
    passed, _ = checks.check_turn_d("I can look into that if you'd like.", [], "X-1")
    assert passed is True
