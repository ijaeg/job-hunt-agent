"""Pure view helpers for the shortlist cards (FR-07). No Streamlit import here.

Like ``rubric.py`` and ``pii.py``, this module has no LLM or network calls
(CLAUDE.md "Architecture and dependency direction") - ``app.py`` calls these
functions with data already in ``JobHuntState`` and renders the result.

Related: FR-07 AC1-AC4, NFR-04, D-11
"""

from __future__ import annotations

from dataclasses import dataclass, field

from job_hunt_agent.models import FitAssessment, JobSummary, MatchEvidence

#: Order the cards group into (FR-07 AC2); "excluded" is rendered separately,
#: not in this list.
_CATEGORY_ORDER: dict[str, int] = {"strong": 0, "partial": 1, "poor": 2}

#: FR-07 AC1: at most this many matches are shown per card.
MAX_MATCHES_SHOWN = 3

#: FR-07 AC4.
LOW_EVIDENCE_NOTE = "Short ad text – open the original listing"

#: Public BA Jobsuche web app URL template for one listing (FR-07 AC1's "link
#: to the listing"). Unverified against a real response (D-1's spike only
#: exercised the JSON API, `config.BA_BASE_URL`); if this scheme turns out to
#: be wrong, only this one constant changes.
_BA_LISTING_URL_TEMPLATE = "https://www.arbeitsagentur.de/jobsuche/jobdetail/{referenznummer}"


def listing_url(referenznummer: str) -> str:
    """Builds the public BA Jobsuche web link for one listing (FR-07 AC1).

    Args:
        referenznummer: The listing's reference number.

    Returns:
        The listing's web URL.

    Related: FR-07 AC1
    """
    return _BA_LISTING_URL_TEMPLATE.format(referenznummer=referenznummer)


@dataclass
class CardData:
    """Everything one shortlist card needs to render (FR-07 AC1).

    ``title``/``employer``/... come from :class:`JobSummary`; when no
    summary was cached for this ``referenznummer`` (e.g. ``assess_fit`` was
    called on a listing this thread never searched for - a possible gap,
    not excluded by the rubric either, FR-06 AC3), those fields fall back to
    ``None`` rather than failing the card.
    """

    referenznummer: str
    title: str
    employer: str | None
    location: str | None
    distance_km: float | None
    remote_type: str | None
    remote_percent: int | None
    published_date: str | None
    url: str
    category: str
    exclusion_reasons: list[str] = field(default_factory=list)
    matches: list[MatchEvidence] = field(default_factory=list)
    gaps: list[MatchEvidence] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    low_evidence: bool = False
    missing_summary: bool = False


def low_evidence_note(low_evidence: bool) -> str | None:
    """FR-07 AC4's note, or ``None`` if the listing's ad text was not short."""
    return LOW_EVIDENCE_NOTE if low_evidence else None


def build_card(
    referenznummer: str, summary: JobSummary | None, assessment: FitAssessment
) -> CardData:
    """Combines a cached :class:`JobSummary` and a :class:`FitAssessment` into one card.

    Args:
        referenznummer: The listing's reference number.
        summary: The cached search-time summary, or ``None`` if this
            listing was never returned by ``search_jobs`` in this thread.
        assessment: The computed fit result (never built by the model,
            invariant 2).

    Related: FR-07 AC1, FR-06 AC3
    """
    return CardData(
        referenznummer=referenznummer,
        title=summary.title if summary else referenznummer,
        employer=summary.employer if summary else None,
        location=summary.location if summary else None,
        distance_km=summary.distance_km if summary else None,
        remote_type=summary.remote_type if summary else None,
        remote_percent=summary.remote_percent if summary else None,
        published_date=summary.published_date.isoformat()
        if summary and summary.published_date
        else None,
        url=listing_url(referenznummer),
        category=assessment.category,
        exclusion_reasons=assessment.exclusion_reasons,
        matches=assessment.matches[:MAX_MATCHES_SHOWN],
        gaps=assessment.gaps,
        unknown=assessment.unknown,
        low_evidence=assessment.low_evidence,
        missing_summary=summary is None,
    )


def build_cards(
    shortlist: list[str],
    summaries: dict[str, JobSummary],
    assessments: dict[str, FitAssessment],
) -> list[CardData]:
    """Builds one card per shortlisted, assessed listing, in shortlist order.

    A ``referenznummer`` in ``shortlist`` with no entry in ``assessments``
    yet (should not happen - ``assess_fit`` adds to both together, but
    nothing enforces it) is skipped rather than raising, so a partial state
    never breaks the page.

    Related: FR-07 AC1
    """
    return [
        build_card(ref, summaries.get(ref), assessments[ref])
        for ref in shortlist
        if ref in assessments
    ]


def order_cards(cards: list[CardData]) -> tuple[list[CardData], list[CardData]]:
    """Splits and orders cards for FR-07 AC2: strong -> partial -> poor, excluded separate.

    Returns:
        A tuple of (visible cards, ordered by category; excluded cards,
        in their original order).
    """
    visible = sorted(
        (c for c in cards if c.category != "excluded"),
        key=lambda c: _CATEGORY_ORDER[c.category],
    )
    excluded = [c for c in cards if c.category == "excluded"]
    return visible, excluded
