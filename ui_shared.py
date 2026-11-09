"""Streamlit UI resources shared by app.py and pages/ (spec §11, D-16).

The cached SQLite connection, the selected user id and profile loading are
needed by every page alike; this module is the one place that reads and
sets the selected user (D-16), imported by all of them rather than one
page importing from another (CLAUDE.md "Architecture and dependency
direction": UI -> package, never the reverse - no page imports app.py).

Related: FR-11 AC1, FR-13 AC2, FR-14 AC1, D-5, D-16
"""

from __future__ import annotations

import uuid
from typing import Any

import streamlit as st
import yaml

from job_hunt_agent import config, storage
from job_hunt_agent.models import Profile
from job_hunt_agent.user_view import order_users, slugify_user_id, validate_user_name

#: No authentication (spec §2.2, D-16): this is the user selected on first
#: start, before anyone has picked a different one, and the only user id
#: ever auto-seeded with the demo profile (FR-14 AC2's one-click load is
#: how every *other* user gets a profile).
DEFAULT_USER_ID = "alex"

_PROFILE_SEED_PATH = config.PROJECT_ROOT / "data" / "samples" / "profile_alex.yaml"


@st.cache_resource
def get_connection(db_path: str) -> Any:
    """One shared SQLite connection for the checkpointer, store, tracker and profile (D-5)."""
    return storage.get_connection(db_path)


def load_demo_profile_data() -> dict[str, Any]:
    """Reads the demo profile YAML (FR-14 AC2), shared by app.py's first-start seeding and
    the profile page's "Load demo profile" button."""
    data = yaml.safe_load(_PROFILE_SEED_PATH.read_text(encoding="utf-8"))
    return data  # type: ignore[no-any-return]


def load_profile_or_none(conn: Any, user_id: str) -> Profile | None:
    """Loads the stored profile, or ``None`` if the user has none yet (FR-14 AC1).

    Only :data:`DEFAULT_USER_ID` is seeded silently (preserving the
    existing demo behaviour); every other user without a profile gets
    ``None`` so the caller can show the hint to the profile page instead
    of seeding anything (WP-08 goal 2).
    """
    profile = storage.load_profile(conn, user_id)
    if profile is not None:
        return profile
    if user_id != DEFAULT_USER_ID:
        return None
    profile = Profile.model_validate(load_demo_profile_data())
    storage.save_profile(conn, user_id, profile)
    return profile


def get_selected_user_id() -> str:
    """Reads the selected user id, defaulting to :data:`DEFAULT_USER_ID` (D-16).

    Kept in ``st.query_params`` (not ``st.session_state``), the same
    mechanism ``app.py``'s own thread id already relies on (FR-16 AC3):
    session state does not survive a browser reload, but the URL does, and
    both are shared across a Streamlit multipage app's pages already.
    """
    user_id = st.query_params.get("user")
    if not user_id:
        user_id = DEFAULT_USER_ID
        st.query_params["user"] = user_id
    return user_id


def select_user(user_id: str) -> None:
    """Switches the selected user and opens a new empty thread for them (D-16)."""
    st.query_params["user"] = user_id
    st.query_params["thread_id"] = str(uuid.uuid4())


def render_user_sidebar(conn: Any) -> str:
    """Renders the sidebar's user picker; returns the selected user id for this run.

    Every page (main, tracker, memory, profile) calls this first, so the
    selected user is read from and changed in one place (CLAUDE.md
    "Architecture and dependency direction"). Picking a different existing
    user, or adding a new one, calls :func:`select_user` immediately, so
    the rest of *this* run (not just the next rerun) already uses the new
    selection - the pattern ``app.py``'s "New search" button also relies
    on for its own query param.

    Related: FR-13 AC2, FR-14, D-16
    """
    # A widget's own session_state entry (keyed by "user_select") cannot be
    # written once that widget has been instantiated in the *same* run - it
    # would otherwise win over a freshly computed `index` below, since it
    # remembers the user's last click, not query params. Adding a new user
    # therefore defers the sync to here, the top of the *next* run, before
    # the selectbox below is created.
    if "_pending_user_select" in st.session_state:
        st.session_state["user_select"] = st.session_state.pop("_pending_user_select")

    current = get_selected_user_id()
    existing = storage.list_users(conn)
    options = order_users(list({current, *existing}))

    with st.sidebar:
        st.caption("User")
        selected = st.selectbox(
            "Select user",
            options,
            index=options.index(current),
            label_visibility="collapsed",
            key="user_select",
        )
        if selected != current:
            select_user(selected)
            current = selected

        with st.expander("Add new user"):
            new_name = st.text_input("Name", key="new_user_name")
            if st.button("Add user", key="add_user_button"):
                error = validate_user_name(new_name)
                if error:
                    st.error(error)
                else:
                    new_id = slugify_user_id(new_name)
                    select_user(new_id)
                    st.session_state["_pending_user_select"] = new_id
                    st.rerun()

    return current
