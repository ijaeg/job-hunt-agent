"""Memory page: lists and deletes the user's stored memories (FR-15 AC3).

Layout only (NFR-04): no business logic. ``storage.py`` reads and deletes
memory items on top of the long-term store (D-6); this page never calls
the agent, so deleting an item here is a user action, not an agent one -
no approval gate, the same reasoning FR-11 AC2 already applies to the
tracker page. Excluded employers keep being applied live from the store
inside ``assess_fit`` (FR-15 AC4): deleting one here takes effect on the
next assessment, without needing a new ``remember`` call.

Related: FR-15 AC3, FR-15 AC4, spec §11
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import streamlit as st

# See app.py's matching comment: this page can run in ways that skip
# Streamlit's "insert the entry script's own directory into sys.path"
# trick - most notably a test driving it directly via
# ``AppTest.from_file(this_path)`` - so it adds the repo root itself
# before importing the sibling ``ui_shared`` module.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from job_hunt_agent import config, storage  # noqa: E402
from ui_shared import get_connection, render_user_sidebar  # noqa: E402

st.set_page_config(page_title="Memory - Job Hunt Agent", layout="wide")

_KIND_LABELS: dict[str, str] = {
    "excluded_employer": "Excluded employer",
    "preference": "Preference",
}


def render_memory(conn: Any, user_id: str, memory: dict[str, Any]) -> None:
    """Renders one memory row: kind, value, created date, delete with confirmation."""
    with st.container(border=True):
        label_col, delete_col = st.columns([4, 1])

        with label_col:
            label = _KIND_LABELS.get(memory["kind"], memory["kind"])
            st.markdown(f"**{label}:** {memory['value']}")
            st.caption(f"Saved {memory['created_at'].date().isoformat()}")

        with delete_col:
            confirm_key = f"confirm_delete_{memory['key']}"
            if st.session_state.get(confirm_key):
                st.warning("Delete this memory?")
                yes_col, no_col = st.columns(2)
                if yes_col.button("Yes, delete", key=f"delete_yes_{memory['key']}"):
                    try:
                        storage.delete_memory(conn, user_id, memory["key"])
                    except Exception:  # noqa: BLE001 - invariant 7: never a stack trace in the UI
                        st.error("Could not delete that memory. Please try again.")
                    st.session_state.pop(confirm_key, None)
                    st.rerun()
                if no_col.button("Cancel", key=f"delete_cancel_{memory['key']}"):
                    st.session_state.pop(confirm_key, None)
                    st.rerun()
            elif st.button("Delete", key=f"delete_{memory['key']}"):
                st.session_state[confirm_key] = True
                st.rerun()


def main() -> None:
    st.title("Memory")

    conn = get_connection(os.getenv("DB_PATH", config.DB_PATH))
    user_id = render_user_sidebar(conn)
    try:
        memories = storage.list_memories(conn, user_id)
    except Exception:  # noqa: BLE001 - invariant 7: never a stack trace in the UI
        st.error("Could not load your memories. Please try again.")
        return

    if not memories:
        st.caption(
            "No memories saved yet – ask the agent to remember a preference or to "
            "exclude an employer; it will ask for your approval before saving."
        )
        return

    for memory in memories:
        render_memory(conn, user_id, memory)


if __name__ == "__main__":
    main()
