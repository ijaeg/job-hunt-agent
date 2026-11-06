"""HTTP client for the BA job board API, and the demo-mode fixture source.

:class:`BAClient` talks to the real v6 search and v4 details endpoints
(D-1); :class:`FixtureSource` reads the cleaned fixture set instead
(FR-19 AC1) with the same two methods, so the tools layer (``tools/``)
can swap one for the other (injected via
:class:`job_hunt_agent.context.AgentContext`) without changing its own
code - see the :class:`JobSource` protocol below.

Related: FR-02, FR-04, FR-19 AC1, spec §8, D-1, D-2
"""

from __future__ import annotations

import base64
import json
import re
import time
from datetime import date
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import httpx

from job_hunt_agent import config
from job_hunt_agent.models import JobDetails, JobSummary
from job_hunt_agent.pii import clean_ad_text

#: Listings under this length are flagged low-evidence (FR-04 AC5).
LOW_EVIDENCE_THRESHOLD = 600


@runtime_checkable
class JobSource(Protocol):
    """Structural interface shared by :class:`BAClient` and :class:`FixtureSource`.

    Tools depend on this protocol, not on either concrete class, so the
    agent context (``AgentContext.job_source``) can hold either without any
    tool code branching on which one it is (FR-19 AC1).

    ``@runtime_checkable``: ``AgentContext`` is itself type-checked by
    Pydantic (every ``@tool``'s auto-built args schema resolves
    ``ToolRuntime``'s generic parameters, which walks into this dataclass's
    field types) - a plain, non-runtime-checkable ``Protocol`` makes that
    ``isinstance`` check raise ``TypeError`` at tool-definition time, not at
    a call site.
    """

    def search(
        self,
        keywords: str,
        location: str,
        radius_km: int = 25,
        published_within_days: int = 28,
        exclude_temp_agency: bool = True,
        page: int = 1,
    ) -> tuple[list[JobSummary], int, list[str]]: ...

    def get_details(self, referenznummer: str) -> JobDetails: ...


#: Allowed ranges for clamped search arguments (FR-02 signature, AC6).
RADIUS_KM_RANGE = (5, 200)
PUBLISHED_WITHIN_DAYS_RANGE = (1, 100)

#: Boolean operators and quote syntax the model sometimes adds to keywords
#: (FR-02 AC7, observed in spike D-4: ``AI OR "Machine Learning"``).
BOOLEAN_OPERATOR_PATTERN = re.compile(r'(?i)\b(AND|OR|NOT)\b|"')


class BAClientError(Exception):
    """Base class for every error :class:`BAClient` raises."""


class BAJobNotFoundError(BAClientError):
    """The BA details endpoint returned 404 ``STELLENANGEBOT_NICHT_GEFUNDEN`` (FR-04 AC3)."""


class BAUnavailableError(BAClientError):
    """A timeout, 429 or 5xx after the one retry of spec §8 was exhausted."""


class BAForbiddenError(BAUnavailableError):
    """403 (key rejected) - spec §8 gives this its own user-facing message, never retried."""


class BAMalformedResponseError(BAClientError):
    """The BA API returned 200 with a body that does not match the known shape."""


def sanitize_keywords(keywords: str) -> tuple[str, list[str]]:
    """Removes boolean operators and quote syntax from search keywords.

    The BA API's support for ``AND``/``OR``/``NOT`` and quoted phrases is
    unverified (FR-02 AC7); the tool description asks the model for plain
    keywords, and this function is the code-side backstop when it adds them
    anyway (seen in spike D-4: ``AI OR "Machine Learning"``).

    Args:
        keywords: Raw keywords as proposed by the model.

    Returns:
        A tuple of the cleaned keywords (collapsed whitespace) and a list
        of notes describing what was removed, empty if nothing was.

    Related: FR-02 AC7, D-4
    """
    if not BOOLEAN_OPERATOR_PATTERN.search(keywords):
        return keywords, []
    cleaned = BOOLEAN_OPERATOR_PATTERN.sub(" ", keywords)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned, [f"removed boolean operators/quote syntax from keywords: {keywords!r}"]


