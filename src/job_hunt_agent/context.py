"""Per-run agent context: the job source and profile every tool call sees.

Passed to ``create_agent(..., context_schema=AgentContext)`` and supplied at
invoke time (``agent.invoke(input, context=AgentContext(...))``); tools
read it via ``runtime.context`` (``ToolRuntime``, langgraph). Unlike
:class:`job_hunt_agent.state.JobHuntState`, this is immutable for the life
of one run - swapping the job source (live vs. demo mode, FR-19 AC1) or the
profile (FR-01 AC4: "the profile is part of the agent's context") never
needs a state update, just a different context object on the next
``invoke``.

Related: FR-01 AC4, FR-19 AC1, spec §5
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from job_hunt_agent.ba_client import JobSource
from job_hunt_agent.models import Profile


@dataclass
class AgentContext:
    """Dependencies tools need but that never live in persisted thread state.

    Attributes:
        job_source: ``BAClient`` (live) or ``FixtureSource`` (demo mode,
            FR-19 AC1) - tools call ``.search()``/``.get_details()``
            without knowing which.
        profile: The selected user's profile (FR-01 AC4, FR-14).
        extraction_model: Chat model ``assess_fit`` calls
            ``.with_structured_output(JobRequirements)`` on (FR-05 AC1).
            Typed ``Any`` (not ``BaseChatModel``) on purpose: tests inject a
            small fake object with just a ``with_structured_output`` method,
            never the real API (CLAUDE.md invariant 5), and importing
            ``BaseChatModel`` here breaks every tool's Pydantic args-schema
            build (``ToolRuntime``'s generic resolves this dataclass's field
            types eagerly, before ``langchain_core`` is guaranteed loaded).
        conn: Shared SQLite connection (``storage.get_connection``) for
            ``save_to_tracker`` (FR-09). The long-term memory store is
            reached separately, via ``ToolRuntime.store`` (D-6) - set at
            ``create_agent(..., store=...)`` time, not here.
    """

    job_source: JobSource
    profile: Profile
    extraction_model: Any
    conn: sqlite3.Connection
