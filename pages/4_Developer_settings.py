"""Developer settings page: model, reasoning effort, tool toggles, demo mode,
and token usage/cost (FR-18 AC1, FR-18 AC2, FR-19 AC3).

Layout only (NFR-04): no business logic. Settings live in ``st.session_state``
(``ui_shared.py`` owns the keys), default to ``config.py``, and are read by
``app.py`` when it builds the model and the agent's tool list - this page
never builds either itself. Each widget below is bound to its own throwaway
``*_WIDGET_KEY`` and syncs into the real setting key on change, not to the
setting key directly - see ``ui_shared.py``'s comment above those constants
for why (Addendum 1 to WP-09).

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

from job_hunt_agent import config, tracing  # noqa: E402
from ui_shared import (  # noqa: E402
    CHAT_MODEL_KEY,
    CHAT_MODEL_WIDGET_KEY,
    DEMO_MODE_AUTO_MESSAGE_KEY,
    DEMO_MODE_KEY,
    DEMO_MODE_WIDGET_KEY,
    GET_JOB_DETAILS_ENABLED_KEY,
    GET_JOB_DETAILS_ENABLED_WIDGET_KEY,
    LANGSMITH_TRACING_KEY,
    LANGSMITH_TRACING_WIDGET_KEY,
    LIST_TRACKER_ENABLED_KEY,
    LIST_TRACKER_ENABLED_WIDGET_KEY,
    REASONING_EFFORT_KEY,
    REASONING_EFFORT_WIDGET_KEY,
    ensure_developer_settings_initialized,
    get_connection,
    render_usage_summary,
    render_user_sidebar,
    session_usage_records,
    sync_setting_from_widget,
)

st.set_page_config(page_title="Developer settings - Job Hunt Agent", layout="wide")


def main() -> None:
    conn = get_connection(os.getenv("DB_PATH", config.DB_PATH))
    render_user_sidebar(conn)
    ensure_developer_settings_initialized()

    st.title("Developer settings")
    st.caption("Not part of the main flow (FR-18 AC1) - changes apply to the next turn.")

    st.selectbox(
        "Chat model",
        config.CHAT_MODEL_OPTIONS,
        index=config.CHAT_MODEL_OPTIONS.index(st.session_state[CHAT_MODEL_KEY]),
        key=CHAT_MODEL_WIDGET_KEY,
        on_change=sync_setting_from_widget,
        args=(CHAT_MODEL_KEY, CHAT_MODEL_WIDGET_KEY),
    )
    st.selectbox(
        "Reasoning effort",
        config.REASONING_EFFORT_OPTIONS,
        index=config.REASONING_EFFORT_OPTIONS.index(st.session_state[REASONING_EFFORT_KEY]),
        key=REASONING_EFFORT_WIDGET_KEY,
        on_change=sync_setting_from_widget,
        args=(REASONING_EFFORT_KEY, REASONING_EFFORT_WIDGET_KEY),
    )
    st.caption(
        "The same model and reasoning effort are used for the structured-extraction "
        "calls inside assess_fit."
    )

    st.toggle(
        "Enable get_job_details tool",
        value=st.session_state[GET_JOB_DETAILS_ENABLED_KEY],
        key=GET_JOB_DETAILS_ENABLED_WIDGET_KEY,
        on_change=sync_setting_from_widget,
        args=(GET_JOB_DETAILS_ENABLED_KEY, GET_JOB_DETAILS_ENABLED_WIDGET_KEY),
        help="assess_fit always loads listing details itself, regardless of this toggle.",
    )

    st.toggle(
        "Enable list_tracker tool",
        value=st.session_state[LIST_TRACKER_ENABLED_KEY],
        key=LIST_TRACKER_ENABLED_WIDGET_KEY,
        on_change=sync_setting_from_widget,
        args=(LIST_TRACKER_ENABLED_KEY, LIST_TRACKER_ENABLED_WIDGET_KEY),
        help='Lets the agent answer "what have I saved?" and avoid re-suggesting saved listings.',
    )

    st.toggle(
        "Demo mode",
        value=st.session_state[DEMO_MODE_KEY],
        key=DEMO_MODE_WIDGET_KEY,
        on_change=sync_setting_from_widget,
        args=(DEMO_MODE_KEY, DEMO_MODE_WIDGET_KEY),
    )
    auto_message = st.session_state.get(DEMO_MODE_AUTO_MESSAGE_KEY)
    if auto_message:
        st.info(auto_message)

    has_langsmith_key = tracing.langsmith_key_present()
    if not has_langsmith_key:
        st.session_state[LANGSMITH_TRACING_KEY] = False
    st.toggle(
        "LangSmith tracing",
        value=st.session_state[LANGSMITH_TRACING_KEY],
        key=LANGSMITH_TRACING_WIDGET_KEY,
        on_change=sync_setting_from_widget,
        args=(LANGSMITH_TRACING_KEY, LANGSMITH_TRACING_WIDGET_KEY),
        disabled=not has_langsmith_key,
        help="Off by default (D-18); traces are sent to LangSmith while this is on.",
    )
    if not has_langsmith_key:
        st.caption(f"Set {config.LANGSMITH_API_KEY_ENV} to enable tracing.")

    st.divider()
    st.subheader("Token usage and cost this session")
    agent_loop, extraction = session_usage_records()
    render_usage_summary(agent_loop, extraction)


if __name__ == "__main__":
    main()
