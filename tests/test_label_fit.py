"""Tests for scripts/label_fit.py (spec §7, §9.1, §9.3, D-20, WP-13).

Pure-helper unit tests for the set-loading and CSV read/write functions,
plus an AppTest integration test that the tool renders a listing and saves
a row without ever showing the app's own fit assessment (D-20) - mirrors
``tests/test_pages_tracker.py``'s AppTest pattern. No network call, no API
key needed (CLAUDE.md invariant 5, NFR-05): this script never touches the
agent, the model or ``job_hunt_agent.rubric`` at all.

Related: spec §7, §9.1, §9.3, invariant 6, D-9, D-20, WP-13
"""

from __future__ import annotations

import csv
import importlib.util
import sys
import uuid
from pathlib import Path
from types import ModuleType

import pytest
from streamlit.testing.v1 import AppTest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "label_fit.py"


def _load_label_fit_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("label_fit_under_test", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


label_fit = _load_label_fit_module()


# ---------------------------------------------------------------------------
# D-20: the tool has no access to the app's own rubric at all
# ---------------------------------------------------------------------------


def test_label_fit_never_imports_the_products_rubric_module() -> None:
    assert not hasattr(label_fit, "rubric")
    assert not hasattr(label_fit, "assess")
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "import rubric" not in source
    assert "from job_hunt_agent.rubric" not in source
    assert "from job_hunt_agent import rubric" not in source


# ---------------------------------------------------------------------------
# load_fit_set: reads eval/fit_set.yaml (the real, committed one)
# ---------------------------------------------------------------------------


def test_load_fit_set_returns_all_twenty_listings_in_file_order() -> None:
    listings = label_fit.load_fit_set(label_fit.FIT_SET_PATH)

    assert len(listings) == 20
    assert all("referenznummer" in row and "set" in row for row in listings)
    refs = [row["referenznummer"] for row in listings]
    assert len(refs) == len(set(refs))


# ---------------------------------------------------------------------------
# load_listings_by_ref: indexes the committed fixture file
# ---------------------------------------------------------------------------


def test_load_listings_by_ref_indexes_every_fit_set_reference() -> None:
    fit_set = label_fit.load_fit_set(label_fit.FIT_SET_PATH)
    listings_by_ref = label_fit.load_listings_by_ref(label_fit.LISTINGS_PATH)

    for row in fit_set:
        ref = row["referenznummer"]
        assert ref in listings_by_ref
        assert listings_by_ref[ref]["referenznummer"] == ref


# ---------------------------------------------------------------------------
# resolve_search_location: which search a listing's distance_km is relative to
# (Addendum 2: FR-01 AC4 - a search location can differ from the profile's own)
# ---------------------------------------------------------------------------


def test_resolve_search_location_single_match() -> None:
    recorded_searches = label_fit.load_recorded_searches(label_fit.RECORDED_SEARCHES_PATH)

    # 11119-4964515256-S matched only the München "Softwareentwickler" query.
    location = label_fit.resolve_search_location("11119-4964515256-S", recorded_searches)

    assert location == 'München (radius 25 km, query "Softwareentwickler")'


def test_resolve_search_location_picks_the_same_query_build_fixtures_used_for_distance() -> None:
    """19913-3074751792188001-S matches both the Hamburg "AI Engineer" (entfernung 4)
    and Berlin "Machine Learning" (entfernung 3) searches; listings.json's own
    distance_km is 3.0 (confirmed against the raw D-1 responses), i.e. Berlin won -
    this must resolve to the same query, not an arbitrary one of the two.
    """
    recorded_searches = label_fit.load_recorded_searches(label_fit.RECORDED_SEARCHES_PATH)
    listings_by_ref = label_fit.load_listings_by_ref(label_fit.LISTINGS_PATH)
    ref = "19913-3074751792188001-S"

    assert listings_by_ref[ref]["distance_km"] == 3.0
    location = label_fit.resolve_search_location(ref, recorded_searches)
    assert location == 'Berlin (radius 25 km, query "Machine Learning")'


def test_resolve_search_location_returns_none_for_an_unknown_reference() -> None:
    recorded_searches = label_fit.load_recorded_searches(label_fit.RECORDED_SEARCHES_PATH)

    assert label_fit.resolve_search_location("NOT-A-REAL-REF-S", recorded_searches) is None


# ---------------------------------------------------------------------------
# load_labelled_refs: resumable read, empty when the file doesn't exist yet
# ---------------------------------------------------------------------------


def test_load_labelled_refs_is_empty_when_the_csv_does_not_exist(tmp_path: Path) -> None:
    assert label_fit.load_labelled_refs(tmp_path / "does-not-exist.csv") == set()


def test_load_labelled_refs_reads_back_appended_rows(tmp_path: Path) -> None:
    csv_path = tmp_path / "fit_labels.csv"
    row_a = label_fit.build_label_row(
        "AAA-S", "strong", dict.fromkeys(label_fit.DIMENSIONS, "met"), {}
    )
    row_b = label_fit.build_label_row(
        "BBB-S", "poor", dict.fromkeys(label_fit.DIMENSIONS, "not_met"), {}
    )
    label_fit.append_label_row(csv_path, row_a)
    label_fit.append_label_row(csv_path, row_b)

    assert label_fit.load_labelled_refs(csv_path) == {"AAA-S", "BBB-S"}


# ---------------------------------------------------------------------------
# append_label_row: writes the header once, then appends - resumable by design
# ---------------------------------------------------------------------------


def test_append_label_row_writes_header_once_and_appends_rows(tmp_path: Path) -> None:
    csv_path = tmp_path / "nested" / "fit_labels.csv"
    verdicts = dict.fromkeys(label_fit.DIMENSIONS, "met")
    notes = {"skills": "matches Python and FastAPI"}

    row = label_fit.build_label_row("10001-S", "strong", verdicts, notes)
    label_fit.append_label_row(csv_path, row)
    label_fit.append_label_row(
        csv_path, label_fit.build_label_row("10002-S", "poor", verdicts, notes)
    )

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == list(label_fit.FIELDNAMES)
        rows = list(reader)

    assert [r["referenznummer"] for r in rows] == ["10001-S", "10002-S"]
    assert rows[0]["category"] == "strong"
    assert rows[0]["skills_verdict"] == "met"
    assert rows[0]["skills_note"] == "matches Python and FastAPI"
    assert rows[0]["timestamp"]


def test_build_label_row_covers_every_dimension() -> None:
    verdicts = {
        "skills": "met",
        "location_remote": "partly",
        "seniority": "not_met",
        "language": "unknown",
        "employment_type": "met",
    }
    row = label_fit.build_label_row("REF-S", "partial", verdicts, {"seniority": "two apart"})

    for dim, verdict in verdicts.items():
        assert row[f"{dim}_verdict"] == verdict
    assert row["seniority_note"] == "two apart"
    assert row["location_remote_note"] == ""


# ---------------------------------------------------------------------------
# AppTest: renders a listing, never shows an assessment, saves on submit
# ---------------------------------------------------------------------------


@pytest.fixture
def labels_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / f"fit_labels_{uuid.uuid4().hex}.csv"
    monkeypatch.setenv("FIT_LABELS_PATH", str(path))
    return path


def test_renders_the_first_pending_listing_without_an_assessment(labels_path: Path) -> None:
    at = AppTest.from_file(str(SCRIPT_PATH), default_timeout=30)
    at.run()

    assert not at.exception
    fit_set = label_fit.load_fit_set(label_fit.FIT_SET_PATH)
    listings_by_ref = label_fit.load_listings_by_ref(label_fit.LISTINGS_PATH)
    first = listings_by_ref[fit_set[0]["referenznummer"]]

    rendered = "\n".join(el.value for el in [*at.markdown, *at.caption, *at.subheader])
    assert first["title"] in rendered
    assert first["referenznummer"] in rendered
    # D-20: the stratum (the selection heuristic) must never leak onto the page.
    assert fit_set[0]["stratum"] not in rendered

    category_box = next(sb for sb in at.selectbox if sb.label == "Overall category")
    assert category_box.value == "— select —"

    # Addendum 2: distance is shown next to the search location it is
    # relative to, not silently assumed to be the Alex profile's Hamburg.
    distance_cell = str(at.table[0].value["distance"].iloc[0])
    assert "km from" in distance_cell
    assert "München" in distance_cell or "Hamburg" in distance_cell or "Berlin" in distance_cell


def test_location_remote_has_no_unknown_option_and_employment_type_has_no_partly(
    labels_path: Path,
) -> None:
    at = AppTest.from_file(str(SCRIPT_PATH), default_timeout=30)
    at.run()

    location_remote_box = at.selectbox(key="location_remote_verdict")
    employment_type_box = at.selectbox(key="employment_type_verdict")

    assert "unknown" not in location_remote_box.options
    assert set(location_remote_box.options) == {"— select —", "met", "partly", "not_met"}
    assert "partly" not in employment_type_box.options
    assert set(employment_type_box.options) == {"— select —", "met", "not_met", "unknown"}

    # The other three dimensions keep all four verdicts.
    for dim in ("skills", "seniority", "language"):
        options = set(at.selectbox(key=f"{dim}_verdict").options)
        assert options == {"— select —", "met", "partly", "not_met", "unknown"}


def test_submitting_without_a_choice_shows_a_friendly_error_and_saves_nothing(
    labels_path: Path,
) -> None:
    at = AppTest.from_file(str(SCRIPT_PATH), default_timeout=30)
    at.run()

    at.form_submit_button[0].click().run()

    assert not at.exception
    assert any("Please select a value" in str(e.value) for e in at.error)
    assert not labels_path.exists()


def test_submitting_a_full_label_saves_a_row_and_advances(labels_path: Path) -> None:
    at = AppTest.from_file(str(SCRIPT_PATH), default_timeout=30)
    at.run()

    fit_set = label_fit.load_fit_set(label_fit.FIT_SET_PATH)
    combined = fit_set + label_fit.load_fit_set(label_fit.FIT_SET_ROUND2_PATH)
    first_ref = fit_set[0]["referenznummer"]

    at.selectbox(key="category").set_value("partial")
    for dim in label_fit.DIMENSIONS:
        at.selectbox(key=f"{dim}_verdict").set_value("met")
    at.form_submit_button[0].click().run()

    assert not at.exception
    assert label_fit.load_labelled_refs(labels_path) == {first_ref}
    assert f"1 of {len(combined)} listings labelled." in "\n".join(c.value for c in at.caption)


def test_all_labelled_shows_a_done_message(labels_path: Path) -> None:
    combined = label_fit.load_fit_set(label_fit.FIT_SET_PATH) + label_fit.load_fit_set(
        label_fit.FIT_SET_ROUND2_PATH
    )
    verdicts = dict.fromkeys(label_fit.DIMENSIONS, "met")
    for row in combined:
        label_fit.append_label_row(
            labels_path, label_fit.build_label_row(row["referenznummer"], "strong", verdicts, {})
        )

    at = AppTest.from_file(str(SCRIPT_PATH), default_timeout=30)
    at.run()

    assert not at.exception
    assert any("All listings are labelled" in s.value for s in at.success)


def test_continues_into_round2_set_once_fit_set_is_fully_labelled(labels_path: Path) -> None:
    """WP-14b/D-26: once the 20 ``fit_set.yaml`` listings are labelled, the tool
    moves on to ``fit_set_round2.yaml``'s 10 - same tool, same columns, no
    assessment and no stratum shown for these either."""
    fit_set = label_fit.load_fit_set(label_fit.FIT_SET_PATH)
    round2 = label_fit.load_fit_set(label_fit.FIT_SET_ROUND2_PATH)
    verdicts = dict.fromkeys(label_fit.DIMENSIONS, "met")
    for row in fit_set:
        label_fit.append_label_row(
            labels_path, label_fit.build_label_row(row["referenznummer"], "strong", verdicts, {})
        )

    at = AppTest.from_file(str(SCRIPT_PATH), default_timeout=30)
    at.run()

    assert not at.exception
    assert not at.success  # not done yet - 10 round-2 listings still pending

    first_round2 = round2[0]
    rendered = "\n".join(el.value for el in [*at.markdown, *at.caption, *at.subheader])
    assert first_round2["title"] in rendered
    assert first_round2["referenznummer"] in rendered
    assert first_round2["stratum"] not in rendered
    assert f"{len(fit_set)} of {len(fit_set) + len(round2)} listings labelled." in "\n".join(
        c.value for c in at.caption
    )
