"""Token usage and cost bookkeeping for the chat model (FR-18 AC2).

Two calls need their usage captured: the main ReAct loop's model calls (run
by ``create_agent``'s model node, in the caller's own thread) and
``assess_fit``'s structured-extraction calls (run in a
``ThreadPoolExecutor``, spec §6.1, ``tools/assess.py``). A plain
``get_usage_metadata_callback()`` context manager does not reach the
extraction calls: Python's ``ThreadPoolExecutor`` does not copy the
caller's ``contextvars`` into worker threads, and LangChain's ambient usage
callback is contextvar-based. The fix used here instead is
:class:`UsageCallbackHandler`, passed *explicitly* as
``config={"callbacks": [handler]}`` to every model call (the main loop's
``agent.stream(...)`` and each extraction's ``.invoke(...)``) - an explicit
``RunnableConfig`` entry reaches a ``ThreadPoolExecutor`` worker just as well
as the calling thread, since it is plain data passed as an argument, not
ambient context. Confirmed with a real OpenRouter call during WP-09's
"Check first": see ``eval/results/wp09_settings_check.json``.

Related: FR-18 AC2, D-17, spec §6.1
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from langchain_core.callbacks.base import BaseCallbackHandler

from job_hunt_agent import pricing


@dataclass(frozen=True, slots=True)
class LlmUsage:
    """Token counts and cost of a single LLM call.

    Attributes:
        model: Model identifier the call was sent to.
        prompt_tokens: Tokens in the prompt.
        completion_tokens: Tokens in the completion, including reasoning
            tokens (D-17).
        reasoning_tokens: Reasoning tokens, counted inside
            ``completion_tokens``.
        cost_usd: Cost in USD as reported by OpenRouter, or None when it was
            not in the response (D-17's estimate then applies instead).

    Related: FR-18 AC2, D-17
    """

    model: str
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    cost_usd: float | None


class UsageCallbackHandler(BaseCallbackHandler):
    """Collects one :class:`LlmUsage` per LLM call it observes.

    Thread-safe (``tools/assess.py`` shares one instance across the
    extraction ``ThreadPoolExecutor``'s workers, each passing it explicitly
    in their own call's ``config`` - see the module docstring).

    Related: FR-18 AC2
    """

    def __init__(self) -> None:
        super().__init__()
        self.records: list[LlmUsage] = []
        self._lock = threading.Lock()

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        """Reads token counts and the reported cost off each generation's message."""
        for generations in response.generations:
            for generation in generations:
                message = getattr(generation, "message", None)
                if message is None:
                    continue
                usage = getattr(message, "usage_metadata", None) or {}
                response_metadata = getattr(message, "response_metadata", None) or {}
                token_usage = response_metadata.get("token_usage") or {}
                output_details = usage.get("output_token_details") or {}
                cost = token_usage.get("cost")
                record = LlmUsage(
                    model=response_metadata.get("model_name", ""),
                    prompt_tokens=int(usage.get("input_tokens", 0)),
                    completion_tokens=int(usage.get("output_tokens", 0)),
                    reasoning_tokens=int(output_details.get("reasoning", 0)),
                    cost_usd=float(cost) if isinstance(cost, int | float) else None,
                )
                with self._lock:
                    self.records.append(record)


@dataclass
class TurnUsageTracker:
    """Pairs the two handlers one agent turn needs, split by call site.

    Attributes:
        agent_loop: Attached to the main ReAct loop's ``agent.stream(...)``
            call (``app.py``).
        extraction: Attached to every structured-extraction call inside one
            ``assess_fit`` invocation (``tools/assess.py``), via
            ``AgentContext.usage_tracker``.

    Related: FR-18 AC2
    """

    agent_loop: UsageCallbackHandler = field(default_factory=UsageCallbackHandler)
    extraction: UsageCallbackHandler = field(default_factory=UsageCallbackHandler)

    def all_records(self) -> list[LlmUsage]:
        """Every record from both call sites, agent loop first."""
        return [*self.agent_loop.records, *self.extraction.records]


def new_turn_usage_tracker() -> TurnUsageTracker:
    """Builds a fresh tracker for one agent turn (never reused across turns)."""
    return TurnUsageTracker()


@dataclass
class UsageTotals:
    """Aggregated tokens and cost over a list of :class:`LlmUsage` records.

    Attributes:
        prompt_tokens: Sum of prompt tokens.
        completion_tokens: Sum of completion tokens (incl. reasoning, D-17).
        cost_usd: Sum of cost, reported where OpenRouter provided it,
            estimated from :mod:`pricing` otherwise.
        reported_calls: Calls whose cost OpenRouter reported.
        estimated_calls: Calls priced from the token-based estimate instead.
        unpriced_calls: Calls with neither a reported nor an estimated cost.
        total_calls: Total number of calls aggregated.

    Related: FR-18 AC2, D-17
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    reported_calls: int = 0
    estimated_calls: int = 0
    unpriced_calls: int = 0
    total_calls: int = 0


def aggregate(records: list[LlmUsage], client: Any = None) -> UsageTotals:
    """Sums token counts and cost over a list of usage records.

    Args:
        records: Usage records to sum, e.g. ``tracker.all_records()``.
        client: Passed on to :func:`job_hunt_agent.pricing.estimate_cost_usd`
            for records without a reported cost (tests only).

    Returns:
        The aggregated totals; ``cost_usd`` mixes reported and estimated
        cost, which :func:`cost_label` reports honestly.

    Related: FR-18 AC2, D-17
    """
    totals = UsageTotals()
    for record in records:
        totals.total_calls += 1
        totals.prompt_tokens += record.prompt_tokens
        totals.completion_tokens += record.completion_tokens
        if record.cost_usd is not None:
            totals.cost_usd += record.cost_usd
            totals.reported_calls += 1
            continue
        estimate = pricing.estimate_cost_usd(
            record.model, record.prompt_tokens, record.completion_tokens, client
        )
        if estimate is None:
            totals.unpriced_calls += 1
        else:
            totals.cost_usd += estimate
            totals.estimated_calls += 1
    return totals


def cost_label(totals: UsageTotals) -> str:
    """The cost as shown in the UI: "cost", "estimated cost" or "cost unavailable".

    "cost" is used when every priced call's cost was reported by OpenRouter;
    "estimated cost" when at least one priced call needed the token-based
    estimate instead (D-17); "cost unavailable" when no call could be priced
    at all.

    Related: FR-18 AC2, D-17
    """
    if totals.reported_calls == 0 and totals.estimated_calls == 0:
        return "cost unavailable"
    label = "estimated cost" if totals.estimated_calls else "cost"
    amount = f"${totals.cost_usd:.4f} {label}"
    if totals.unpriced_calls:
        amount += f" ({totals.unpriced_calls} call(s) unpriced)"
    return amount


def usage_caption(totals: UsageTotals) -> str:
    """One-line summary for the UI: tokens, split by agent loop vs. extraction, and cost.

    Related: FR-18 AC2
    """
    if totals.total_calls == 0:
        return "no model calls yet"
    return (
        f"{totals.prompt_tokens:,} in / {totals.completion_tokens:,} out tokens "
        f"· {cost_label(totals)}"
    )
