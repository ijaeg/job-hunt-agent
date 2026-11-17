"""Pure check rules for the explanation-consistency measurement (D-13 Option 2, WP-15c).

Five deterministic checks (C1-C5, spec FR-08, see ``eval/explanation_set.yaml``'s
``check_rules``) compare one follow-up answer against the thread's stored
``FitAssessment`` objects and this turn's own tool calls - no model or network call
here, so every function is unit-testable on fixed fake data
(``tests/test_explanation_checks.py``).

Related: D-13, FR-08 AC1, FR-08 AC2, spec §6.3, §9, invariant 2, WP-15c
"""

from __future__ import annotations

import re
from typing import Any

from job_hunt_agent.models import FitAssessment

CATEGORY_WORDS = ("strong", "partial", "poor", "excluded")

#: Phrases accepted as "the answer says the listing has not been assessed" (C5).
NOT_ASSESSED_PHRASES = (
    "have not assessed",
    "haven't assessed",
    "has not been assessed",
    "hasn't been assessed",
    "not yet assessed",
    "didn't assess",
    "did not assess",
    "no assessment",
    "not been evaluated",
    "haven't evaluated",
    "have not evaluated",
)

_QUOTE_PATTERN = re.compile(
    r'"(?P<straight>[^"]+)"'
    r"|„(?P<german>[^“]+)“"
    r"|“(?P<curly>[^”]+)”",
    re.UNICODE,
)


def _normalize_ws(text: str) -> str:
    """Case- and whitespace-normalises ``text`` for verbatim-substring comparison (C1)."""
    return " ".join(text.split()).strip().lower()


def _whole_word(word: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(word)}(?!\w)", re.IGNORECASE)


def extract_quotes(answer: str) -> list[str]:
    """Quoted passages in ``answer``, any of the three quote-mark styles C1 checks."""
    quotes = []
    for match in _QUOTE_PATTERN.finditer(answer):
        quotes.append(next(g for g in match.groups() if g is not None))
    return quotes


def _strip_markers(text: str, markers: list[str]) -> str:
    """Removes every literal occurrence of each ``markers`` phrase from ``text``.

    Used so a gap phrase that contains a match-marker word as a substring (e.g.
    "not met" contains "met"; "not in your profile" contains "your profile") is
    never also read as a match marker (C2, coach review).
    """
    stripped = text
    for marker in markers:
        stripped = stripped.replace(marker, " ")
    return stripped


def split_sentences(text: str) -> list[str]:
    """Splits ``text`` into sentences for the sentence-level checks C2/C3.

    A simple heuristic (split after ``.``/``!``/``?``/newline followed by
    whitespace) - good enough for short, plainly-punctuated model answers; not a
    real sentence parser.
    """
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def check_quote_fidelity(answer: str, assessments: list[FitAssessment]) -> list[dict[str, str]]:
    """C1: every >=4-word quoted passage must be a verbatim substring of stored evidence.

    Checked against *all* of the thread's stored assessments (every listing
    assessed so far in the thread), not only the question's own listing - a
    follow-up may legitimately quote evidence surfaced in an earlier turn.
    """
    evidence_pool = [
        _normalize_ws(evidence)
        for assessment in assessments
        for match_evidence in (*assessment.matches, *assessment.gaps)
        for evidence in (match_evidence.evidence_de, match_evidence.evidence_en)
    ]
    flags = []
    for quote in extract_quotes(answer):
        if len(quote.split()) < 4:
            continue
        normalized = _normalize_ws(quote)
        if not any(normalized in evidence for evidence in evidence_pool):
            flags.append(
                {"quote": quote, "reason": "not a verbatim substring of any stored evidence"}
            )
    return flags


def check_match_gap_consistency(
    answer: str,
    assessment: FitAssessment,
    match_markers: list[str],
    gap_markers: list[str],
) -> list[dict[str, str]]:
    """C2: flags a matched skill co-occurring with a gap marker, or vice versa.

    Gap markers are evaluated first and stripped out of the sentence before it is
    searched for match markers, so a gap phrase containing a match-marker word as
    a substring (e.g. "not met" contains "met"; "not in your profile" contains
    "your profile") is never also read as a match marker (coach review). Heuristic
    sentence-level co-occurrence otherwise (documented limitation) - every flag is
    meant to be read by a person and reported as confirmed or a false alarm.
    """
    flags = []
    for sentence in split_sentences(answer):
        lowered = sentence.lower()
        for match_evidence in assessment.matches:
            if match_evidence.name.lower() in lowered and any(
                marker in lowered for marker in gap_markers
            ):
                flags.append(
                    {
                        "sentence": sentence,
                        "skill": match_evidence.name,
                        "type": "match_presented_as_gap",
                    }
                )
        cleaned_of_gap_markers = _strip_markers(lowered, gap_markers)
        for gap_evidence in assessment.gaps:
            if gap_evidence.name.lower() in lowered and any(
                marker in cleaned_of_gap_markers for marker in match_markers
            ):
                flags.append(
                    {
                        "sentence": sentence,
                        "skill": gap_evidence.name,
                        "type": "gap_presented_as_match",
                    }
                )
    return flags


def check_category_consistency(
    answer: str,
    referenznummer: str,
    title: str,
    employer: str,
    assessment: FitAssessment,
) -> list[dict[str, str]]:
    """C3: a category word stated for a listing must equal its stored category."""
    flags = []
    for sentence in split_sentences(answer):
        lowered = sentence.lower()
        mentions_listing = (
            referenznummer.lower() in lowered
            or title.lower() in lowered
            or employer.lower() in lowered
        )
        if not mentions_listing:
            continue
        for word in CATEGORY_WORDS:
            if _whole_word(word).search(lowered) and word != assessment.category:
                flags.append(
                    {
                        "sentence": sentence,
                        "stated_category": word,
                        "stored_category": assessment.category,
                    }
                )
    return flags


def check_no_new_tool_call(tool_calls: list[dict[str, Any]]) -> bool:
    """C4: turns a-c must not call any tool (FR-08 AC1 - answered from state)."""
    return not tool_calls


def check_turn_d(
    answer: str, tool_calls: list[dict[str, Any]], referenznummer: str
) -> tuple[bool, str]:
    """C5: a question about a listing not yet assessed in the thread.

    Passes if ``assess_fit`` was called for ``referenznummer`` in this turn, or the
    answer states the listing has not been assessed; fails if the answer states a
    category word for it without that tool call. A vaguer answer that neither
    declines nor states a category is not separately scored - a documented
    limitation (see ``docs/explanation_check.md``).
    """
    called = any(
        call.get("name") == "assess_fit"
        and referenznummer in (call.get("args", {}).get("referenznummern") or [])
        for call in tool_calls
    )
    if called:
        return True, "assess_fit called for the listing in this turn"
    lowered = answer.lower()
    if any(phrase in lowered for phrase in NOT_ASSESSED_PHRASES):
        return True, "answer states the listing has not been assessed"
    for word in CATEGORY_WORDS:
        if _whole_word(word).search(lowered):
            return False, f"answer states category {word!r} without a new assess_fit call"
    return True, "no category word stated; treated as pass (see limitations)"
