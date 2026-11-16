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
    first_ref = fit_set[0]["referenznummer"]

    at.selectbox(key="category").set_value("partial")
    for dim in label_fit.DIMENSIONS:
        at.selectbox(key=f"{dim}_verdict").set_value("met")
    at.form_submit_button[0].click().run()

    assert not at.exception
    assert label_fit.load_labelled_refs(labels_path) == {first_ref}
    assert f"1 of {len(fit_set)} listings labelled." in "\n".join(c.value for c in at.caption)


def test_all_labelled_shows_a_done_message(labels_path: Path) -> None:
    fit_set = label_fit.load_fit_set(label_fit.FIT_SET_PATH)
    verdicts = dict.fromkeys(label_fit.DIMENSIONS, "met")
    for row in fit_set:
        label_fit.append_label_row(
            labels_path, label_fit.build_label_row(row["referenznummer"], "strong", verdicts, {})
        )

    at = AppTest.from_file(str(SCRIPT_PATH), default_timeout=30)
    at.run()

    assert not at.exception
    assert any("All listings are labelled" in s.value for s in at.success)
