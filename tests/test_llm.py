"""Tests for :mod:`job_hunt_agent.llm` (spec §5.5).

Related: spec §5.5, invariant 1
"""

from __future__ import annotations

import pytest

from job_hunt_agent import config
from job_hunt_agent.llm import build_real_model


def test_build_real_model_requires_the_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(config.OPENROUTER_API_KEY_ENV, raising=False)
    with pytest.raises(RuntimeError, match=config.OPENROUTER_API_KEY_ENV):
        build_real_model()


def test_build_real_model_wires_openrouter_with_zdr_routing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invariant 1: OpenRouter only, with zero data retention provider routing."""
    monkeypatch.setenv(config.OPENROUTER_API_KEY_ENV, "test-key")
    model = build_real_model()
    assert model.model_name == config.CHAT_MODEL
    assert str(model.openai_api_base) == config.OPENROUTER_BASE_URL
    assert model.openai_api_key is not None
    assert model.openai_api_key.get_secret_value() == "test-key"
    assert model.extra_body == {
        "reasoning": {"effort": config.REASONING_EFFORT},
        "provider": config.PROVIDER_PREFERENCES,
    }
