"""Tests for :mod:`job_hunt_agent.ba_client`.

Uses ``httpx.MockTransport`` with response shapes taken from
``spikes/NOTES.md`` § D-1 (``ergebnisliste``, ``referenznummer``,
``maxErgebnisse``, the 404 body) - never calls the real API (CLAUDE.md
invariant 5).

Related: FR-02, FR-04, FR-19 AC1, spec §8, D-1
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from job_hunt_agent import ba_client
from job_hunt_agent.ba_client import (
    BAClient,
    BAJobNotFoundError,
    BAMalformedResponseError,
    BAUnavailableError,
    FixtureSource,
    sanitize_keywords,
)

SEARCH_ITEM = {
    "stellenangebotsTitel": "Python-Entwickler (w/m/d)",
    "firma": "Beispiel AG",
    "referenznummer": "17338-c2de5ff0cd55000215-S",
    "entfernung": 2,
    "datumErsteVeroeffentlichung": "2026-11-04",
    "homeofficetyp": "ANGABE_IN_PROZENT",
    "homeofficeprozent": 50,
    "gehaltsspanneVon": 60000.0,
    "gehaltsspanneBis": 80000.0,
    "arbeitszeitVollzeit": True,
    "vertragsdauer": "UNBEFRISTET",
    "externeURL": "https://example.invalid/job",
    "stellenlokationen": [{"adresse": {"ort": "Hamburg", "plz": "20457"}}],
}

DETAILS_BODY = {
    "stellenangebotsTitel": "Python-Entwickler (w/m/d)",
    "firma": "Beispiel AG",
    "referenznummer": "17338-c2de5ff0cd55000215-S",
    "stellenangebotsBeschreibung": "Wir suchen eine Python-Entwicklerin. " * 30,
    "istArbeitnehmerUeberlassung": False,
    "istPrivateArbeitsvermittlung": False,
    "homeofficetyp": "ANGABE_IN_PROZENT",
    "homeofficeprozent": 50,
    "befristungInMonaten": None,
    "arbeitszeitVollzeit": True,
    "gehaltsspanneVon": 60000.0,
    "gehaltsspanneBis": 80000.0,
}


def _client_with(handler: Any) -> BAClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport, base_url="https://ba.test")
    return BAClient(client=http_client)


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retries sleep for real (spec §8); tests fake the clock, not the logic."""
    monkeypatch.setattr(ba_client.time, "sleep", lambda _seconds: None)


def test_sanitize_keywords_removes_boolean_operators_and_quotes() -> None:
    """FR-02 AC7: operators and quote syntax are removed and reported."""
    cleaned, notes = sanitize_keywords('AI OR "Machine Learning" AND NOT Java')
    assert "OR" not in cleaned
    assert '"' not in cleaned
    assert notes != []


def test_sanitize_keywords_leaves_plain_keywords_untouched() -> None:
    """Plain keywords produce no notes."""
    cleaned, notes = sanitize_keywords("Python Entwickler")
    assert cleaned == "Python Entwickler"
    assert notes == []


def test_search_maps_fields_from_the_real_response_shape() -> None:
    """A 200 response with ``ergebnisliste`` maps to ``JobSummary`` objects."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ergebnisliste": [SEARCH_ITEM], "maxErgebnisse": 1})

    with _client_with(handler) as client:
        summaries, total, notes = client.search("Python Entwickler", "Hamburg")

    assert total == 1
    assert notes == []
    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.referenznummer == "17338-c2de5ff0cd55000215-S"
    assert summary.employer == "Beispiel AG"
    assert summary.location == "Hamburg"
    assert summary.distance_km == 2
    assert summary.external_url is True


def test_search_with_no_results_is_normal_not_an_error() -> None:
    """FR-02 AC4: ``maxErgebnisse: 0`` with no ``ergebnisliste`` key is normal."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"maxErgebnisse": 0})

    with _client_with(handler) as client:
        summaries, total, notes = client.search("Nonexistent Role Xyz", "Nowhere")

    assert summaries == []
    assert total == 0
    assert notes == []


