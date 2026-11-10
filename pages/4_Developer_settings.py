"""Developer settings page: model, reasoning effort, tool toggle, demo mode,
and token usage/cost (FR-18 AC1, FR-18 AC2, FR-19 AC3).

Layout only (NFR-04): no business logic. Settings live in ``st.session_state``
(``ui_shared.py`` owns the keys), default to ``config.py``, and are read by
``app.py`` when it builds the model and the agent's tool list - this page
never builds either itself.

Related: FR-18 AC1, FR-18 AC2, FR-19 AC3, D-17, spec §11
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

# See app.py's matching comment: this page can run in ways that skip
# Streamlit's "insert the entry script's own directory into sys.path" trick -
# most notably AppTest.from_file(this_path) - so it adds the repo root itself
# before importing the sibling ui_shared module.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from job_hunt_agent import config  # noqa: E402
from ui_shared import (  # noqa: E402
    CHAT_MODEL_KEY,
    DEMO_MODE_AUTO_MESSAGE_KEY,
    DEMO_MODE_KEY,
    GET_JOB_DETAILS_ENABLED_KEY,
    REASONING_EFFORT_KEY,
    ensure_developer_settings_initialized,
    get_connection,
    render_usage_summary,
    render_user_sidebar,
    session_usage_records,
)

st.set_page_config(page_title="Developer settings - Job Hunt Agent", layout="wide")


def main() -> None:
    conn = get_connection(os.getenv("DB_PATH", config.DB_PATH))
    render_user_sidebar(conn)
    ensure_developer_settings_initialized()

    st.title("Developer settings")
    st.caption("Not part of the main flow (FR-18 AC1) - changes apply to the next turn.")

    st.selectbox("Chat model", config.CHAT_MODEL_OPTIONS, key=CHAT_MODEL_KEY)
    st.selectbox("Reasoning effort", config.REASONING_EFFORT_OPTIONS, key=REASONING_EFFORT_KEY)
    st.caption(
        "The same model and reasoning effort are used for the structured-extraction "
        "calls inside assess_fit."
    )

    st.toggle(
        "Enable get_job_details tool",
        key=GET_JOB_DETAILS_ENABLED_KEY,
        help="assess_fit always loads listing details itself, regardless of this toggle.",
    )

    st.toggle("Demo mode", key=DEMO_MODE_KEY)
    auto_message = st.session_state.get(DEMO_MODE_AUTO_MESSAGE_KEY)
    if auto_message:
        st.info(auto_message)

    st.divider()
    st.subheader("Token usage and cost this session")
    agent_loop, extraction = session_usage_records()
    render_usage_summary(agent_loop, extraction)


if __name__ == "__main__":
    main()
