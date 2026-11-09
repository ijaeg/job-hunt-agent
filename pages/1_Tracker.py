"""Tracker page: list, update and delete the user's saved listings (FR-11).

Layout only (NFR-04): no business logic. ``storage.py`` persists the
tracker rows; ``job_hunt_agent.tracker_view`` (pure, no Streamlit) orders
them and decides which are overdue. This page never calls the agent, so
none of its actions - changing a status, deleting an entry - go through
approval: FR-11 AC2 is explicit that these are user actions, not agent
ones (contrast with ``save_to_tracker``'s approval in app.py, FR-10).

Related: FR-11 AC1, FR-11 AC2, spec §11
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, date, datetime
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

from job_hunt_agent import config, storage, tracker_view, ui_view  # noqa: E402
from job_hunt_agent.models import TrackerEntry  # noqa: E402
from ui_shared import USER_ID, get_connection  # noqa: E402

st.set_page_config(page_title="Tracker - Job Hunt Agent", layout="wide")

_STATUSES: list[str] = ["saved", "applied", "rejected"]


def _update_status(conn: Any, entry: TrackerEntry, new_status: str) -> None:
    """Reuses ``save_tracker_entry`` with a new ``updated_at``; ``created_at`` is untouched."""
    updated = entry.model_copy(update={"status": new_status, "updated_at": datetime.now(UTC)})
    storage.save_tracker_entry(conn, updated)  # type: ignore[arg-type]


def render_entry(conn: Any, entry: TrackerEntry, overdue: bool) -> None:
    """Renders one tracker row: title/employer, status, follow-up date, note, delete."""
    with st.container(border=True):
        title_col, status_col, date_col, delete_col = st.columns([3, 2, 2, 2])

        with title_col:
            st.markdown(f"**[{entry.title}]({ui_view.listing_url(entry.referenznummer)})**")
            if entry.employer:
                st.caption(entry.employer)

        with status_col:
            new_status = st.selectbox(
                "Status",
                _STATUSES,
                index=_STATUSES.index(entry.status),
                key=f"status_{entry.referenznummer}",
                label_visibility="collapsed",
            )
            if new_status != entry.status:
                try:
                    _update_status(conn, entry, new_status)
                except Exception:  # noqa: BLE001 - invariant 7: never a stack trace in the UI
                    st.error("Could not update that entry. Please try again.")
                else:
                    st.rerun()

        with date_col:
            if entry.follow_up_date:
                label = f"Follow-up: {entry.follow_up_date.isoformat()}"
                st.markdown(f":red[**Overdue** – {label}]" if overdue else label)
            else:
                st.caption("No follow-up date")

        if entry.note:
            st.caption(f"Note: {entry.note}")

        with delete_col:
            confirm_key = f"confirm_delete_{entry.referenznummer}"
            if st.session_state.get(confirm_key):
                st.warning("Delete this entry?")
                yes_col, no_col = st.columns(2)
                if yes_col.button("Yes, delete", key=f"delete_yes_{entry.referenznummer}"):
                    try:
                        storage.delete_tracker_entry(conn, entry.user_id, entry.referenznummer)
                    except Exception:  # noqa: BLE001 - invariant 7
                        st.error("Could not delete that entry. Please try again.")
                    st.session_state.pop(confirm_key, None)
                    st.rerun()
                if no_col.button("Cancel", key=f"delete_cancel_{entry.referenznummer}"):
                    st.session_state.pop(confirm_key, None)
                    st.rerun()
            elif st.button("Delete", key=f"delete_{entry.referenznummer}"):
                st.session_state[confirm_key] = True
                st.rerun()


def main() -> None:
    st.title("Tracker")

    conn = get_connection(os.getenv("DB_PATH", config.DB_PATH))
    try:
        entries = storage.list_tracker_entries(conn, USER_ID)
    except Exception:  # noqa: BLE001 - invariant 7: never a stack trace in the UI
        st.error("Could not load the tracker. Please try again.")
        return

    if not entries:
        st.caption(
            "No tracker entries yet – save a listing from the shortlist on the main page "
            "to see it here."
        )
        return

    today = date.today()
    for entry in tracker_view.order_entries(entries, today):
        render_entry(conn, entry, tracker_view.is_overdue(entry.follow_up_date, today))


if __name__ == "__main__":
    main()
