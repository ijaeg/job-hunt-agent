"""Agent-level integration tests: approval, rejection lock, resume after restart.

Mirrors the pattern proven in ``spikes/hitl_app.py``/``spikes/test_hitl_app.py``
(D-5) with this package's real middleware and tools instead of the spike's
dummy ones.

Related: FR-09, FR-10 AC1, FR-10 AC3, FR-10 AC4, FR-13 AC3, FR-15, D-5
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from conftest import ScriptedModel
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from job_hunt_agent import storage
from job_hunt_agent.context import AgentContext
from job_hunt_agent.middleware.rejection_lock import RejectionLockMiddleware
from job_hunt_agent.models import JobSummary, Profile
from job_hunt_agent.state import JobHuntState
from job_hunt_agent.tools.memory import remember
from job_hunt_agent.tools.tracker import save_to_tracker

HITL_MIDDLEWARE = [
    HumanInTheLoopMiddleware(
        interrupt_on={
            "save_to_tracker": {"allowed_decisions": ["approve", "edit", "reject"]},
            "remember": {"allowed_decisions": ["approve", "edit", "reject"]},
        }
    ),
    RejectionLockMiddleware(),
]


def _profile() -> Profile:
    return Profile(
        skills=["Python"],
        seniority="senior",
        location="Hamburg",
        radius_km=25,
        remote_preference="hybrid",
        german_level="basic",
        english_level="native",
    )


class FakeSource:
    def search(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def get_details(self, referenznummer: str) -> Any:
        raise AssertionError("not needed for these tests")


def _build(tools: list[Any], turns: list[Any], checkpointer: Any, store: Any = None) -> Any:
    return create_agent(
        model=ScriptedModel(turns),
        tools=tools,
        state_schema=JobHuntState,
        context_schema=AgentContext,
        middleware=HITL_MIDDLEWARE,
        checkpointer=checkpointer,
        store=store,
    )


def _context(conn: Any = None) -> AgentContext:
    return AgentContext(
        job_source=FakeSource(), profile=_profile(), extraction_model=None, conn=conn
    )


# ---------------------------------------------------------------------------
# Approval required for both write tools (FR-10 AC1, AC4)
# ---------------------------------------------------------------------------


def test_save_to_tracker_does_not_run_without_approval(tmp_path: Path) -> None:
    """FR-10 AC4: no write tool executes without a recorded approval."""
    conn = storage.get_connection(str(tmp_path / "t.sqlite"))
    agent = _build(
        [save_to_tracker],
        [
            [
                {
                    "name": "save_to_tracker",
                    "args": {"referenznummer": "A-1-S", "status": "saved"},
                }
            ]
        ],
        storage.get_checkpointer(conn),
    )
    cfg = {"configurable": {"thread_id": "t1"}}
    agent.invoke(
        {
            "messages": [HumanMessage("save it")],
            "user_id": "alex",
            "summaries": {"A-1-S": JobSummary(referenznummer="A-1-S", title="Python Dev")},
        },
        config=cfg,
        context=_context(conn),
    )
    assert storage.get_tracker_entry(conn, "alex", "A-1-S") is None
    assert agent.get_state(cfg).interrupts


def test_save_to_tracker_runs_after_approval(tmp_path: Path) -> None:
    """FR-10 AC1: approving the proposal lets the tool run."""
    conn = storage.get_connection(str(tmp_path / "t.sqlite"))
    agent = _build(
        [save_to_tracker],
        [
            [
                {
                    "name": "save_to_tracker",
                    "args": {"referenznummer": "A-1-S", "status": "saved"},
                }
            ],
            "Saved it.",
        ],
        storage.get_checkpointer(conn),
    )
    cfg = {"configurable": {"thread_id": "t1"}}
    ctx = _context(conn)
    agent.invoke(
        {
            "messages": [HumanMessage("save it")],
            "user_id": "alex",
            "summaries": {"A-1-S": JobSummary(referenznummer="A-1-S", title="Python Dev")},
        },
        config=cfg,
        context=ctx,
    )
    agent.invoke(Command(resume={"decisions": [{"type": "approve"}]}), config=cfg, context=ctx)
    stored = storage.get_tracker_entry(conn, "alex", "A-1-S")
    assert stored is not None
    assert stored.status == "saved"


def test_save_to_tracker_does_not_run_after_rejection(tmp_path: Path) -> None:
    """FR-10 AC3: a rejected action is never executed later."""
    conn = storage.get_connection(str(tmp_path / "t.sqlite"))
    agent = _build(
        [save_to_tracker],
        [
            [
                {
                    "name": "save_to_tracker",
                    "args": {"referenznummer": "A-1-S", "status": "saved"},
                }
            ],
            "Understood, not saved.",
        ],
        storage.get_checkpointer(conn),
    )
    cfg = {"configurable": {"thread_id": "t1"}}
    ctx = _context(conn)
    agent.invoke(
        {
            "messages": [HumanMessage("save it")],
            "user_id": "alex",
            "summaries": {"A-1-S": JobSummary(referenznummer="A-1-S", title="Python Dev")},
        },
        config=cfg,
        context=ctx,
    )
    agent.invoke(
        Command(resume={"decisions": [{"type": "reject", "message": "not now"}]}),
        config=cfg,
        context=ctx,
    )
    assert storage.get_tracker_entry(conn, "alex", "A-1-S") is None


def test_remember_does_not_run_without_approval() -> None:
    """FR-10 AC4: the ``remember`` write tool also requires approval."""
    store = InMemoryStore()
    agent = _build(
        [remember],
        [[{"name": "remember", "args": {"kind": "preference", "value": "remote only"}}]],
        InMemorySaver(),
        store=store,
    )
    cfg = {"configurable": {"thread_id": "t1"}}
    agent.invoke(
        {"messages": [HumanMessage("remember this")], "user_id": "alex"},
        config=cfg,
        context=_context(),
    )
    assert store.search(("memories", "alex")) == []
    assert agent.get_state(cfg).interrupts


def test_remember_runs_after_approval() -> None:
    store = InMemoryStore()
    agent = _build(
        [remember],
        [
            [{"name": "remember", "args": {"kind": "preference", "value": "remote only"}}],
            "Got it.",
        ],
        InMemorySaver(),
        store=store,
    )
    cfg = {"configurable": {"thread_id": "t1"}}
    ctx = _context()
    agent.invoke(
        {"messages": [HumanMessage("remember this")], "user_id": "alex"}, config=cfg, context=ctx
    )
    agent.invoke(Command(resume={"decisions": [{"type": "approve"}]}), config=cfg, context=ctx)
    assert len(store.search(("memories", "alex"))) == 1


# ---------------------------------------------------------------------------
# Rejection lock (spec §5.4 #4, FR-10 AC3)
# ---------------------------------------------------------------------------


def test_rejection_lock_drops_repeated_proposal_without_second_interrupt() -> None:
    """D-5's central finding: a repeated identical proposal is dropped, not re-interrupted."""
    store = InMemoryStore()
    call = {"name": "remember", "args": {"kind": "preference", "value": "remote only"}}
    agent = _build([remember], [[call], [call]], InMemorySaver(), store=store)
    cfg = {"configurable": {"thread_id": "t1"}}
    ctx = _context()
    agent.invoke(
        {"messages": [HumanMessage("remember this")], "user_id": "alex"}, config=cfg, context=ctx
    )
    result = agent.invoke(
        Command(resume={"decisions": [{"type": "reject", "message": "no"}]}),
        config=cfg,
        context=ctx,
    )
    assert not agent.get_state(cfg).interrupts
    assert "already rejected" in str(result["messages"][-1].content)
    assert store.search(("memories", "alex")) == []