def _clamp(value: int, bounds: tuple[int, int], label: str, notes: list[str]) -> int:
    low, high = bounds
    if value < low:
        notes.append(f"{label} clamped from {value} to {low}")
        return low
    if value > high:
        notes.append(f"{label} clamped from {value} to {high}")
        return high
    return value


def _location_from(item: dict[str, Any]) -> str | None:
    locations = item.get("stellenlokationen") or []
    if not locations:
        return None
    adresse = locations[0].get("adresse") or {}
    ort = adresse.get("ort")
    return ort if isinstance(ort, str) else None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _job_summary_from_search_item(item: dict[str, Any]) -> JobSummary:
    referenznummer = item.get("referenznummer")
    if not isinstance(referenznummer, str):
        raise BAMalformedResponseError("search result item has no referenznummer")
    title, _ = clean_ad_text(item.get("stellenangebotsTitel", "") or "")
    return JobSummary(
        referenznummer=referenznummer,
        title=title,
        employer=item.get("firma"),
        location=_location_from(item),
        distance_km=item.get("entfernung"),
        published_date=_parse_date(item.get("datumErsteVeroeffentlichung")),
        remote_type=item.get("homeofficetyp"),
        remote_percent=item.get("homeofficeprozent"),
        salary_min=item.get("gehaltsspanneVon"),
        salary_max=item.get("gehaltsspanneBis"),
        full_time=item.get("arbeitszeitVollzeit"),
        contract_duration=item.get("vertragsdauer"),
        external_url=bool(item.get("externeURL")),
    )


def _job_details_from_response(referenznummer: str, body: dict[str, Any]) -> JobDetails:
    title, _ = clean_ad_text(body.get("stellenangebotsTitel", "") or "")
    description, _ = clean_ad_text(body.get("stellenangebotsBeschreibung", "") or "")
    return JobDetails(
        referenznummer=referenznummer,
        title=title,
        employer=body.get("firma"),
        description=description,
        is_temp_agency=body.get("istArbeitnehmerUeberlassung"),
        is_private_recruiter=body.get("istPrivateArbeitsvermittlung"),
        remote_type=body.get("homeofficetyp"),
        remote_percent=body.get("homeofficeprozent"),
        contract_months=body.get("befristungInMonaten"),
        full_time=body.get("arbeitszeitVollzeit"),
        salary_min=body.get("gehaltsspanneVon"),
        salary_max=body.get("gehaltsspanneBis"),
        low_evidence=len(description) < LOW_EVIDENCE_THRESHOLD,
    )


