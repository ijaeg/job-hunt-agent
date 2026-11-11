"""LangSmith tracing: off by default, built per run (spec §9.5, Hard 2, D-18).

Two-step build - :func:`build_client` once, :func:`build_tracer` per run - so a
caller that runs many turns (``app.py``) can cache the client (one eager network
call, confirmed in WP-10's "Check first": ``Client(...)`` does a ``GET /info``
immediately) instead of paying that cost on every turn; the per-run tracer itself
is a local object with no network call of its own. Every failure here - a missing
key, an unreachable LangSmith, a bad response - is swallowed and yields ``None``,
never an exception: tracing is best-effort and must never affect the rest of the
app (spec §8).

Related: FR-18 AC1, spec §8, §9.5, D-18
"""

from __future__ import annotations

import os
from typing import Any

from langchain_core.tracers.langchain import LangChainTracer
from langsmith import Client

from job_hunt_agent import config


def langsmith_key_present() -> bool:
    """Whether ``LANGSMITH_API_KEY`` is set.

    Read fresh on every call, never cached or stored anywhere else - gates the
    developer-settings toggle and every client build below without ever
    writing the key itself to a file, a log or the UI (CLAUDE.md invariant 4).

    Related: FR-18 AC1
    """
    return bool(os.getenv(config.LANGSMITH_API_KEY_ENV, "").strip())


def build_client() -> Any | None:
    """Builds one LangSmith client, or ``None`` if the key is missing or the
    client itself fails to build.

    Cheap to call repeatedly by contract (every failure is caught here), but
    not free (one network call) - callers that run many turns on one key
    (``ui_shared.get_langsmith_client``) cache the result for the life of the
    process instead of rebuilding it per turn.

    Related: spec §8, §9.5, D-18
    """
    api_key = os.getenv(config.LANGSMITH_API_KEY_ENV, "").strip()
    if not api_key:
        return None
    try:
        return Client(
            api_url=config.LANGSMITH_ENDPOINT,
            api_key=api_key,
            timeout_ms=config.LANGSMITH_CLIENT_TIMEOUT_SECONDS * 1000,
        )
    except Exception:  # noqa: BLE001 - a tracing failure never affects the app (spec §8)
        return None


def build_tracer(
    client: Any | None,
    *,
    demo_mode: bool,
    thread_id: str,
    scenario: str | None = None,
) -> Any | None:
    """Builds one ``LangChainTracer`` for a single run, or ``None``.

    Args:
        client: A pre-built LangSmith client (:func:`build_client`); ``None``
            (tracing off, no key, or the client failed to build) always
            yields ``None`` here too.
        demo_mode: Tags the run ``demo`` or ``live`` (spec §9.5).
        thread_id: Recorded as run metadata, so a trace can be matched back
            to the Streamlit thread (or script run) it came from.
        scenario: Recorded as an extra tag when the caller knows which demo
            scenario (S1, S3, ...) this run belongs to (spec §9.5); omitted
            for ordinary app usage, where it is not known in advance.

    Related: FR-18 AC1, spec §9.5, D-18
    """
    if client is None:
        return None
    try:
        tags = ["demo" if demo_mode else "live"]
        if scenario:
            tags.append(scenario)
        return LangChainTracer(
            project_name=config.LANGSMITH_PROJECT,
            client=client,
            tags=tags,
            metadata={"thread_id": thread_id},
        )
    except Exception:  # noqa: BLE001 - a tracing failure never affects the app (spec §8)
        return None
