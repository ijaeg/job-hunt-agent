"""Model prices from the OpenRouter models endpoint, cached for one session.

Adapted from Ingo's Sprint 2 project (D-17): the endpoint needs no API key.
OpenRouter already reports the cost of a call most of the time (see
``usage.py``), but when it does not, the app prices the token counts itself
from this table. If the endpoint is unavailable the app keeps working and
shows "cost unavailable" instead of a number; a failed fetch is never
cached, so a later call can try again.

Uses ``httpx`` (this project's HTTP client, spec §8), not ``urllib`` - the
same pattern as :class:`job_hunt_agent.ba_client.BAClient`: pass a pre-built
``httpx.Client`` (e.g. with a ``MockTransport``) for tests; without one, a
short-lived real client is built and closed again.

Related: FR-18 AC2, D-17
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from job_hunt_agent import config


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """Price of one model, in USD per token.

    Attributes:
        model: Model identifier as used by OpenRouter.
        prompt_usd_per_token: Price of one prompt token.
        completion_usd_per_token: Price of one completion token.

    Related: FR-18 AC2, D-17
    """

    model: str
    prompt_usd_per_token: float
    completion_usd_per_token: float


_cache: dict[str, ModelPrice] | None = None


def fetch_model_prices(client: httpx.Client | None = None) -> dict[str, ModelPrice]:
    """Fetch the price table from the OpenRouter models endpoint.

    Args:
        client: Pre-built ``httpx.Client`` for tests; a short-lived real
            client is built and closed again when omitted.

    Returns:
        A mapping from model identifier to its price; empty if the endpoint is
        unavailable or the answer cannot be read, in which case the UI shows
        "cost unavailable".

    Related: FR-18 AC2, D-17
    """
    owns_client = client is None
    http_client = client or httpx.Client(timeout=config.OPENROUTER_PRICES_TIMEOUT_SECONDS)
    try:
        response = http_client.get(config.OPENROUTER_MODELS_URL)
        response.raise_for_status()
        payload: Any = json.loads(response.content)
        prices: dict[str, ModelPrice] = {}
        for entry in payload.get("data", []):
            pricing = entry.get("pricing") or {}
            try:
                prices[entry["id"]] = ModelPrice(
                    model=entry["id"],
                    prompt_usd_per_token=float(pricing["prompt"]),
                    completion_usd_per_token=float(pricing["completion"]),
                )
            except (KeyError, TypeError, ValueError):
                continue  # one malformed entry does not spoil the table
        return prices
    except Exception:  # noqa: BLE001 - network, HTTP or JSON error: the app keeps working
        return {}
    finally:
        if owns_client:
            http_client.close()


def get_prices(client: httpx.Client | None = None) -> dict[str, ModelPrice]:
    """Return the price table, fetching it only on the first call.

    An empty table (endpoint unavailable) is not cached, so a later call can
    try again; failures are never cached (D-17).

    Related: FR-18 AC2, D-17
    """
    global _cache
    if not _cache:
        _cache = fetch_model_prices(client)
    return _cache


def clear_cache() -> None:
    """Forget the cached prices (used by tests)."""
    global _cache
    _cache = None


def get_price(model: str, client: httpx.Client | None = None) -> ModelPrice | None:
    """Look up the cached price of one model.

    Args:
        model: Model identifier.
        client: Passed on to :func:`get_prices`.

    Returns:
        The price, or None if the model is unknown or prices are unavailable.

    Related: FR-18 AC2
    """
    return get_prices(client).get(model)


def estimate_cost_usd(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    client: httpx.Client | None = None,
) -> float | None:
    """Price one call from token counts.

    Args:
        model: Model identifier.
        prompt_tokens: Tokens in the prompt.
        completion_tokens: Tokens in the completion, including reasoning tokens
            (D-17).
        client: Passed on to :func:`get_prices`.

    Returns:
        The cost in USD, or None when the price is unknown.

    Related: FR-18 AC2, D-17
    """
    price = get_price(model, client)
    if price is None:
        return None
    return (
        prompt_tokens * price.prompt_usd_per_token
        + completion_tokens * price.completion_usd_per_token
    )