class BAClient:
    """Talks to the real BA job board API (v6 search, v4 details).

    Pass a pre-built ``httpx.Client`` (e.g. with a ``MockTransport``) for
    tests; without one, a real client is built from ``config.py``.

    Related: FR-02, FR-04, spec §8, D-1
    """

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            base_url=config.BA_BASE_URL,
            headers={"X-API-Key": config.BA_API_KEY, "Accept": "application/json"},
            timeout=config.BA_TIMEOUT_SECONDS,
        )
        self._details_cache: dict[str, JobDetails] = {}

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> BAClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _request(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        """One GET with spec §8's single retry on timeout, 429 or 5xx.

        Failures are never cached (spec §8): every call re-tries the
        network, even for a ``referenznummer`` that failed before.
        """
        last_exc: httpx.HTTPError | None = None
        for attempt in range(config.BA_MAX_RETRIES + 1):
            try:
                response = self._client.get(path, params=params)
            except httpx.TimeoutException as exc:
                last_exc = exc
            else:
                if response.status_code == 403:
                    raise BAForbiddenError("the job board rejected the request (403)")
                if response.status_code >= 500 or response.status_code == 429:
                    if attempt < config.BA_MAX_RETRIES:
                        time.sleep(config.BA_RETRY_DELAY_SECONDS)
                        continue
                    raise BAUnavailableError(
                        f"the job board returned {response.status_code} after retrying"
                    )
                return response
            if attempt < config.BA_MAX_RETRIES:
                time.sleep(config.BA_RETRY_DELAY_SECONDS)
        raise BAUnavailableError("the job board did not respond in time") from last_exc

    def search(
        self,
        keywords: str,
        location: str,
        radius_km: int = 25,
        published_within_days: int = 28,
        exclude_temp_agency: bool = True,
        page: int = 1,
    ) -> tuple[list[JobSummary], int, list[str]]:
        """Searches the job board (v6 ``/pc/v6/jobs``).

        Args:
            keywords: Free-text search terms (sanitized before the call).
            location: City or region name (API parameter ``wo``).
            radius_km: Search radius in km, clamped to 5-200.
            published_within_days: Maximum listing age in days, clamped to
                1-100.
            exclude_temp_agency: Maps to the API's ``zeitarbeit=false``
                (D-1 AC1).
            page: 1-based page number.

        Returns:
            A tuple of at most 25 :class:`JobSummary` objects, the API's
            reported total (``maxErgebnisse``), and a list of notes (e.g.
            clamped arguments, sanitized keywords). ``total == 0`` with an
            empty list is a normal result, not an error (FR-02 AC4).

        Raises:
            BAUnavailableError: On 403, a timeout, 429 or 5xx after retrying.
            BAMalformedResponseError: If a 200 response is not a dict, or a
                result item has no ``referenznummer``.

        Related: FR-02 AC1-AC7, D-1
        """
        notes: list[str] = []
        clean_keywords, keyword_notes = sanitize_keywords(keywords)
        notes.extend(keyword_notes)
        radius_km = _clamp(radius_km, RADIUS_KM_RANGE, "radius_km", notes)
        published_within_days = _clamp(
            published_within_days, PUBLISHED_WITHIN_DAYS_RANGE, "published_within_days", notes
        )
        page = max(page, 1)

        params: dict[str, Any] = {
            "was": clean_keywords,
            "wo": location,
            "umkreis": radius_km,
            "veroeffentlichtseit": published_within_days,
            "angebotsart": 1,
            "page": page,
            "size": 25,
        }
        if exclude_temp_agency:
            params["zeitarbeit"] = "false"

        response = self._request("/pc/v6/jobs", params=params)
        try:
            body = response.json()
        except ValueError as exc:
            raise BAMalformedResponseError("search response was not valid JSON") from exc
        if not isinstance(body, dict):
            raise BAMalformedResponseError("search response was not a JSON object")

        items = body.get("ergebnisliste") or []
        if not isinstance(items, list):
            raise BAMalformedResponseError("search response 'ergebnisliste' was not a list")

        summaries = [
            _job_summary_from_search_item(item) for item in items if isinstance(item, dict)
        ]
        total = body.get("maxErgebnisse")
        total_int = int(total) if isinstance(total, int | float) else len(summaries)
        return summaries[:25], total_int, notes

    def get_details(self, referenznummer: str) -> JobDetails:
        """Fetches one listing's details (v4 ``/pc/v4/jobdetails/{base64}``).

        Successful results are cached per ``referenznummer`` for the life
        of this client instance (FR-04 AC4); failures are never cached.

        Args:
            referenznummer: The listing's BA reference number.

        Returns:
            The cleaned :class:`JobDetails` (FR-22 AC1 already applied).

        Raises:
            BAJobNotFoundError: On 404 ``STELLENANGEBOT_NICHT_GEFUNDEN``
                (FR-04 AC3).
            BAUnavailableError: On 403, a timeout, 429 or 5xx after retrying.
            BAMalformedResponseError: If a 200 response is not a dict.

        Related: FR-04 AC1-AC5, D-1
        """
        if referenznummer in self._details_cache:
            return self._details_cache[referenznummer]

        encoded = base64.b64encode(referenznummer.encode()).decode()
        response = self._request(f"/pc/v4/jobdetails/{encoded}")

        if response.status_code == 404:
            try:
                body = response.json()
            except ValueError:
                body = {}
            codes = [m.get("code") for m in body.get("messages", []) if isinstance(m, dict)]
            if "STELLENANGEBOT_NICHT_GEFUNDEN" in codes:
                raise BAJobNotFoundError(f"listing {referenznummer} no longer available")
            raise BAMalformedResponseError(f"unexpected 404 body for {referenznummer}")

        try:
            body = response.json()
        except ValueError as exc:
            raise BAMalformedResponseError("details response was not valid JSON") from exc
        if not isinstance(body, dict):
            raise BAMalformedResponseError("details response was not a JSON object")

        details = _job_details_from_response(referenznummer, body)
        self._details_cache[referenznummer] = details
        return details


def _job_summary_from_fixture_listing(listing: dict[str, Any]) -> JobSummary:
    return JobSummary(
        referenznummer=listing["referenznummer"],
        title=listing["title"],
        employer=listing.get("employer"),
        location=listing.get("location"),
        distance_km=listing.get("distance_km"),
        published_date=_parse_date(listing.get("published_date")),
        remote_type=listing.get("remote_type"),
        remote_percent=listing.get("remote_percent"),
        salary_min=listing.get("salary_min"),
        salary_max=listing.get("salary_max"),
        full_time=listing.get("full_time"),
        contract_duration=listing.get("contract_duration"),
        external_url=bool(listing.get("external_url")),
    )


class FixtureSource:
    """Demo-mode stand-in for :class:`BAClient` (FR-19 AC1).

    Reads the cleaned fixture set built by ``scripts/build_fixtures.py``
    once at construction time; ``search`` and ``get_details`` mirror
    :class:`BAClient`'s signatures so the tools layer can use either
    interchangeably.

    For a query that exactly matches one of the 5 real D-1 searches
    (``recorded_searches.json``, sibling to the listing file), ``search``
    replays the *real* recorded total instead of the committed listing
    set's own size (at most ~6 for any query - too small to ever show the
    ">50, narrow" refinement direction, D-10 Option 4). A query that
    *narrows* a recorded one (same location, its keywords plus more terms,
    radius/age the same or smaller) filters that recorded query's own
    listings - restricted to the ones actually present in ``listings.json``
    - by the narrower criteria; this can honestly be 0 if none of that
    recorded query's listings happen to be in the committed set (D-10
    addendum, 2026-11-06 - no invented numbers either way). Any other query
    falls back to filtering the full committed listing set as before.

    Related: FR-03 AC1, FR-19 AC1, D-8, D-10
    """

    def __init__(self, fixtures_path: Path | None = None) -> None:
        path = fixtures_path or (
            config.PROJECT_ROOT / "data" / "samples" / "fixtures" / "listings.json"
        )
        raw = json.loads(path.read_text(encoding="utf-8"))
        self._listings: list[dict[str, Any]] = raw

        recorded_path = path.parent / "recorded_searches.json"
        self._recorded_searches: list[dict[str, Any]] = (
            json.loads(recorded_path.read_text(encoding="utf-8")) if recorded_path.exists() else []
        )

    def _recorded_match(
        self, keywords: str, location: str, radius_km: int, published_within_days: int
    ) -> dict[str, Any] | None:
        """A recorded search this query exactly replays, or ``None`` (D-10 Option 4).

        Matched on keywords/location (case-insensitive, trimmed), radius and
        published-within-days; ``exclude_temp_agency`` is not part of the
        match (the D-1 spike recorded these totals without that filter) and
        is still applied afterwards to whichever listings from the
        committed set happen to overlap.
        """
        key = (keywords.strip().lower(), location.strip().lower(), radius_km, published_within_days)
        for record in self._recorded_searches:
            record_key = (
                str(record["keywords"]).strip().lower(),
                str(record["location"]).strip().lower(),
                record["radius_km"],
                record["published_within_days"],
            )
            if key == record_key:
                return record
        return None

    def _narrows_recorded_query(
        self, keywords: str, location: str, radius_km: int, published_within_days: int
    ) -> dict[str, Any] | None:
        """A recorded search this query narrows, or ``None`` (D-10 addendum).

        "Narrows": same location; every one of the recorded query's own
        keyword terms is also present in this query's terms (same topic,
        possibly more specific - "the recorded keywords plus more terms");
        radius and publication age are the same or smaller. Excludes an
        exact match (``_recorded_match`` handles that case instead).
        """
        query_terms = {t.lower() for t in keywords.split() if t}
        for record in self._recorded_searches:
            if str(record["location"]).strip().lower() != location.strip().lower():
                continue
            record_terms = {t.lower() for t in str(record["keywords"]).split() if t}
            if not record_terms <= query_terms:
                continue
            radius_too_wide = radius_km > record["radius_km"]
            age_too_wide = published_within_days > record["published_within_days"]
            if radius_too_wide or age_too_wide:
                continue
            is_exact = (
                query_terms == record_terms
                and radius_km == record["radius_km"]
                and published_within_days == record["published_within_days"]
            )
            if is_exact:
                continue
            return record
        return None

    def search(
        self,
        keywords: str,
        location: str,
        radius_km: int = 25,
        published_within_days: int = 28,
        exclude_temp_agency: bool = True,
        page: int = 1,
    ) -> tuple[list[JobSummary], int, list[str]]:
        notes: list[str] = []
        clean_keywords, keyword_notes = sanitize_keywords(keywords)
        notes.extend(keyword_notes)
        radius_km = _clamp(radius_km, RADIUS_KM_RANGE, "radius_km", notes)
        page = max(page, 1)

        terms = [t.lower() for t in clean_keywords.split() if t]

        def matches(listing: dict[str, Any]) -> bool:
            if exclude_temp_agency and listing.get("is_temp_agency") is True:
                return False
            haystack = f"{listing.get('title', '')} {listing.get('employer', '')}".lower()
            if terms and not all(term in haystack for term in terms):
                return False
            if location and location.lower() not in (listing.get("location") or "").lower():
                distance = listing.get("distance_km")
                if distance is None or distance > radius_km:
                    return False
            return True

        recorded = self._recorded_match(clean_keywords, location, radius_km, published_within_days)
        narrowed_from = (
            None
            if recorded is not None
            else self._narrows_recorded_query(
                clean_keywords, location, radius_km, published_within_days
            )
        )

        if recorded is not None:
            total = int(recorded["total"])
            by_ref = {listing["referenznummer"]: listing for listing in self._listings}
            matching = [
                by_ref[ref]
                for ref in recorded["referenznummern"]
                if ref in by_ref
                and not (exclude_temp_agency and by_ref[ref].get("is_temp_agency") is True)
            ]
        elif narrowed_from is not None:
            notes.append(
                f"narrowed from the recorded query '{narrowed_from['keywords']}' / "
                f"{narrowed_from['location']} (D-10 addendum)"
            )
            candidate_refs = set(narrowed_from["referenznummern"])
            matching = [
                listing
                for listing in self._listings
                if listing["referenznummer"] in candidate_refs and matches(listing)
            ]
            total = len(matching)
        else:
            matching = [listing for listing in self._listings if matches(listing)]
            total = len(matching)

        start = (page - 1) * 25
        page_items = matching[start : start + 25]
        summaries = [_job_summary_from_fixture_listing(listing) for listing in page_items]
        return summaries, total, notes

    def get_details(self, referenznummer: str) -> JobDetails:
        for listing in self._listings:
            if listing["referenznummer"] == referenznummer:
                return JobDetails(
                    referenznummer=listing["referenznummer"],
                    title=listing["title"],
                    employer=listing.get("employer"),
                    description=listing["description"],
                    is_temp_agency=listing.get("is_temp_agency"),
                    is_private_recruiter=listing.get("is_private_recruiter"),
                    remote_type=listing.get("remote_type"),
                    remote_percent=listing.get("remote_percent"),
                    contract_months=listing.get("contract_months"),
                    full_time=listing.get("full_time"),
                    salary_min=listing.get("salary_min"),
                    salary_max=listing.get("salary_max"),
                    low_evidence=bool(listing.get("low_evidence")),
                )
        raise BAJobNotFoundError(f"listing {referenznummer} not in the fixture set")