def test_search_clamps_radius_and_reports_it() -> None:
    """FR-02 AC6: an out-of-range radius is clamped and the clamp is reported."""
    seen_params: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_params.update(dict(request.url.params))
        return httpx.Response(200, json={"maxErgebnisse": 0})

    with _client_with(handler) as client:
        _, _, notes = client.search("Python", "Hamburg", radius_km=500)

    assert seen_params["umkreis"] == "200"
    assert any("radius_km" in note for note in notes)


def test_search_clamps_radius_below_the_minimum() -> None:
    """FR-02 AC6: a radius below 5 km is clamped up, not rejected."""
    seen_params: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_params.update(dict(request.url.params))
        return httpx.Response(200, json={"maxErgebnisse": 0})

    with _client_with(handler) as client:
        _, _, notes = client.search("Python", "Hamburg", radius_km=1)

    assert seen_params["umkreis"] == "5"
    assert any("radius_km" in note for note in notes)


def test_search_clamps_published_within_days() -> None:
    """FR-02 AC6: ``published_within_days`` is clamped to 1-100."""
    seen_params: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_params.update(dict(request.url.params))
        return httpx.Response(200, json={"maxErgebnisse": 0})

    with _client_with(handler) as client:
        _, _, notes = client.search("Python", "Hamburg", published_within_days=365)

    assert seen_params["veroeffentlichtseit"] == "100"
    assert any("published_within_days" in note for note in notes)


def test_search_item_without_referenznummer_is_malformed() -> None:
    """A result item with no ``referenznummer`` cannot be used downstream."""
    item = {k: v for k, v in SEARCH_ITEM.items() if k != "referenznummer"}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ergebnisliste": [item], "maxErgebnisse": 1})

    with _client_with(handler) as client, pytest.raises(BAMalformedResponseError):
        client.search("Python", "Hamburg")


def test_search_item_without_location_leaves_it_unset() -> None:
    """A result item with no ``stellenlokationen`` still maps, with no location."""
    item = {k: v for k, v in SEARCH_ITEM.items() if k != "stellenlokationen"}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ergebnisliste": [item], "maxErgebnisse": 1})

    with _client_with(handler) as client:
        summaries, _, _ = client.search("Python", "Hamburg")

    assert summaries[0].location is None


def test_search_unparseable_published_date_leaves_it_unset() -> None:
    """An unparseable ``datumErsteVeroeffentlichung`` does not crash the mapping."""
    item = {**SEARCH_ITEM, "datumErsteVeroeffentlichung": "not-a-date"}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ergebnisliste": [item], "maxErgebnisse": 1})

    with _client_with(handler) as client:
        summaries, _, _ = client.search("Python", "Hamburg")

    assert summaries[0].published_date is None


def test_search_maps_zeitarbeit_false_for_exclude_temp_agency() -> None:
    """FR-02 AC1: ``exclude_temp_agency=True`` maps to ``zeitarbeit=false``."""
    seen_params: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_params.update(dict(request.url.params))
        return httpx.Response(200, json={"maxErgebnisse": 0})

    with _client_with(handler) as client:
        client.search("Python", "Hamburg", exclude_temp_agency=True)

    assert seen_params["zeitarbeit"] == "false"
    assert seen_params["angebotsart"] == "1"


def test_search_403_raises_unavailable_without_retry() -> None:
    """403 (wrong API key) raises immediately - retrying a bad key is pointless."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(403, text="")

    with _client_with(handler) as client, pytest.raises(BAUnavailableError):
        client.search("Python", "Hamburg")
    assert calls == 1


def test_search_retries_once_on_500_then_succeeds() -> None:
    """Spec §8: one retry after a 5xx, then a normal result."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(500, text="server error")
        return httpx.Response(200, json={"maxErgebnisse": 0})

    with _client_with(handler) as client:
        summaries, total, _ = client.search("Python", "Hamburg")

    assert calls == 2
    assert (summaries, total) == ([], 0)


def test_search_raises_unavailable_after_exhausting_the_one_retry() -> None:
    """A persistent 5xx raises after the single retry (spec §8)."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, text="still down")

    with _client_with(handler) as client, pytest.raises(BAUnavailableError):
        client.search("Python", "Hamburg")
    assert calls == 2


def test_search_retries_once_on_timeout() -> None:
    """A timeout is retried once, then raises if it keeps happening (spec §8)."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.TimeoutException("timed out")

    with _client_with(handler) as client, pytest.raises(BAUnavailableError):
        client.search("Python", "Hamburg")
    assert calls == 2


