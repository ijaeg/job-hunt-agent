"""Profile page: edit, save and demo-load the selected user's profile (FR-14).

Layout only (NFR-04): no business logic. ``storage.py`` persists the
profile row; validation is the :class:`job_hunt_agent.models.Profile`
model itself (FR-14 AC1) - an invalid value (e.g. a radius outside 5-200
km) is caught here as a friendly message, never a stack trace (invariant
7, CLAUDE.md). "Load demo profile" stores ``data/samples/profile_alex.yaml``
for whichever user is selected, not only for ``ui_shared.DEFAULT_USER_ID``
(FR-14 AC2).

Related: FR-14 AC1-AC3, D-16, spec §11
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import streamlit as st
from pydantic import ValidationError

# See app.py's matching comment: this page can run in ways that skip
# Streamlit's "insert the entry script's own directory into sys.path"
# trick - most notably a test driving it directly via
# ``AppTest.from_file(this_path)`` - so it adds the repo root itself
# before importing the sibling ``ui_shared`` module.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from job_hunt_agent import config, storage  # noqa: E402
from job_hunt_agent.models import Profile  # noqa: E402
from ui_shared import get_connection, load_demo_profile_data, render_user_sidebar  # noqa: E402

st.set_page_config(page_title="Profile - Job Hunt Agent", layout="wide")

_SENIORITY_LEVELS: list[str] = ["junior", "mid", "senior", "lead"]
_LANGUAGE_LEVELS: list[str] = ["none", "basic", "fluent", "native"]
_REMOTE_PREFERENCES: list[str] = ["onsite", "hybrid", "remote"]


def _build_profile_from_form(
    skills_text: str,
    seniority: str,
    location: str,
    radius_km: int,
    remote_preference: str,
    wants_full_time: bool,
    wants_permanent: bool,
    exclude_temp_agency: bool,
    german_level: str,
    english_level: str,
) -> Profile:
    """Raises :class:`pydantic.ValidationError` on any out-of-range or malformed field."""
    return Profile(
        skills=[s.strip() for s in skills_text.split(",") if s.strip()],
        seniority=seniority,  # type: ignore[arg-type]
        location=location,
        radius_km=radius_km,
        remote_preference=remote_preference,  # type: ignore[arg-type]
        wants_full_time=wants_full_time,
        wants_permanent=wants_permanent,
        exclude_temp_agency=exclude_temp_agency,
        german_level=german_level,  # type: ignore[arg-type]
        english_level=english_level,  # type: ignore[arg-type]
    )


def render_form(conn: Any, user_id: str, profile: Profile | None) -> None:
    """Renders the profile form, pre-filled with ``profile`` if one is stored (FR-14 AC1)."""
    with st.form("profile_form"):
        skills_text = st.text_input(
            "Skills (comma-separated)",
            value=", ".join(profile.skills) if profile else "",
        )
        seniority = st.selectbox(
            "Seniority",
            _SENIORITY_LEVELS,
            index=_SENIORITY_LEVELS.index(profile.seniority) if profile else 1,
        )
        location = st.text_input("Location", value=profile.location if profile else "")
        # No min_value/max_value here on purpose: the 5-200 km range is a
        # Profile field constraint (FR-14 AC1), validated below after
        # submit, so an out-of-range value shows this page's own friendly
        # message instead of being silently clamped by the widget.
        radius_km = st.number_input(
            "Search radius (km)", value=profile.radius_km if profile else 25, step=5
        )
        remote_preference = st.selectbox(
            "Remote preference",
            _REMOTE_PREFERENCES,
            index=_REMOTE_PREFERENCES.index(profile.remote_preference) if profile else 1,
        )
        wants_full_time = st.checkbox(
            "Wants full-time", value=profile.wants_full_time if profile else True
        )
        wants_permanent = st.checkbox(
            "Wants a permanent contract", value=profile.wants_permanent if profile else True
        )
        exclude_temp_agency = st.checkbox(
            "Exclude temporary agency work", value=profile.exclude_temp_agency if profile else True
        )
        german_level = st.selectbox(
            "German level",
            _LANGUAGE_LEVELS,
            index=_LANGUAGE_LEVELS.index(profile.german_level) if profile else 1,
        )
        english_level = st.selectbox(
            "English level",
            _LANGUAGE_LEVELS,
            index=_LANGUAGE_LEVELS.index(profile.english_level) if profile else 2,
        )
        submitted = st.form_submit_button("Save")

    if not submitted:
        return

    try:
        new_profile = _build_profile_from_form(
            skills_text,
            seniority,
            location,
            int(radius_km),
            remote_preference,
            wants_full_time,
            wants_permanent,
            exclude_temp_agency,
            german_level,
            english_level,
        )
    except ValidationError as exc:
        messages = "; ".join(err["msg"] for err in exc.errors())
        st.error(f"Could not save the profile: {messages}")
        return

    try:
        storage.save_profile(conn, user_id, new_profile)
    except Exception:  # noqa: BLE001 - invariant 7: never a stack trace in the UI
        st.error("Could not save the profile. Please try again.")
        return

    st.success("Profile saved.")
    st.rerun()


def main() -> None:
    st.title("Profile")

    conn = get_connection(os.getenv("DB_PATH", config.DB_PATH))
    user_id = render_user_sidebar(conn)

    if st.button("Load demo profile"):
        try:
            demo_profile = Profile.model_validate(load_demo_profile_data())
            storage.save_profile(conn, user_id, demo_profile)
        except Exception:  # noqa: BLE001 - invariant 7: never a stack trace in the UI
            st.error("Could not load the demo profile. Please try again.")
        else:
            st.success("Demo profile loaded.")
            st.rerun()

    try:
        profile = storage.load_profile(conn, user_id)
    except Exception:  # noqa: BLE001 - invariant 7: never a stack trace in the UI
        st.error("Could not load the profile. Please try again.")
        return

    render_form(conn, user_id, profile)

    st.caption(
        "The fit assessment uses this profile immediately on your next search in an open "
        "thread; the agent itself only sees it in full from the next new search thread."
    )


if __name__ == "__main__":
    main()
