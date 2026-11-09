"""AppTest integration tests for ``app.py`` (WP-04 core journey UI).

Uses ``streamlit.testing.v1.AppTest`` with a scripted model
(``JOB_HUNT_FAKE_MODEL=1``, mirroring ``spikes/hitl_app.py``'s pattern, D-5)
and the demo ``FixtureSource`` - no network call, no API key needed
(CLAUDE.md invariant 5, NFR-05).

Card-rendering tests seed state directly via ``agent.update_state()``
(bypassing the model entirely) rather than driving a full search ->
details -> assess_fit chain through the scripted model - that chain is
already covered by ``tests/test_tools_assess.py`` and
``scripts/run_core_journey.py``'s real-model run; this file is about the
*view*, not the pipeline.

Related: FR-01 AC1, FR-07, FR-10 AC2, FR-10 AC5, FR-13 AC3, FR-16, NFR-05, D-5
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from job_hunt_agent import storage
from job_hunt_agent.agent import build_agent
from job_hunt_agent.models import FitAssessment, JobSummary

APP_PATH = str(Path(__file__).resolve().parents[1] / "app.py")

#: A referenznummer actually present in the committed fixture set, so
#: ``save_to_tracker``'s fallback ``get_details`` call (no cached summary)
#: succeeds without a prior search_jobs call.
A_REAL_REF = "10001-1003822592-S"


def _load_app_module() -> ModuleType:
    """Loads ``app.py`` by path so its ``st.cache_resource``-wrapped
    ``get_connection`` (keyed by source hash, not module identity) can be
    cleared from the test - same trick as ``spikes/test_hitl_app.py``.
    """
    spec = importlib.util.spec_from_file_location("app_under_test", APP_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _fake_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOB_HUNT_FAKE_MODEL", "1")


# ---------------------------------------------------------------------------
# iter_new_tool_calls: dedup across echoed stream_mode="updates" steps
# ---------------------------------------------------------------------------


def test_iter_new_tool_calls_dedups_the_same_call_echoed_by_later_middleware_steps() -> None:
    """Reproduces the real bug found in the WP-04 smoke run.

    ``stream_mode="updates"`` re-emits the *same* ``AIMessage`` (same tool
    call id) from later middleware hooks (e.g. the built-in
    ``PIIMiddleware``) that return the whole ``messages`` list, not just
    what is new. Counting every occurrence double-counted every tool call
    in ``eval/results/ui_smoke_wp04.json``'s first run.
    """
    from langchain_core.messages import AIMessage

    app = _load_app_module()

    call = AIMessage(content="", tool_calls=[{"name": "search_jobs", "args": {}, "id": "call_1"}])
    steps = [
        {"model": {"messages": [call]}},
        {"PIIMiddleware[phone].before_model": {"messages": [call]}},  # echoed, same id
        {"PIIMiddleware[email].before_model": {"messages": [call]}},  # echoed again
    ]

    seen: set[str] = set()
    all_new_calls = [tc for step in steps for tc in app.iter_new_tool_calls(step, seen)]
    assert len(all_new_calls) == 1
    assert all_new_calls[0]["name"] == "search_jobs"


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    path = str(tmp_path / f"wp04-{uuid.uuid4().hex}.sqlite")
    monkeypatch.setenv("DB_PATH", path)
    return path


def new_app(scripted_turns: list[Any], thread_id: str | None = None) -> AppTest:
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.session_state["_scripted_turns"] = scripted_turns
    if thread_id:
        at.query_params["thread_id"] = thread_id
    return at


def _seed_shortlist(db_path: str, thread_id: str) -> None:
    """Writes shortlist/summaries/assessments straight into the checkpointer.

    Related: FR-07 AC1, FR-07 AC2
    """
    conn = storage.get_connection(db_path)
    agent = build_agent(model=object(), conn=conn)
    cfg = {"configurable": {"thread_id": thread_id}}
    agent.update_state(
        cfg,
        {
            "user_id": "alex",
            "shortlist": ["A-1-S", "B-2-S", "C-3-S", "D-4-S"],
            "summaries": {
                "A-1-S": JobSummary(referenznummer="A-1-S", title="Poor Match", employer="Gamma"),
                "B-2-S": JobSummary(referenznummer="B-2-S", title="Strong Match", employer="Acme"),
                "C-3-S": JobSummary(referenznummer="C-3-S", title="Partial Match", employer="Beta"),
                "D-4-S": JobSummary(
                    referenznummer="D-4-S", title="Excluded Match", employer="Delta"
                ),
            },
            "assessments": {
                "A-1-S": FitAssessment(referenznummer="A-1-S", category="poor"),
                "B-2-S": FitAssessment(
                    referenznummer="B-2-S",
                    category="strong",
                    matches=["Python — writes production Python"],
                ),
                "C-3-S": FitAssessment(referenznummer="C-3-S", category="partial"),
                "D-4-S": FitAssessment(
                    referenznummer="D-4-S",
                    category="excluded",
                    exclusion_reasons=["temporary agency work"],
                ),
            },
        },
    )


# ---------------------------------------------------------------------------
# (a) a turn renders cards in the right order (FR-07 AC1, AC2)
# ---------------------------------------------------------------------------


def test_cards_render_strong_partial_poor_excluded_separate(db_path: str) -> None:
    thread_id = "cards-thread"
    _seed_shortlist(db_path, thread_id)

    at = new_app([], thread_id=thread_id)
    at.run()

    assert not at.exception
    markdown_text = [str(m.value) for m in at.markdown]
    titles = [text for text in markdown_text if text.startswith("**[")]
    # Strong -> partial -> poor, then the excluded listing last, inside its
    # own collapsed expander (FR-07 AC2).
    assert titles == [
        "**[Strong Match](https://www.arbeitsagentur.de/jobsuche/jobdetail/B-2-S)**",
        "**[Partial Match](https://www.arbeitsagentur.de/jobsuche/jobdetail/C-3-S)**",
        "**[Poor Match](https://www.arbeitsagentur.de/jobsuche/jobdetail/A-1-S)**",
        "**[Excluded Match](https://www.arbeitsagentur.de/jobsuche/jobdetail/D-4-S)**",
    ]
    assert any("Excluded Match" in str(m.value) for e in at.expander for m in e.markdown)


# ---------------------------------------------------------------------------
# (b) a save request raises the approval and shows the arguments (FR-10 AC2)
# ---------------------------------------------------------------------------


def test_save_request_raises_approval_with_exact_arguments(db_path: str) -> None:
    at = new_app(
        [
            [
                {
                    "name": "save_to_tracker",
                    "args": {"referenznummer": A_REAL_REF, "status": "saved"},
                }
            ]
        ]
    )
    at.run()
    at.chat_input[0].set_value("save it").run()

    assert not at.exception
    assert any("save_to_tracker" in str(w.value) for w in at.warning)
    assert any(
        json.loads(j.value) == {"referenznummer": A_REAL_REF, "status": "saved"} for j in at.json
    )


# ---------------------------------------------------------------------------
# (c) approve writes the tracker row (checked directly against SQLite)
# ---------------------------------------------------------------------------


def test_approve_writes_the_tracker_row(db_path: str) -> None:
    at = new_app(
        [
            [
                {
                    "name": "save_to_tracker",
                    "args": {"referenznummer": A_REAL_REF, "status": "saved"},
                }
            ],
            "Saved it.",
        ]
    )
    at.run()
    at.chat_input[0].set_value("save it").run()
    at.button(key="approval_approve_0").click().run()

    assert not at.exception
    conn = storage.get_connection(db_path)
    entry = storage.get_tracker_entry(conn, "alex", A_REAL_REF)
    assert entry is not None
    assert entry.status == "saved"


# ---------------------------------------------------------------------------
# (d) reject writes nothing (FR-10 AC3)
# ---------------------------------------------------------------------------


def test_reject_writes_nothing(db_path: str) -> None:
    at = new_app(
        [
            [
                {
                    "name": "save_to_tracker",
                    "args": {"referenznummer": A_REAL_REF, "status": "saved"},
                }
            ],
            "Understood, not saved.",
        ]
    )
    at.run()
    at.chat_input[0].set_value("save it").run()
    at.button(key="approval_reject_0").click().run()

    assert not at.exception
    conn = storage.get_connection(db_path)
    assert storage.get_tracker_entry(conn, "alex", A_REAL_REF) is None


# ---------------------------------------------------------------------------
# Edit decision: edited args reach the tracker row (FR-10 AC2)
# ---------------------------------------------------------------------------


def test_edit_decision_writes_the_edited_arguments(db_path: str) -> None:
    at = new_app(
        [
            [
                {
                    "name": "save_to_tracker",
                    "args": {"referenznummer": A_REAL_REF, "status": "saved"},
                }
            ],
            "Updated it.",
        ]
    )
    at.run()
    at.chat_input[0].set_value("save it").run()

    at.button(key="approval_edit_btn_0").click().run()
    assert not at.exception
    assert any(b.label == "Save edited action" for b in at.button)

    at.selectbox(key="approval_edit_0_status").set_value("applied").run()
    at.text_input(key="approval_edit_0_note").set_value("great fit, applying").run()
    at.button(key="approval_save_edit_0").click().run()

    assert not at.exception
    conn = storage.get_connection(db_path)
    entry = storage.get_tracker_entry(conn, "alex", A_REAL_REF)
    assert entry is not None
    assert entry.status == "applied"
    assert entry.note == "great fit, applying"


# ---------------------------------------------------------------------------
# (e) a new AppTest on the same DB file/thread (simulated restart) still
#     shows the pending interrupt and the history (FR-13 AC3)
# ---------------------------------------------------------------------------


def test_restart_resumes_the_same_thread_and_keeps_history(db_path: str) -> None:
    thread_id = "restart-thread"
    at1 = new_app(
        [
            [
                {
                    "name": "save_to_tracker",
                    "args": {"referenznummer": A_REAL_REF, "status": "saved"},
                }
            ]
        ],
        thread_id=thread_id,
    )
    at1.run()
    at1.chat_input[0].set_value("save it").run()
    assert not at1.exception
    assert any("save_to_tracker" in str(w.value) for w in at1.warning)

    # Simulate a restart: clear app.py's cached connection, open a genuinely new one.
    app_module = _load_app_module()
    app_module.get_connection.clear()

    at2 = new_app([], thread_id=thread_id)
    at2.run()
    assert not at2.exception
    # The history survived the restart - including the user's own message,
    # but not the injected profile-context one (FR-01 AC1, FR-01 AC4).
    chat_text = [str(m.value) for cm in at2.chat_message for m in cm.markdown]
    assert "save it" in chat_text
    assert not any("not a message from the user" in text for text in chat_text)
    assert any("save_to_tracker" in str(w.value) for w in at2.warning)

    at2.button(key="approval_approve_0").click().run()
    assert not at2.exception

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT status FROM tracker WHERE user_id = ? AND referenznummer = ?",
        ("alex", A_REAL_REF),
    ).fetchone()
    assert row == ("saved",)
