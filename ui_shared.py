"""Streamlit UI resources shared by app.py and pages/ (spec §11).

The cached SQLite connection, the demo user id and profile seeding are
needed by the main chat page and the tracker page alike; this module is
the one place that defines them, imported by both rather than one page
importing from another (CLAUDE.md "Architecture and dependency
direction": UI -> package, never the reverse - no page imports app.py).

Related: FR-11 AC1, FR-14 AC1, D-5
"""

from __future__ import annotations

from typing import Any

import streamlit as st
import yaml

from job_hunt_agent import config, storage
from job_hunt_agent.models import Profile

#: No authentication yet (spec §2.2); every run is this one demo user.
USER_ID = "alex"

_PROFILE_SEED_PATH = config.PROJECT_ROOT / "data" / "samples" / "profile_alex.yaml"


@st.cache_resource
def get_connection(db_path: str) -> Any:
    """One shared SQLite connection for the checkpointer, store, tracker and profile (D-5)."""
    return storage.get_connection(db_path)


def load_or_seed_profile(conn: Any, user_id: str) -> Profile:
    """Loads the stored profile, or seeds it from the demo profile once (FR-14 AC1)."""
    profile = storage.load_profile(conn, user_id)
    if profile is not None:
        return profile
    data = yaml.safe_load(_PROFILE_SEED_PATH.read_text(encoding="utf-8"))
    profile = Profile.model_validate(data)
    storage.save_profile(conn, user_id, profile)
    return profile