def test_search_malformed_json_raises() -> None:
    """A 200 with a body that is not valid JSON is reported, not silently ignored."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    with _client_with(handler) as client, pytest.raises(BAMalformedResponseError):
        client.search("Python", "Hamburg")


def test_search_malformed_ergebnisliste_type_raises() -> None:
    """``ergebnisliste`` must be a list; anything else is malformed."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ergebnisliste": "not a list", "maxErgebnisse": 1})

    with _client_with(handler) as client, pytest.raises(BAMalformedResponseError):
        client.search("Python", "Hamburg")


def test_get_details_success_cleans_description() -> None:
    """FR-04 AC2: the description is cleaned before the model ever sees it."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=DETAILS_BODY)

    with _client_with(handler) as client:
        details = client.get_details("17338-c2de5ff0cd55000215-S")

    assert details.referenznummer == "17338-c2de5ff0cd55000215-S"
    assert details.is_temp_agency is False
    assert details.low_evidence is False


def test_get_details_short_text_is_flagged_low_evidence() -> None:
    """FR-04 AC5: a description under 600 characters is flagged."""
    body = {**DETAILS_BODY, "stellenangebotsBeschreibung": "Kurzer Teaser-Text."}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    with _client_with(handler) as client:
        details = client.get_details("17338-c2de5ff0cd55000215-S")

    assert details.low_evidence is True


def test_get_details_encodes_referenznummer_as_base64_in_the_path() -> None:
    """FR-04 AC1: the path segment is the base64-encoded reference number."""
    seen_path = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_path
        seen_path = request.url.path
        return httpx.Response(200, json=DETAILS_BODY)

    with _client_with(handler) as client:
        client.get_details("17338-c2de5ff0cd55000215-S")

    expected = base64.b64encode(b"17338-c2de5ff0cd55000215-S").decode()
    assert seen_path == f"/pc/v4/jobdetails/{expected}"


def test_get_details_404_with_known_code_raises_not_found() -> None:
    """FR-04 AC3: the real D-1 404 body raises ``BAJobNotFoundError``."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "timestamp": "2026-11-05T09:16:07Z",
                "messages": [{"code": "STELLENANGEBOT_NICHT_GEFUNDEN"}],
            },
        )

    with _client_with(handler) as client, pytest.raises(BAJobNotFoundError):
        client.get_details("00000-0000000000-S")


def test_get_details_404_with_unknown_code_is_malformed() -> None:
    """A 404 body that does not match the known D-1 shape is reported as malformed."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"messages": [{"code": "SOMETHING_ELSE"}]})

    with _client_with(handler) as client, pytest.raises(BAMalformedResponseError):
        client.get_details("17338-c2de5ff0cd55000215-S")


def test_get_details_caches_successful_results_for_the_session() -> None:
    """FR-04 AC4: a second call for the same reference number does not hit the network."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=DETAILS_BODY)

    with _client_with(handler) as client:
        client.get_details("17338-c2de5ff0cd55000215-S")
        client.get_details("17338-c2de5ff0cd55000215-S")

    assert calls == 1


