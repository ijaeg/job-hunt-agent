"""Builds the real OpenRouter chat model (spec §5.5).

Shared by ``scripts/run_core_journey.py`` and ``app.py`` so the OpenRouter
wiring (ZDR provider routing, invariant 1) exists in exactly one place.

Related: spec §5.5, NFR-01, invariant 1
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import SecretStr

from job_hunt_agent import config


def build_real_model(model: str | None = None, reasoning_effort: str | None = None) -> Any:
    """Builds the ``ChatOpenAI`` client pointed at OpenRouter with ZDR routing.

    Args:
        model: Model identifier; defaults to :data:`config.CHAT_MODEL`.
            Developer settings (FR-18 AC1) pass one of
            :data:`config.CHAT_MODEL_OPTIONS` instead.
        reasoning_effort: Reasoning effort; defaults to
            :data:`config.REASONING_EFFORT`. Confirmed in WP-09's "Check
            first" to work the same way (``extra_body["reasoning"]["effort"]``)
            for every model in ``CHAT_MODEL_OPTIONS``, including
            ``anthropic/claude-haiku-4.5`` (D-4).

    Raises:
        RuntimeError: If ``config.OPENROUTER_API_KEY_ENV`` is not set.

    Related: spec §5.5, FR-18 AC1, invariant 1, D-4
    """
    from langchain_openai import ChatOpenAI

    api_key = os.getenv(config.OPENROUTER_API_KEY_ENV, "").strip()
    if not api_key:
        raise RuntimeError(f"{config.OPENROUTER_API_KEY_ENV} is not set.")
    return ChatOpenAI(
        model=model or config.CHAT_MODEL,
        base_url=config.OPENROUTER_BASE_URL,
        api_key=SecretStr(api_key),
        timeout=config.OPENROUTER_TIMEOUT_SECONDS,
        max_retries=0,
        extra_body={
            "reasoning": {"effort": reasoning_effort or config.REASONING_EFFORT},
            "provider": config.PROVIDER_PREFERENCES,
        },
    )
