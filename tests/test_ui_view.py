"""Tests for :mod:`job_hunt_agent.ui_view` (FR-07).

Related: FR-07 AC1-AC4, FR-06 AC3, D-11
"""

from __future__ import annotations

from datetime import date

from job_hunt_agent.models import FitAssessment, JobSummary
from job_hunt_agent.ui_view import (
    build_card,
    build_cards,
    listing_url,
    low_evidence_note,
    order_cards,
)


def _summary(**overrides: object) -> JobSummary:
    defaults: dict[str, object] = {
        "referenznummer": "19522-0068291613-S",
        "title": "Python-Entwickler",
        "employer": "Acme GmbH",
        "location": "Hamburg",
        "distance_km": 10.0,
        "published_date": date(2026, 11, 1),
        "remote_type": "ANGABE_IN_PROZENT",
        "remote_percent": 50,
    }
    defaults.update(overrides)
    return JobSummary.model_validate(defaults)


def _assessment(**overrides: object) -> FitAssessment:
    defaults: dict[str, object] = {
        "referenznummer": "19522-0068291613-S",
        "category": "strong",
        "matches": ["Python — writes production Python"],
        "gaps": [],
        "unknown": [],
        "low_evidence": False,
        "rubric": {},
    }
    defaults.update(overrides)
    return FitAssessment.model_validate(defaults)


# ---------------------------------------------------------------------------
# listing_url
# ---------------------------------------------------------------------------


def test_listing_url_embeds_the_referenznummer() -> None:
    url = listing_url("19522-0068291613-S")
    assert url == "https://www.arbeitsagentur.de/jobsuche/jobdetail/19522-0068291613-S"


# ---------------------------------------------------------------------------
# low_evidence_note (FR-07 AC4)
# ---------------------------------------------------------------------------


def test_low_evidence_note_present_when_flagged() -> None:
    assert low_evidence_note(True) == "Short ad text – open the original listing"


def test_low_evidence_note_absent_when_not_flagged() -> None:
    assert low_evidence_note(False) is None


# ---------------------------------------------------------------------------
# build_card: combining summaries + assessments (FR-07 AC1)
# ---------------------------------------------------------------------------


def test_build_card_uses_summary_fields() -> None:
    card = build_card("19522-0068291613-S", _summary(), _assessment())
    assert card.title == "Python-Entwickler"
    assert card.employer == "Acme GmbH"
    assert card.location == "Hamburg"
    assert card.distance_km == 10.0
    assert card.published_date == "2026-11-01"
    assert card.url == "https://www.arbeitsagentur.de/jobsuche/jobdetail/19522-0068291613-S"
    assert card.category == "strong"
    assert card.missing_summary is False


def test_build_card_falls_back_gracefully_without_a_summary() -> None:
    """FR-06 AC3: a missing summary degrades gracefully, never breaks the card."""
    card = build_card("00000-0000000000-S", None, _assessment(referenznummer="00000-0000000000-S"))
    assert card.title == "00000-0000000000-S"
    assert card.employer is None
    assert card.location is None
    assert card.missing_summary is True


def test_build_card_caps_matches_at_three() -> None:
    assessment = _assessment(matches=[f"Skill {i} — evidence {i}" for i in range(5)])
    card = build_card("19522-0068291613-S", _summary(), assessment)
    assert len(card.matches) == 3


# ---------------------------------------------------------------------------
# build_cards: skips a shortlist entry with no assessment yet
# ---------------------------------------------------------------------------


def test_build_cards_skips_unassessed_shortlist_entries() -> None:
    cards = build_cards(
        shortlist=["A-1-S", "B-2-S"],
        summaries={"A-1-S": _summary(referenznummer="A-1-S")},
        assessments={"A-1-S": _assessment(referenznummer="A-1-S")},
    )
    assert [c.referenznummer for c in cards] == ["A-1-S"]


# ---------------------------------------------------------------------------
# order_cards (FR-07 AC2)
# ---------------------------------------------------------------------------


def test_order_cards_orders_strong_partial_poor_and_separates_excluded() -> None:
    cards = [
        build_card("P", None, _assessment(referenznummer="P", category="poor")),
        build_card("E", None, _assessment(referenznummer="E", category="excluded")),
        build_card("S", None, _assessment(referenznummer="S", category="strong")),
        build_card("T", None, _assessment(referenznummer="T", category="partial")),
    ]
    visible, excluded = order_cards(cards)
    assert [c.referenznummer for c in visible] == ["S", "T", "P"]
    assert [c.referenznummer for c in excluded] == ["E"]