def test_get_details_failure_is_never_cached() -> None:
    """Spec §8: a failed lookup is retried fully on the next call, not remembered."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(404, json={"messages": [{"code": "STELLENANGEBOT_NICHT_GEFUNDEN"}]})

    with _client_with(handler) as client:
        with pytest.raises(BAJobNotFoundError):
            client.get_details("00000-0000000000-S")
        with pytest.raises(BAJobNotFoundError):
            client.get_details("00000-0000000000-S")

    assert calls == 2


# ---------------------------------------------------------------------------
# FixtureSource (demo mode, FR-19 AC1)
# ---------------------------------------------------------------------------


@pytest.fixture
def fixture_path(tmp_path: Path) -> Path:
    listings = [
        {
            "referenznummer": "DEMO-0000000001-S",
            "title": "Python-Entwickler (m/w/d)",
            "employer": "Demo GmbH",
            "location": "Hamburg",
            "distance_km": 10.0,
            "published_date": "2026-11-01",
            "remote_type": "ANGABE_IN_PROZENT",
            "remote_percent": 50,
            "salary_min": 60000.0,
            "salary_max": 80000.0,
            "full_time": True,
            "contract_duration": "UNBEFRISTET",
            "external_url": False,
            "description": "Wir suchen eine Python-Entwicklerin. " * 30,
            "is_temp_agency": False,
            "is_private_recruiter": False,
            "contract_months": None,
            "low_evidence": False,
        },
        {
            "referenznummer": "DEMO-0000000002-S",
            "title": "Softwareentwickler Zeitarbeit (m/w/d)",
            "employer": "Demo Zeitarbeit GmbH",
            "location": "Hamburg",
            "distance_km": 12.0,
            "published_date": "2026-10-20",
            "remote_type": None,
            "remote_percent": None,
            "salary_min": None,
            "salary_max": None,
            "full_time": True,
            "contract_duration": "BEFRISTET",
            "external_url": False,
            "description": "Zeitarbeit bei einem Kundenbetrieb. " * 10,
            "is_temp_agency": True,
            "is_private_recruiter": False,
            "contract_months": 12,
            "low_evidence": False,
        },
    ]
    path = tmp_path / "listings.json"
    path.write_text(json.dumps(listings), encoding="utf-8")
    return path


def test_fixture_source_search_filters_by_keyword(fixture_path: Path) -> None:
    source = FixtureSource(fixtures_path=fixture_path)
    summaries, total, _ = source.search("Python", "Hamburg", exclude_temp_agency=False)
    assert total == 1
    assert summaries[0].referenznummer == "DEMO-0000000001-S"


def test_fixture_source_search_excludes_temp_agency_by_default(fixture_path: Path) -> None:
    source = FixtureSource(fixtures_path=fixture_path)
    summaries, total, _ = source.search("Entwickler", "Hamburg", exclude_temp_agency=True)
    refs = {s.referenznummer for s in summaries}
    assert "DEMO-0000000002-S" not in refs
    assert total == 1


def test_fixture_source_get_details_found(fixture_path: Path) -> None:
    source = FixtureSource(fixtures_path=fixture_path)
    details = source.get_details("DEMO-0000000001-S")
    assert details.title == "Python-Entwickler (m/w/d)"
    assert details.is_temp_agency is False


def test_fixture_source_search_falls_back_to_distance_when_location_text_differs(
    fixture_path: Path,
) -> None:
    """A listing whose stored location text doesn't match still counts if in radius."""
    source = FixtureSource(fixtures_path=fixture_path)
    summaries, total, _ = source.search("Python", "Altona", radius_km=25, exclude_temp_agency=False)
    assert total == 1
    assert summaries[0].referenznummer == "DEMO-0000000001-S"


def test_fixture_source_search_excludes_listing_outside_radius_with_different_location(
    fixture_path: Path,
) -> None:
    """A listing with a non-matching location *and* too far away is excluded."""
    source = FixtureSource(fixtures_path=fixture_path)
    summaries, total, _ = source.search("Python", "Altona", radius_km=5, exclude_temp_agency=False)
    assert total == 0
    assert summaries == []


def test_fixture_source_get_details_not_found_raises(fixture_path: Path) -> None:
    source = FixtureSource(fixtures_path=fixture_path)
    with pytest.raises(BAJobNotFoundError):
        source.get_details("DOES-NOT-EXIST-S")


# ---------------------------------------------------------------------------
# FixtureSource: recorded-search replay (D-10 Option 4)
# ---------------------------------------------------------------------------


@pytest.fixture
def fixture_path_with_recorded_searches(fixture_path: Path) -> Path:
    """Same listings as ``fixture_path``, plus a sibling ``recorded_searches.json``."""
    recorded = [
        {
            "keywords": "Softwareentwickler",
            "location": "München",
            "radius_km": 25,
            "published_within_days": 28,
            "total": 103,
            "referenznummern": ["DEMO-0000000001-S", "SOME-OTHER-REF-NOT-IN-LISTINGS-S"],
        }
    ]
    (fixture_path.parent / "recorded_searches.json").write_text(
        json.dumps(recorded), encoding="utf-8"
    )
    return fixture_path


