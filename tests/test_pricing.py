"""Tests for :mod:`job_hunt_agent.pricing` (D-17, FR-18 AC2).

Uses ``httpx.MockTransport`` - never calls the real OpenRouter models
endpoint (CLAUDE.md invariant 5).

Related: FR-18 AC2, D-17
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from job_hunt_agent import pricing

MODELS_PAYLOAD = {
    "data": [
        {
            "id": "openai/gpt-5-mini",
            "pricing": {"prompt": "0.00000025", "completion": "0.000002"},
        },
        {
            "id": "anthropic/claude-haiku-4.5",
            "pricing": {"prompt": "0.000001", "completion": "0.000005"},
        },
    ]
}


def _client_with(handler: Any) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def _clear_price_cache() -> Iterator[None]:
    pricing.clear_cache()
    yield
    pricing.clear_cache()


def test_fetch_model_prices_ok() -> None:
    client = _client_with(lambda request: httpx.Response(200, json=MODELS_PAYLOAD))
    prices = pricing.fetch_model_prices(client)
    assert prices["openai/gpt-5-mini"].prompt_usd_per_token == 0.00000025
    assert prices["openai/gpt-5-mini"].completion_usd_per_token == 0.000002
    assert "anthropic/claude-haiku-4.5" in prices


def test_fetch_model_prices_skips_one_malformed_entry() -> None:
    payload = {
        "data": [
            {"id": "broken/model", "pricing": {"prompt": "not-a-number", "completion": "0.1"}},
            MODELS_PAYLOAD["data"][0],
        ]
    }
    client = _client_with(lambda request: httpx.Response(200, json=payload))
    prices = pricing.fetch_model_prices(client)
    assert "broken/model" not in prices
    assert "openai/gpt-5-mini" in prices


def test_fetch_model_prices_timeout_returns_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    client = _client_with(handler)
    assert pricing.fetch_model_prices(client) == {}


def test_fetch_model_prices_http_error_returns_empty() -> None:
    client = _client_with(lambda request: httpx.Response(503))
    assert pricing.fetch_model_prices(client) == {}


def test_get_prices_does_not_cache_a_failure() -> None:
    """D-17: a failed fetch is never cached, so a later call can retry."""
    calls: list[int] = []

    def failing(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503)

    ok_client = _client_with(lambda request: httpx.Response(200, json=MODELS_PAYLOAD))

    assert pricing.get_prices(_client_with(failing)) == {}
    assert len(calls) == 1

    prices = pricing.get_prices(ok_client)
    assert "openai/gpt-5-mini" in prices


def test_get_prices_caches_a_success() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json=MODELS_PAYLOAD)

    client = _client_with(handler)
    pricing.get_prices(client)
    pricing.get_prices(client)
    assert len(calls) == 1


def test_get_price_unknown_model_is_none() -> None:
    client = _client_with(lambda request: httpx.Response(200, json=MODELS_PAYLOAD))
    assert pricing.get_price("unknown/model", client) is None


def test_estimate_cost_usd() -> None:
    client = _client_with(lambda request: httpx.Response(200, json=MODELS_PAYLOAD))
    cost = pricing.estimate_cost_usd("openai/gpt-5-mini", 1000, 500, client)
    assert cost == pytest.approx(1000 * 0.00000025 + 500 * 0.000002)


def test_estimate_cost_usd_unknown_model_is_none() -> None:
    client = _client_with(lambda request: httpx.Response(200, json=MODELS_PAYLOAD))
    assert pricing.estimate_cost_usd("unknown/model", 1000, 500, client) is None
