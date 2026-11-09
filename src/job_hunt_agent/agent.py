"""Agent assembly (spec §5): state, tools, middleware, checkpointer and store.

Two "load once per thread" middlewares run early, right after the input
guard: ``LoadProfileContextMiddleware`` (FR-01 AC4, needed by autonomous
search refinement, FR-03 AC1, D-10 addendum) and ``LoadMemoryContextMiddleware``
(FR-15 AC2, closing the gap WP-05/WP-06 left open - the system prompt's
"apply automatically" wording now has something to point at). Both inject
one labelled context message on the thread's first model call; the hard
exclusion from an excluded employer is applied independently, by code, in
``tools/assess.py`` (``rubric.hard_exclusions``, read live from the store)
- the context message only lets the model *explain* that filtering, never
decide it (FR-15 AC4).

Related: spec §5, §5.4, FR-01 AC4, FR-10, FR-15 AC2, FR-15 AC4, D-5, D-6, D-10
"""

from __future__ import annotations

import sqlite3
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware

from job_hunt_agent import config, storage
from job_hunt_agent.context import AgentContext
from job_hunt_agent.middleware.input_guard import InputGuardMiddleware
from job_hunt_agent.middleware.limits import (
    ResetSearchCallCounterMiddleware,
    build_model_call_limit_middleware,
)
from job_hunt_agent.middleware.memory_context import LoadMemoryContextMiddleware
from job_hunt_agent.middleware.pii_guard import build_pii_middlewares
from job_hunt_agent.middleware.profile_context import LoadProfileContextMiddleware
from job_hunt_agent.middleware.rejection_lock import RejectionLockMiddleware
from job_hunt_agent.middleware.tool_errors import tool_error_middleware
from job_hunt_agent.state import JobHuntState
from job_hunt_agent.tools.assess import assess_fit
from job_hunt_agent.tools.details import get_job_details
from job_hunt_agent.tools.memory import remember
from job_hunt_agent.tools.search import search_jobs
from job_hunt_agent.tools.tracker import save_to_tracker

_SYSTEM_PROMPT_PATH = config.PROJECT_ROOT / "prompts" / "system.md"

#: The five tools of the core journey (spec §4); ``list_tracker`` is a
#: Should item, not included (CLAUDE.md "Order of work").
AGENT_TOOLS = [search_jobs, get_job_details, assess_fit, save_to_tracker, remember]

#: Tools gated by human approval (FR-10 AC1).
WRITE_TOOLS = {"save_to_tracker", "remember"}


def load_system_prompt() -> str:
    """Reads the system prompt (FR-03 AC1, FR-10 AC6, FR-21 AC2, FR-23 AC1)."""
    return _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def build_agent(model: Any, conn: sqlite3.Connection) -> Any:
    """Builds the compiled agent graph (spec §5).

    ``context=AgentContext(job_source=..., profile=..., extraction_model=...,
    conn=conn)`` must be supplied at invoke time - it is not baked in here,
    since the job source (live vs. demo, FR-19 AC1) and profile can differ
    per run.

    Args:
        model: Chat model for the main ReAct loop (``config.CHAT_MODEL`` by
            convention; tests pass a scripted stand-in, CLAUDE.md
            invariant 5).
        conn: Shared SQLite connection (``storage.get_connection``) for the
            checkpointer (FR-13) and memory store (FR-15, D-6).

    Returns:
        A compiled, invokable agent (``langgraph`` ``CompiledStateGraph``).

    Related: spec §5, §5.4, FR-10, FR-13, FR-15, D-5, D-6
    """
    checkpointer = storage.get_checkpointer(conn)
    store = storage.get_store(conn)

    # Heterogeneous middleware types (the built-in ModelCallLimitMiddleware's
    # own generics, this package's bare-AgentMiddleware subclasses, and a
    # plain @wrap_tool_call-built instance) don't unify under a single
    # AgentMiddleware[...] generic signature; list[Any] sidesteps that
    # without weakening any individual middleware's own type checking.
    middleware: list[Any] = [
        InputGuardMiddleware(),
        LoadProfileContextMiddleware(),
        LoadMemoryContextMiddleware(),
        *build_pii_middlewares(),
        build_model_call_limit_middleware(),
        ResetSearchCallCounterMiddleware(),
        HumanInTheLoopMiddleware(
            interrupt_on={
                "save_to_tracker": {"allowed_decisions": ["approve", "edit", "reject"]},
                "remember": {"allowed_decisions": ["approve", "edit", "reject"]},
            }
        ),
        # Listed AFTER HumanInTheLoopMiddleware on purpose - see the module
        # docstring in middleware/rejection_lock.py (D-5 finding: after_model
        # hooks run in reverse list order).
        RejectionLockMiddleware(),
        tool_error_middleware,
    ]

    return create_agent(
        model,
        tools=AGENT_TOOLS,
        system_prompt=load_system_prompt(),
        state_schema=JobHuntState,
        context_schema=AgentContext,
        middleware=middleware,
        checkpointer=checkpointer,
        store=store,
    )