def test_fixture_source_replays_the_recorded_total_for_an_exact_match(
    fixture_path_with_recorded_searches: Path,
) -> None:
    """D-10 Option 4: an exact-matching query reports the real recorded total (103)."""
    source = FixtureSource(fixtures_path=fixture_path_with_recorded_searches)
    summaries, total, _ = source.search(
        "Softwareentwickler", "München", radius_km=25, published_within_days=28
    )
    assert total == 103
    # Only DEMO-0000000001-S is both recorded and present in the committed listings.
    assert [s.referenznummer for s in summaries] == ["DEMO-0000000001-S"]


def test_fixture_source_replay_still_respects_exclude_temp_agency(
    fixture_path_with_recorded_searches: Path,
) -> None:
    """A recorded listing that is a temp-agency one is still filtered out by default."""
    recorded_path = fixture_path_with_recorded_searches.parent / "recorded_searches.json"
    recorded = json.loads(recorded_path.read_text(encoding="utf-8"))
    recorded[0]["referenznummern"] = ["DEMO-0000000002-S"]  # the temp-agency listing
    recorded_path.write_text(json.dumps(recorded), encoding="utf-8")

    source = FixtureSource(fixtures_path=fixture_path_with_recorded_searches)
    summaries, total, _ = source.search(
        "Softwareentwickler", "München", radius_km=25, published_within_days=28
    )
    assert total == 103  # the recorded total is unaffected by the local filter
    assert summaries == []  # but the one listing we have for it is excluded


def test_fixture_source_non_matching_query_falls_back_to_filtering(
    fixture_path_with_recorded_searches: Path,
) -> None:
    """A query that is not an exact recorded match uses the normal filter path."""
    source = FixtureSource(fixtures_path=fixture_path_with_recorded_searches)
    summaries, total, _ = source.search("Python", "Hamburg", exclude_temp_agency=False)
    assert total == 1
    assert summaries[0].referenznummer == "DEMO-0000000001-S"


def test_fixture_source_without_recorded_searches_file_falls_back(fixture_path: Path) -> None:
    """No sibling ``recorded_searches.json`` at all -> always the normal filter path."""
    source = FixtureSource(fixtures_path=fixture_path)
    summaries, total, _ = source.search(
        "Softwareentwickler", "München", radius_km=25, published_within_days=28
    )
    assert total == 0
    assert summaries == []


# ---------------------------------------------------------------------------
# FixtureSource: narrowing a recorded query (D-10 addendum, 2026-11-06)
# ---------------------------------------------------------------------------


@pytest.fixture
def narrowing_fixture_path(tmp_path: Path) -> Path:
    """A München recorded search (total 103) with one real matching listing in range.

    ``MUC-JAVA-SENIOR-S`` is both within the recorded query's own reference
    numbers and the committed listing set - its title matches "Java" and
    "Senior" so a narrower, on-topic query should find it.
    ``MUC-OTHER-S`` is in the committed listings but was never part of the
    recorded München search - a narrowing query must not pick it up.
    """
    listings = [
        {
            "referenznummer": "MUC-JAVA-SENIOR-S",
            "title": "Senior Java Softwareentwickler (m/w/d)",
            "employer": "Beispiel AG München",
            "location": "München",
            "distance_km": 5.0,
            "published_date": "2026-11-01",
            "remote_type": None,
            "remote_percent": None,
            "salary_min": None,
            "salary_max": None,
            "full_time": True,
            "contract_duration": "UNBEFRISTET",
            "external_url": False,
            "description": "Infrastruktur als Code mit Terraform gehoert zu deinen Aufgaben. "
            + "x" * 900,
            "is_temp_agency": False,
            "is_private_recruiter": False,
            "contract_months": None,
            "low_evidence": False,
        },
        {
            "referenznummer": "MUC-OTHER-S",
            "title": "Senior Java Softwareentwickler, nicht Teil der aufgezeichneten Suche",
            "employer": "Andere Firma",
            "location": "München",
            "distance_km": 5.0,
            "published_date": "2026-11-01",
            "remote_type": None,
            "remote_percent": None,
            "salary_min": None,
            "salary_max": None,
            "full_time": True,
            "contract_duration": "UNBEFRISTET",
            "external_url": False,
            "description": "x" * 1000,
            "is_temp_agency": False,
            "is_private_recruiter": False,
            "contract_months": None,
            "low_evidence": False,
        },
    ]
    recorded = [
        {
            "keywords": "Softwareentwickler",
            "location": "München",
            "radius_km": 25,
            "published_within_days": 28,
            "total": 103,
            "referenznummern": ["MUC-JAVA-SENIOR-S"],
        }
    ]
    listings_path = tmp_path / "listings.json"
    listings_path.write_text(json.dumps(listings), encoding="utf-8")
    (tmp_path / "recorded_searches.json").write_text(json.dumps(recorded), encoding="utf-8")
    return listings_path


