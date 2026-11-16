"""Labelling tool for the fit evaluation set (spec §7, §9.3, D-20, WP-13).

A small Streamlit app, run on its own (**not** part of the product app, not
under ``pages/``): ``uv run streamlit run scripts/label_fit.py``. Shows one
listing of ``eval/fit_set.yaml`` at a time - its cleaned ad text, the
structured fields the rubric (spec §7) actually uses, the Alex demo profile,
and a plain-words summary of the rubric itself - and asks for an overall
category and one verdict per rubric dimension, each with an optional note.
Saves to ``eval/fit_labels.csv`` after every listing (one row per
``referenznummer``), so labelling can stop and resume at any time.

**Blind by design (D-20):** this tool does not import the product's rubric
module at all, so it has nothing to compute or show the app's own category
or verdicts with - Ingo's label must not be influenced by the app's own
answer. It also never shows a listing's ``eval/fit_set.yaml`` stratum,
since that would leak the hard-exclusion/skill-match heuristic the
selection script used.

Usage (from the project root):
    uv run streamlit run scripts/label_fit.py

Reads:
    eval/fit_set.yaml, data/samples/fixtures/listings.json,
    data/samples/profile_alex.yaml

Writes:
    eval/fit_labels.csv

Related: spec §7, §9.1, §9.3, invariant 6, D-9, D-20, WP-13
"""

from __future__ import annotations

import csv
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import streamlit as st
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIT_SET_PATH = PROJECT_ROOT / "eval" / "fit_set.yaml"
LISTINGS_PATH = PROJECT_ROOT / "data" / "samples" / "fixtures" / "listings.json"
PROFILE_PATH = PROJECT_ROOT / "data" / "samples" / "profile_alex.yaml"
#: Overridable by tests (``FIT_LABELS_PATH`` env var) so an AppTest run never
#: writes into the real ``eval/fit_labels.csv`` - same convention as the
#: product pages' ``DB_PATH``.
LABELS_PATH = Path(os.getenv("FIT_LABELS_PATH", str(PROJECT_ROOT / "eval" / "fit_labels.csv")))

#: Rubric dimensions in spec §7's order; keys match ``FitAssessment.rubric``
#: (``job_hunt_agent.rubric.DIMENSION_WEIGHTS``) so a later agreement check
#: can line a label up with the app's own verdict dimension-for-dimension.
DIMENSIONS: tuple[str, ...] = (
    "skills",
    "location_remote",
    "seniority",
    "language",
    "employment_type",
)

DIMENSION_LABELS: dict[str, str] = {
    "skills": "Skills",
    "location_remote": "Location / remote",
    "seniority": "Seniority",
    "language": "Language (German level)",
    "employment_type": "Employment type",
}

_PLACEHOLDER = "— select —"
CATEGORY_OPTIONS: tuple[str, ...] = (_PLACEHOLDER, "strong", "partial", "poor", "excluded")
VERDICT_OPTIONS: tuple[str, ...] = (_PLACEHOLDER, "met", "partly", "not_met", "unknown")

#: CSV column order; a verdict/note pair per dimension (spec §7, D-20).
FIELDNAMES: tuple[str, ...] = (
    "referenznummer",
    "category",
    *(f"{dim}_verdict" for dim in DIMENSIONS),
    *(f"{dim}_note" for dim in DIMENSIONS),
    "timestamp",
)


def load_fit_set(path: Path) -> list[dict[str, Any]]:
    """Returns the ``listings`` entries of ``eval/fit_set.yaml``, in file order."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    listings: list[dict[str, Any]] = doc["listings"]
    return listings


def load_listings_by_ref(path: Path) -> dict[str, dict[str, Any]]:
    """Indexes the fixture listing file by ``referenznummer`` for lookup by the fit set."""
    listings: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return {listing["referenznummer"]: listing for listing in listings}


def load_labelled_refs(csv_path: Path) -> set[str]:
    """Reference numbers already labelled, so the tool resumes after the last one saved."""
    if not csv_path.exists():
        return set()
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        return {row["referenznummer"] for row in csv.DictReader(handle)}


def build_label_row(
    referenznummer: str, category: str, verdicts: dict[str, str], notes: dict[str, str]
) -> dict[str, str]:
    """Assembles one CSV row; ``verdicts``/``notes`` are keyed by dimension name."""
    row = {"referenznummer": referenznummer, "category": category}
    for dim in DIMENSIONS:
        row[f"{dim}_verdict"] = verdicts[dim]
        row[f"{dim}_note"] = notes.get(dim, "")
    row["timestamp"] = datetime.now(UTC).isoformat()
    return row


def append_label_row(csv_path: Path, row: dict[str, str]) -> None:
    """Appends ``row`` to ``csv_path``, writing the header first if the file is new."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not csv_path.exists()
    with csv_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        if is_new:
            writer.writeheader()
        writer.writerow(row)


