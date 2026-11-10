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

from job_hunt_agent import ba_client, config, storage
from job_hunt_agent.models import Profile
from job_hunt_agent.user_view import order_users, slugify_user_id, validate_user_name

#: No authentication (spec §2.2, D-16): this is the user selected on first
#: start, before anyone has picked a different one, and the only user id
#: ever auto-seeded with the demo profile (FR-14 AC2's one-click load is
#: how every *other* user gets a profile).
DEFAULT_USER_ID = "alex"

_PROFILE_SEED_PATH = config.PROJECT_ROOT / "data" / "samples" / "profile_alex.yaml"

# ---------------------------------------------------------------------------
# Developer settings and automatic demo mode (FR-18 AC1, FR-19 AC3)
# ---------------------------------------------------------------------------

#: Session-state keys for developer settings; every page reads/writes these
#: directly, so the main page and pages/4_Developer_settings.py always agree.
CHAT_MODEL_KEY = "dev_chat_model"
REASONING_EFFORT_KEY = "dev_reasoning_effort"
GET_JOB_DETAILS_ENABLED_KEY = "dev_get_job_details_enabled"
DEMO_MODE_KEY = "demo_mode"
DEMO_MODE_AUTO_MESSAGE_KEY = "demo_mode_auto_message"

#: Usage records (FR-18 AC2), kept as two lists throughout - agent loop and
#: extraction - so the UI can show the split the spec asks for, not just a
#: combined total.
SESSION_AGENT_LOOP_USAGE_KEY = "session_usage_agent_loop"
SESSION_EXTRACTION_USAGE_KEY = "session_usage_extraction"
LAST_TURN_AGENT_LOOP_USAGE_KEY = "last_turn_usage_agent_loop"
LAST_TURN_EXTRACTION_USAGE_KEY = "last_turn_usage_extraction"


def ensure_developer_settings_initialized(reachability_check: Any = None) -> None:
    """Sets session-state defaults for developer settings and demo mode.

    Called at the top of every page (same pattern as :func:`render_user_sidebar`),
    so whichever page loads first in a fresh session sees the same defaults.
    Every setting but demo mode defaults to ``config.py`` (FR-18 AC1); demo
    mode's default is decided once per session by a BA API reachability check
    (FR-19 AC3) - unreachable switches it on and records why, so the main
    page can show the message once.

    Args:
        reachability_check: Defaults to :func:`job_hunt_agent.ba_client.check_reachable`,
            looked up at call time (not bound as a default argument), so
            tests can ``monkeypatch.setattr(ba_client, "check_reachable", ...)``
            and never reach the real BA API (CLAUDE.md invariant 5) regardless
            of which page runs first.

    Related: FR-18 AC1, FR-19 AC3
    """
    st.session_state.setdefault(CHAT_MODEL_KEY, config.CHAT_MODEL)
    st.session_state.setdefault(REASONING_EFFORT_KEY, config.REASONING_EFFORT)
    st.session_state.setdefault(GET_JOB_DETAILS_ENABLED_KEY, True)
    if DEMO_MODE_KEY not in st.session_state:
        check = reachability_check or ba_client.check_reachable
        reachable = check()
        st.session_state[DEMO_MODE_KEY] = not reachable
        if not reachable:
            st.session_state[DEMO_MODE_AUTO_MESSAGE_KEY] = (
                "Demo mode was switched on automatically: the job board API was not "
                "reachable at start-up."
            )


def record_turn_usage(tracker: Any) -> None:
    """Appends one turn's usage records to the session totals (FR-18 AC2).

    Also replaces the "last turn" records shown under the newest answer, kept
    split into agent loop and extraction throughout, per FR-18 AC2. ``tracker``
    is ``None`` when usage was not tracked for this turn (e.g. an early return
    before the agent ran).

    Related: FR-18 AC2
    """
    agent_loop = tracker.agent_loop.records if tracker is not None else []
    extraction = tracker.extraction.records if tracker is not None else []
    st.session_state[LAST_TURN_AGENT_LOOP_USAGE_KEY] = agent_loop
    st.session_state[LAST_TURN_EXTRACTION_USAGE_KEY] = extraction
    st.session_state.setdefault(SESSION_AGENT_LOOP_USAGE_KEY, [])
    st.session_state.setdefault(SESSION_EXTRACTION_USAGE_KEY, [])
    st.session_state[SESSION_AGENT_LOOP_USAGE_KEY].extend(agent_loop)
    st.session_state[SESSION_EXTRACTION_USAGE_KEY].extend(extraction)


def session_usage_records() -> tuple[list[Any], list[Any]]:
    """All usage records collected so far this session: (agent loop, extraction)."""
    return (
        st.session_state.get(SESSION_AGENT_LOOP_USAGE_KEY, []),
        st.session_state.get(SESSION_EXTRACTION_USAGE_KEY, []),
    )


def last_turn_usage_records() -> tuple[list[Any], list[Any]]:
    """Usage records of the most recently completed turn: (agent loop, extraction)."""
    return (
        st.session_state.get(LAST_TURN_AGENT_LOOP_USAGE_KEY, []),
        st.session_state.get(LAST_TURN_EXTRACTION_USAGE_KEY, []),
    )


def render_usage_summary(agent_loop: list[Any], extraction: list[Any]) -> None:
    """Renders the token/cost split the main page, sidebar and settings page all share.

    Related: FR-18 AC2
    """
    from job_hunt_agent import usage as usage_module

    combined = usage_module.aggregate([*agent_loop, *extraction])
    st.caption(f"Total: {usage_module.usage_caption(combined)}")
    st.caption(f"Agent loop: {usage_module.usage_caption(usage_module.aggregate(agent_loop))}")
    st.caption(f"Extraction: {usage_module.usage_caption(usage_module.aggregate(extraction))}")


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
