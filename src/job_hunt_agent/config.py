"""Central configuration: model, provider routing, limits and timeouts.

Every value named by the spec is defined here once, so that switching the
model, a timeout or a limit needs no code change elsewhere (FR-20 AC2).
Secrets are never stored here: only the *name* of the environment variable
that holds the OpenRouter key is a constant (invariant 4, CLAUDE.md).

Related: FR-02, FR-18, FR-20, NFR-01, spec §5.5, §8
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

#: Repository root; all other paths are derived from it.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

# The gitignored .env is loaded before any setting below is read, so that
# values in .env (e.g. CHAT_MODEL) take effect; an exported variable always
# wins (NFR-01).
load_dotenv(PROJECT_ROOT / ".env", override=False)

# ---------------------------------------------------------------------------
# OpenRouter and model (spec §5.5, FR-18, FR-20)
# ---------------------------------------------------------------------------

#: OpenAI-compatible base URL the chat model is pointed at (NFR-01).
OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

#: Name of the environment variable holding the API key; never the key itself.
OPENROUTER_API_KEY_ENV: str = "OPENROUTER_API_KEY"

#: Default chat model, overridable by the ``CHAT_MODEL`` env var (spec §5.5).
CHAT_MODEL: str = os.getenv("CHAT_MODEL", "openai/gpt-5-mini")

#: Models offered in the developer settings (FR-18 AC1); the default comes
#: first. Extend with ``CHAT_MODEL_OPTIONS`` (comma-separated OpenRouter IDs);
#: no code change needed. The second model is confirmed in spike D-4.
CHAT_MODEL_OPTIONS: tuple[str, ...] = tuple(
    dict.fromkeys(
        [
            CHAT_MODEL,
            *(
                m.strip()
                for m in os.getenv("CHAT_MODEL_OPTIONS", "anthropic/claude-haiku-4.5").split(",")
                if m.strip()
            ),
        ]
    )
)

#: Default reasoning effort passed to the chat model (spec §5.5).
REASONING_EFFORT: str = os.getenv("REASONING_EFFORT", "low")

#: Reasoning efforts offered in the developer settings (FR-18 AC1).
REASONING_EFFORT_OPTIONS: tuple[str, ...] = ("minimal", "low", "medium", "high")

#: OpenRouter provider routing: no training on our data, zero data retention
#: (spec §5.5, invariant 1) - profile data and ad texts are sent to the model.
PROVIDER_PREFERENCES: dict[str, object] = {"data_collection": "deny", "zdr": True}

# ---------------------------------------------------------------------------
# BA job board API (D-1, spikes/NOTES.md)
# ---------------------------------------------------------------------------

#: Base URL of the BA job board JSON API (D-1).
BA_BASE_URL: str = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"

#: Public client ID of the official job search web app, sent as the
#: ``X-API-Key`` header; not a secret (D-1).
BA_API_KEY: str = "jobboerse-jobsuche"

# ---------------------------------------------------------------------------
# Timeouts and retries per external call (spec §8)
# ---------------------------------------------------------------------------

#: Request timeout for BA search and details calls, in seconds (spec §8).
BA_TIMEOUT_SECONDS: int = 15

#: Retries on a BA timeout, HTTP 429 or 5xx (spec §8).
BA_MAX_RETRIES: int = 1

#: Delay before the BA retry, in seconds (spec §8).
BA_RETRY_DELAY_SECONDS: float = 2.0

#: Request timeout for OpenRouter chat calls, in seconds (spec §8).
OPENROUTER_TIMEOUT_SECONDS: int = 60

#: Retries on HTTP 429 or 5xx, with exponential backoff (spec §8).
OPENROUTER_MAX_RETRIES: int = 2

#: Base delay of the exponential backoff, in seconds (spec §8).
OPENROUTER_RETRY_BACKOFF_SECONDS: float = 1.0

#: Request timeout for one structured-extraction call in ``assess_fit``, in
#: seconds (spec §8).
ASSESS_FIT_TIMEOUT_SECONDS: int = 60

#: Retries on invalid JSON from a structured-extraction call (spec §8).
ASSESS_FIT_JSON_RETRY_ATTEMPTS: int = 1

# ---------------------------------------------------------------------------
# Agent limits (FR-20)
# ---------------------------------------------------------------------------

#: Maximum model calls per user message (FR-20 AC1).
MAX_MODEL_CALLS_PER_MESSAGE: int = 10

#: Maximum ``search_jobs`` calls per user message (FR-20 AC1, FR-03 AC2).
MAX_SEARCH_CALLS_PER_MESSAGE: int = 3

#: Maximum user message length in characters (FR-01 AC2).
MAX_MESSAGE_LENGTH: int = 1000

# ---------------------------------------------------------------------------
# Storage (spec §5, D-5, D-6)
# ---------------------------------------------------------------------------

#: One shared SQLite file for the checkpointer, the memory store and the
#: tracker/profile tables (D-5, D-6); overridable so tests use a temp file.
DB_PATH: str = os.getenv("DB_PATH", str(PROJECT_ROOT / "data" / "job_hunt_agent.sqlite"))

#: Maximum listings per ``assess_fit`` call (FR-05 AC6).
MAX_LISTINGS_PER_ASSESS_FIT_CALL: int = 8

#: Maximum concurrent structured-extraction calls within one ``assess_fit``
#: call (FR-05 AC1).
MAX_CONCURRENT_EXTRACTIONS: int = 4