def _render_structured_fields(listing: dict[str, Any]) -> None:
    st.markdown("**Structured fields**")
    st.table(
        {
            "distance_km": [listing.get("distance_km")],
            "remote_type": [listing.get("remote_type")],
            "remote_percent": [listing.get("remote_percent")],
            "full_time": [listing.get("full_time")],
            "contract_duration": [listing.get("contract_duration")],
            "contract_months": [listing.get("contract_months")],
            "is_temp_agency": [listing.get("is_temp_agency")],
        }
    )


def _render_profile(profile: dict[str, Any]) -> None:
    st.markdown("**Alex profile**")
    st.json(profile)


def _render_rubric_summary() -> None:
    with st.expander("Rubric rules (spec §7), in plain words - see docs/labelling_guide.md"):
        st.markdown(
            "- Hard exclusions decide **excluded** before anything else: "
            "temporary-agency work the profile excludes, or outside the "
            "radius and not fully remote (FR-06).\n"
            "- **Skills**: met = most of the ad's skills are in the profile; "
            "partly = some overlap; not met = little/none; unknown = no "
            "concrete skills named.\n"
            "- **Location/remote**: met = within radius and remote "
            "preference satisfied, or fully remote; partly = within radius, "
            "remote not stated; not met = outside radius, not fully remote; "
            "unknown = can't tell.\n"
            "- **Seniority**: met = same level; partly = one level apart; "
            "not met = two+ apart; unknown = not mentioned.\n"
            "- **Language**: met = requirement at/below the profile's German "
            "level; partly = one level above; not met = two+ above; "
            "unknown = not mentioned.\n"
            "- **Employment type**: met = full-time/contract-length match; "
            "not met = a stated value conflicts; unknown = neither stated."
        )


def render_listing_form(listing: dict[str, Any], profile: dict[str, Any]) -> None:
    """Renders one listing and its labelling form; never shows the app's own assessment."""
    st.subheader(f"{listing['title']} — {listing.get('employer') or 'unknown employer'}")
    st.caption(f"Reference: {listing['referenznummer']}")

    st.markdown("**Ad text**")
    st.markdown(listing["description"])

    _render_structured_fields(listing)
    _render_profile(profile)
    _render_rubric_summary()

    with st.form("label_form"):
        category = st.selectbox("Overall category", CATEGORY_OPTIONS, key="category")
        verdicts: dict[str, str] = {}
        notes: dict[str, str] = {}
        for dim in DIMENSIONS:
            label = DIMENSION_LABELS[dim]
            verdicts[dim] = st.selectbox(f"{label} verdict", VERDICT_OPTIONS, key=f"{dim}_verdict")
            notes[dim] = st.text_input(f"{label} note (optional)", key=f"{dim}_note")
        submitted = st.form_submit_button("Save and next")

    if not submitted:
        return

    missing = [label for label, value in [("category", category)] if value == _PLACEHOLDER]
    missing += [DIMENSION_LABELS[dim] for dim in DIMENSIONS if verdicts[dim] == _PLACEHOLDER]
    if missing:
        st.error(f"Please select a value for: {', '.join(missing)}.")
        return

    row = build_label_row(listing["referenznummer"], category, verdicts, notes)
    append_label_row(LABELS_PATH, row)
    st.rerun()


def main() -> None:
    st.set_page_config(page_title="Fit labelling - WP-13", layout="wide")
    st.title("Fit labelling (WP-13)")
    st.caption(
        "Label each listing against the §7 rubric and the Alex profile. "
        "You never see the app's own assessment here (D-20)."
    )

    fit_set = load_fit_set(FIT_SET_PATH)
    listings_by_ref = load_listings_by_ref(LISTINGS_PATH)
    profile = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    labelled = load_labelled_refs(LABELS_PATH)

    pending = [row for row in fit_set if row["referenznummer"] not in labelled]
    st.caption(f"{len(fit_set) - len(pending)} of {len(fit_set)} listings labelled.")

    if not pending:
        st.success("All listings are labelled. See eval/fit_labels.csv.")
        return

    current = pending[0]
    listing = listings_by_ref.get(current["referenznummer"])
    if listing is None:
        st.error(f"Reference {current['referenznummer']} is not in the fixture set.")
        return

    render_listing_form(listing, profile)


if __name__ == "__main__":
    main()
