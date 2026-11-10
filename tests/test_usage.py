"""Tests for :mod:`job_hunt_agent.usage` (FR-18 AC2, D-17).

``UsageCallbackHandler.on_llm_end`` is exercised with hand-built stand-ins
for the ``LLMResult``/``ChatGeneration`` shape LangChain passes it, not a
real model call (CLAUDE.md invariant 5) - confirmed against the real shape
during WP-09's "Check first" (see ``eval/results/wp09_settings_check.json``).

Related: FR-18 AC2, D-17
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from job_hunt_agent import pricing, usage


class _FakeGeneration:
    def __init__(self, message: Any) -> None:
        self.message = message


class _FakeLLMResult:
    def __init__(self, *messages: Any) -> None:
        self.generations = [[_FakeGeneration(m)] for m in messages]


class _FakeMessage:
    def __init__(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        reasoning_tokens: int = 0,
        cost: float | None = None,
    ) -> None:
        self.usage_metadata = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "output_token_details": {"reasoning": reasoning_tokens},
        }
        self.response_metadata = {
            "model_name": model,
            "token_usage": {} if cost is None else {"cost": cost},
        }


@pytest.fixture(autouse=True)
def _clear_price_cache() -> Any:
    pricing.clear_cache()
    yield
    pricing.clear_cache()


# ---------------------------------------------------------------------------
# UsageCallbackHandler
# ---------------------------------------------------------------------------


def test_on_llm_end_records_tokens_and_reported_cost() -> None:
    handler = usage.UsageCallbackHandler()
    message = _FakeMessage("openai/gpt-5-mini", 50, 20, reasoning_tokens=5, cost=0.001)
    handler.on_llm_end(_FakeLLMResult(message))
    assert handler.records == [
        usage.LlmUsage(
            model="openai/gpt-5-mini",
            prompt_tokens=50,
            completion_tokens=20,
            reasoning_tokens=5,
            cost_usd=0.001,
        )
    ]


def test_on_llm_end_cost_none_when_not_in_token_usage() -> None:
    handler = usage.UsageCallbackHandler()
    message = _FakeMessage("openai/gpt-5-mini", 10, 5)
    handler.on_llm_end(_FakeLLMResult(message))
    assert handler.records[0].cost_usd is None


def test_on_llm_end_accumulates_across_calls() -> None:
    handler = usage.UsageCallbackHandler()
    handler.on_llm_end(_FakeLLMResult(_FakeMessage("m", 1, 1)))
    handler.on_llm_end(_FakeLLMResult(_FakeMessage("m", 2, 2)))
    assert len(handler.records) == 2


def test_on_llm_end_skips_a_generation_without_a_message() -> None:
    handler = usage.UsageCallbackHandler()
    result = _FakeLLMResult()
    result.generations = [[_FakeGeneration(None)]]
    handler.on_llm_end(result)
    assert handler.records == []


# ---------------------------------------------------------------------------
# TurnUsageTracker
# ---------------------------------------------------------------------------


def test_turn_usage_tracker_all_records_agent_loop_first() -> None:
    tracker = usage.new_turn_usage_tracker()
    tracker.extraction.on_llm_end(_FakeLLMResult(_FakeMessage("m", 1, 1)))
    tracker.agent_loop.on_llm_end(_FakeLLMResult(_FakeMessage("m", 2, 2)))
    records = tracker.all_records()
    assert len(records) == 2
    assert records[0].prompt_tokens == 2  # agent_loop first
    assert records[1].prompt_tokens == 1


def test_new_turn_usage_tracker_returns_independent_instances() -> None:
    a = usage.new_turn_usage_tracker()
    b = usage.new_turn_usage_tracker()
    a.agent_loop.on_llm_end(_FakeLLMResult(_FakeMessage("m", 1, 1)))
    assert b.agent_loop.records == []


# ---------------------------------------------------------------------------
# aggregate / cost_label / usage_caption
# ---------------------------------------------------------------------------


def _usage(
    model: str = "openai/gpt-5-mini",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
    reasoning_tokens: int = 0,
    cost_usd: float | None = None,
) -> usage.LlmUsage:
    return usage.LlmUsage(model, prompt_tokens, completion_tokens, reasoning_tokens, cost_usd)


def test_aggregate_sums_tokens_and_prefers_reported_cost() -> None:
    records = [_usage(prompt_tokens=10, completion_tokens=5, cost_usd=0.01), _usage(cost_usd=0.02)]
    totals = usage.aggregate(records)
    assert totals.prompt_tokens == 20
    assert totals.completion_tokens == 10
    assert totals.cost_usd == pytest.approx(0.03)
    assert totals.reported_calls == 2
    assert totals.estimated_calls == 0
    assert totals.unpriced_calls == 0


def test_aggregate_estimates_when_cost_is_missing() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "openai/gpt-5-mini",
                            "pricing": {"prompt": "0.001", "completion": "0.002"},
                        }
                    ]
                },
            )
        )
    )
    totals = usage.aggregate([_usage(prompt_tokens=100, completion_tokens=50)], client)
    assert totals.estimated_calls == 1
    assert totals.reported_calls == 0
    assert totals.cost_usd == pytest.approx(100 * 0.001 + 50 * 0.002)


def test_aggregate_unpriced_when_price_table_unavailable() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503)))
    totals = usage.aggregate([_usage()], client)
    assert totals.unpriced_calls == 1
    assert totals.cost_usd == 0.0


def test_cost_label_cost_unavailable_when_nothing_priced() -> None:
    totals = usage.UsageTotals(total_calls=1, unpriced_calls=1)
    assert usage.cost_label(totals) == "cost unavailable"


def test_cost_label_cost_when_all_reported() -> None:
    totals = usage.UsageTotals(cost_usd=0.0123, reported_calls=2, total_calls=2)
    assert usage.cost_label(totals) == "$0.0123 cost"


def test_cost_label_estimated_cost_when_any_call_is_estimated() -> None:
    totals = usage.UsageTotals(cost_usd=0.02, reported_calls=1, estimated_calls=1, total_calls=2)
    assert usage.cost_label(totals) == "$0.0200 estimated cost"


def test_cost_label_notes_unpriced_calls_alongside_a_known_total() -> None:
    totals = usage.UsageTotals(cost_usd=0.01, reported_calls=1, unpriced_calls=1, total_calls=2)
    assert "1 call(s) unpriced" in usage.cost_label(totals)


def test_usage_caption_no_calls() -> None:
    assert usage.usage_caption(usage.UsageTotals()) == "no model calls yet"


def test_usage_caption_includes_tokens_and_cost() -> None:
    totals = usage.UsageTotals(
        prompt_tokens=1234, completion_tokens=567, cost_usd=0.01, reported_calls=1, total_calls=1
    )
    caption = usage.usage_caption(totals)
    assert "1,234" in caption
    assert "567" in caption
    assert "cost" in caption
