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


def build_real_model() -> Any:
    """Builds the ``ChatOpenAI`` client pointed at OpenRouter with ZDR routing.

    Raises:
        RuntimeError: If ``config.OPENROUTER_API_KEY_ENV`` is not set.

    Related: spec §5.5, invariant 1
    """
    from langchain_openai import ChatOpenAI

    api_key = os.getenv(config.OPENROUTER_API_KEY_ENV, "").strip()
    if not api_key:
        raise RuntimeError(f"{config.OPENROUTER_API_KEY_ENV} is not set.")
    return ChatOpenAI(
        model=config.CHAT_MODEL,
        base_url=config.OPENROUTER_BASE_URL,
        api_key=SecretStr(api_key),
        timeout=config.OPENROUTER_TIMEOUT_SECONDS,
        max_retries=0,
        extra_body={
            "reasoning": {"effort": config.REASONING_EFFORT},
            "provider": config.PROVIDER_PREFERENCES,
        },
    )