# ---------------------------------------------------------------------------
# Resume after restart from the checkpointer (FR-13 AC3)
# ---------------------------------------------------------------------------


def test_resume_after_restart_reads_the_pending_interrupt_from_sqlite(tmp_path: Path) -> None:
    """FR-13 AC3: a fresh agent object on the same thread/file still sees the interrupt."""
    db_path = str(tmp_path / "restart.sqlite")
    storage.get_connection.cache_clear()
    conn1 = storage.get_connection(db_path)
    agent1 = _build(
        [save_to_tracker],
        [[{"name": "save_to_tracker", "args": {"referenznummer": "A-1-S", "status": "saved"}}]],
        storage.get_checkpointer(conn1),
    )
    cfg = {"configurable": {"thread_id": "restart-thread"}}
    agent1.invoke(
        {
            "messages": [HumanMessage("save it")],
            "user_id": "alex",
            "summaries": {"A-1-S": JobSummary(referenznummer="A-1-S", title="Python Dev")},
        },
        config=cfg,
        context=_context(conn1),
    )
    assert agent1.get_state(cfg).interrupts

    # Simulate a restart: clear the cached connection, open a genuinely new one.
    storage.get_connection.cache_clear()
    conn2 = storage.get_connection(db_path)
    agent2 = _build([save_to_tracker], [], storage.get_checkpointer(conn2))
    assert agent2.get_state(cfg).interrupts

    agent2.invoke(
        Command(resume={"decisions": [{"type": "approve"}]}), config=cfg, context=_context(conn2)
    )
    stored = storage.get_tracker_entry(conn2, "alex", "A-1-S")
    assert stored is not None
    assert stored.status == "saved"
