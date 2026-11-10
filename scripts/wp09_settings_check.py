"""Real-model check for developer settings (FR-18 AC1, FR-18 AC2, D-4).

Runs the demo query "Find Softwareentwickler jobs in München." (one of D-10's
recorded searches, so the fixture set actually returns listings for it)
three times: once with each ``config.CHAT_MODEL_OPTIONS`` entry (default
reasoning effort, ``get_job_details`` enabled), and once more with the
default model but ``get_job_details`` disabled - confirming WP-09 Goal 4,
that the agent still completes the core journey without that tool
(``assess_fit`` loads details itself regardless, spec §6.1).

Records, per run: elapsed seconds, the tool-call sequence, input/output
tokens split into agent loop and extraction (FR-18 AC2), and cost with
whether it was reported by OpenRouter or estimated from :mod:`pricing`
(D-17). No ad text is written anywhere (CLAUDE.md invariant 4): only tool
names/arguments and usage numbers.

Usage (needs OPENROUTER_API_KEY):
    uv run python scripts/wp09_settings_check.py

Writes:
    eval/results/wp09_settings_check.json

Related: FR-18 AC1, FR-18 AC2, FR-19 AC3, D-4, D-17, WP-09
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from langchain_core.messages import AIMessage, HumanMessage

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from job_hunt_agent import config, storage, usage  # noqa: E402
from job_hunt_agent.agent import AGENT_TOOLS, build_agent  # noqa: E402
from job_hunt_agent.ba_client import FixtureSource  # noqa: E402
from job_hunt_agent.context import AgentContext  # noqa: E402
from job_hunt_agent.llm import build_real_model  # noqa: E402
from job_hunt_agent.models import Profile  # noqa: E402

DB_PATH = PROJECT_ROOT / "data" / "wp09_settings_check.sqlite"
RESULTS_PATH = PROJECT_ROOT / "eval" / "results" / "wp09_settings_check.json"

#: D-10's recorded München search - guarantees the fixture set returns
#: listings for it, not a possibly-empty generic match.
DEMO_QUERY = "Find Softwareentwickler jobs in München."


def _tool_sequence(messages: list[Any]) -> list[dict[str, Any]]:
    calls = []
    for msg in messages:
        if isinstance(msg, AIMessage):
            for tc in msg.tool_calls:
                calls.append({"name": tc["name"], "args": tc["args"]})
    return calls


def _usage_summary(records: list[usage.LlmUsage]) -> dict[str, Any]:
    totals = usage.aggregate(records)
    return {
        "calls": totals.total_calls,
        "prompt_tokens": totals.prompt_tokens,
        "completion_tokens": totals.completion_tokens,
        "cost_usd": round(totals.cost_usd, 6),
        "reported_calls": totals.reported_calls,
        "estimated_calls": totals.estimated_calls,
        "unpriced_calls": totals.unpriced_calls,
        "cost_label": usage.cost_label(totals),
    }


def run_scenario(
    label: str, model_name: str, get_job_details_enabled: bool, thread_id: str
) -> dict[str, Any]:
    model = build_real_model(model_name, config.REASONING_EFFORT)
    conn = storage.get_connection(str(DB_PATH))
    tools = (
        AGENT_TOOLS
        if get_job_details_enabled
        else [t for t in AGENT_TOOLS if t.name != "get_job_details"]
    )
    agent = build_agent(model, conn, tools=tools)

    profile = Profile.model_validate(
        yaml.safe_load((PROJECT_ROOT / "data" / "samples" / "profile_alex.yaml").read_text())
    )
    tracker = usage.new_turn_usage_tracker()
    ctx = AgentContext(
        job_source=FixtureSource(),
        profile=profile,
        extraction_model=model,
        conn=conn,
        usage_tracker=tracker,
    )
    cfg = {"configurable": {"thread_id": thread_id}, "callbacks": [tracker.agent_loop]}

    started = time.perf_counter()
    result = agent.invoke(
        {"messages": [HumanMessage(DEMO_QUERY)], "user_id": "alex"}, config=cfg, context=ctx
    )
    elapsed = time.perf_counter() - started

    tool_calls = _tool_sequence(result["messages"])
    final_answer = str(result["messages"][-1].content) if result["messages"] else ""

    return {
        "label": label,
        "model": model_name,
        "reasoning_effort": config.REASONING_EFFORT,
        "get_job_details_enabled": get_job_details_enabled,
        "elapsed_seconds": round(elapsed, 2),
        "tool_sequence": [c["name"] for c in tool_calls],
        "tool_calls": tool_calls,
        "shortlist_size": len(result.get("shortlist", [])),
        "agent_loop_usage": _usage_summary(tracker.agent_loop.records),
        "extraction_usage": _usage_summary(tracker.extraction.records),
        "final_answer": final_answer,
    }


def main() -> int:
    if DB_PATH.exists():
        DB_PATH.unlink()  # a fresh store every run

    scenarios = [
        run_scenario("default_model", config.CHAT_MODEL, True, "wp09-default"),
        run_scenario("secondary_model", config.CHAT_MODEL_OPTIONS[1], True, "wp09-secondary-model"),
        run_scenario("get_job_details_disabled", config.CHAT_MODEL, False, "wp09-no-details-tool"),
    ]

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(scenarios, indent=2, ensure_ascii=False), encoding="utf-8")

    for scenario in scenarios:
        print(f"--- {scenario['label']} ({scenario['model']}) ---")
        print(f"  elapsed: {scenario['elapsed_seconds']}s")
        print(f"  tools: {scenario['tool_sequence']}")
        print(f"  agent loop usage: {scenario['agent_loop_usage']}")
        print(f"  extraction usage: {scenario['extraction_usage']}")
    print(f"\nResults: {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