def test_fixture_source_narrowing_query_finds_the_recorded_listing(
    narrowing_fixture_path: Path,
) -> None:
    """D-10 addendum: recorded keywords + more terms, same location, smaller radius."""
    source = FixtureSource(fixtures_path=narrowing_fixture_path)
    summaries, total, notes = source.search(
        "Java Senior Softwareentwickler", "München", radius_km=10, published_within_days=14
    )
    assert total == 1
    assert [s.referenznummer for s in summaries] == ["MUC-JAVA-SENIOR-S"]
    assert any("narrowed from" in note for note in notes)


def test_fixture_source_narrowing_query_excludes_listings_outside_the_recorded_search(
    narrowing_fixture_path: Path,
) -> None:
    """MUC-OTHER-S matches the keywords but was never part of the recorded search."""
    source = FixtureSource(fixtures_path=narrowing_fixture_path)
    summaries, total, _ = source.search(
        "Java Senior Softwareentwickler", "München", radius_km=25, published_within_days=28
    )
    assert total == 1
    assert [s.referenznummer for s in summaries] == ["MUC-JAVA-SENIOR-S"]


def test_fixture_source_narrowing_is_honest_about_zero_results(
    narrowing_fixture_path: Path,
) -> None:
    """A narrowing query whose extra term the one recorded listing doesn't match: total 0."""
    source = FixtureSource(fixtures_path=narrowing_fixture_path)
    summaries, total, _ = source.search(
        "Softwareentwickler Kubernetes", "München", radius_km=25, published_within_days=28
    )
    assert total == 0
    assert summaries == []


def test_fixture_source_wider_radius_does_not_count_as_narrowing(
    narrowing_fixture_path: Path,
) -> None:
    """A *wider* radius than the recorded query is not a narrowing - falls back to generic."""
    source = FixtureSource(fixtures_path=narrowing_fixture_path)
    summaries, total, notes = source.search(
        "Java Senior Softwareentwickler", "München", radius_km=50, published_within_days=28
    )
    # Falls through to the generic path over the whole committed set, so both
    # München listings (both keyword-matching) are found, not just the recorded one.
    assert total == 2
    assert not any("narrowed from" in note for note in notes)


def test_fixture_source_narrowing_matches_a_term_only_present_in_the_description(
    narrowing_fixture_path: Path,
) -> None:
    """D-10 follow-up 2: narrowing checks description text, not just title/employer.

    ``MUC-JAVA-SENIOR-S``'s description mentions "Terraform" nowhere in its
    title, only in its description (``narrowing_fixture_path``).
    """
    source = FixtureSource(fixtures_path=narrowing_fixture_path)
    summaries, total, notes = source.search(
        "Java Senior Softwareentwickler Terraform",
        "München",
        radius_km=10,
        published_within_days=14,
    )
    assert total == 1
    assert [s.referenznummer for s in summaries] == ["MUC-JAVA-SENIOR-S"]
    assert any("narrowed from" in note for note in notes)


def test_fixture_source_dropping_a_recorded_keyword_does_not_count_as_narrowing(
    narrowing_fixture_path: Path,
) -> None:
    """Replacing the recorded keyword entirely falls back to the generic path, not narrowing.

    "Entwickler" is a substring of "Softwareentwickler" (the generic filter
    matches substrings, not whole words), so the generic path still finds
    both München listings here - the point of this test is the *absence*
    of the "narrowed from" note, i.e. this did not take the
    recorded-query-restricted path, not the resulting count.
    """
    source = FixtureSource(fixtures_path=narrowing_fixture_path)
    summaries, total, notes = source.search(
        "Java Senior Entwickler", "München", radius_km=25, published_within_days=28
    )
    assert not any("narrowed from" in note for note in notes)
    assert total == 2
    assert {s.referenznummer for s in summaries} == {"MUC-JAVA-SENIOR-S", "MUC-OTHER-S"}
