"""Tests for :mod:`job_hunt_agent.config`.

Related: FR-18, FR-20, NFR-01, spec §5.5, §8
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Any

import dotenv
import pytest

from job_hunt_agent import config


def test_module_imports() -> None:
    """The configuration module imports and exposes its constants."""
    assert config.BA_BASE_URL == "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
    assert config.MAX_MODEL_CALLS_PER_MESSAGE == 10


def test_spec_5_5_default_model_and_reasoning_effort() -> None:
    """The default model and reasoning effort match spec §5.5."""
    assert config.CHAT_MODEL == "openai/gpt-5-mini"
    assert config.REASONING_EFFORT == "low"


def test_spec_5_5_provider_routing_is_zero_data_retention() -> None:
    """Provider routing denies training and enforces zero data retention."""
    assert config.PROVIDER_PREFERENCES == {"data_collection": "deny", "zdr": True}


def test_chat_model_overridable_by_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """``CHAT_MODEL`` in the environment replaces the default model (FR-20 AC2)."""
    monkeypatch.setenv("CHAT_MODEL", "test/model")
    try:
        assert importlib.reload(config).CHAT_MODEL == "test/model"
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_fr18_chat_model_options_default_includes_second_model() -> None:
    """The developer-settings model list defaults to gpt-5-mini plus haiku-4.5 (D-4)."""
    assert config.CHAT_MODEL_OPTIONS[0] == config.CHAT_MODEL
    assert "anthropic/claude-haiku-4.5" in config.CHAT_MODEL_OPTIONS


def test_fr18_chat_model_options_overridable_and_deduplicated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``CHAT_MODEL_OPTIONS`` is comma-separated and never lists the default twice."""
    monkeypatch.setenv("CHAT_MODEL_OPTIONS", f"{config.CHAT_MODEL}, some/other-model")
    try:
        reloaded = importlib.reload(config)
        assert reloaded.CHAT_MODEL_OPTIONS == (config.CHAT_MODEL, "some/other-model")
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_nfr01_dotenv_is_loaded_before_settings_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """A value from the project's .env file reaches config before settings are read (NFR-01)."""
    seen: dict[str, Any] = {}

    def fake_load_dotenv(path: Path, override: bool = False) -> bool:
        seen["path"], seen["override"] = path, override
        os.environ["CHAT_MODEL"] = "from/dotenv"  # what the real .env would do
        return True

    monkeypatch.delenv("CHAT_MODEL", raising=False)
    monkeypatch.setattr(dotenv, "load_dotenv", fake_load_dotenv)
    try:
        reloaded = importlib.reload(config)
        assert reloaded.CHAT_MODEL == "from/dotenv"
        assert seen == {"path": reloaded.PROJECT_ROOT / ".env", "override": False}
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_api_key_is_not_a_configuration_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the name of the key variable is a constant, never the key itself (invariant 4)."""
    secret = "sk-or-v1-test-not-a-real-key"
    monkeypatch.setenv(config.OPENROUTER_API_KEY_ENV, secret)
    try:
        reloaded = importlib.reload(config)
        assert reloaded.OPENROUTER_API_KEY_ENV == "OPENROUTER_API_KEY"
        assert all(secret not in repr(value) for value in vars(reloaded).values())
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_spec_8_timeouts_and_retries_per_external_call() -> None:
    """Timeouts and retries match the table in spec §8."""
    assert config.BA_TIMEOUT_SECONDS == 15
    assert config.BA_MAX_RETRIES == 1
    assert config.BA_RETRY_DELAY_SECONDS == 2.0
    assert config.OPENROUTER_TIMEOUT_SECONDS == 60
    assert config.OPENROUTER_MAX_RETRIES == 2
    assert config.ASSESS_FIT_TIMEOUT_SECONDS == 60
    assert config.ASSESS_FIT_JSON_RETRY_ATTEMPTS == 1


def test_fr20_ac1_agent_limits() -> None:
    """Model-call and search-call limits match FR-20 AC1."""
    assert config.MAX_MODEL_CALLS_PER_MESSAGE == 10
    assert config.MAX_SEARCH_CALLS_PER_MESSAGE == 3
