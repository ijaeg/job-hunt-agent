"""Real-model check for the Should items (FR-12 AC1, FR-17 AC1, WP-12).

Demo mode (``FixtureSource``, invariant 6), user "alex", one thread:
(1) the demo search query, then saving one of its listings with approval,
(2) "What have I saved?", (3) the demo search query again - repeating (2)
once more with ``list_tracker`` removed from the agent's tools (mirrors
developer settings' toggle, FR-18 AC1). Records the tool-call sequence and
final answer of every turn, whether ``list_tracker`` was actually used in
each "What have I saved?" turn, and whether the ad text ever leaks into the
recorded JSON (it never does: only tool names/arguments/results and the
model's own answers are written, CLAUDE.md invariant 4).

Usage (needs OPENROUTER_API_KEY):
    uv run python scripts/wp12_should_check.py

Writes:
    eval/results/wp12_should_check.json

Related: FR-12 AC1, FR-17 AC1, FR-18 AC1, WP-12
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from job_hunt_agent import config, storage  # noqa: E402
from job_hunt_agent.agent import AGENT_TOOLS, build_agent  # noqa: E402
from job_hunt_agent.ba_client import FixtureSource  # noqa: E402
from job_hunt_agent.context import AgentContext  # noqa: E402
from job_hunt_agent.llm import build_real_model  # noqa: E402
from job_hunt_agent.models import Profile  # noqa: E402

DB_PATH = PROJECT_ROOT / "data" / "wp12_should_check.sqlite"
RESULTS_PATH = PROJECT_ROOT / "eval" / "results" / "wp12_should_check.json"
QUERY = "Find Softwareentwickler jobs in München."
THREAD_ID = "wp12-should-check"


def _tool_calls_of(messages: list[Any]) -> list[dict[str, Any]]:
    """Every tool call proposed across these messages, in order."""
    calls = []
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            calls.extend({"name": tc["name"], "args": tc["args"]} for tc in msg.tool_calls)
    return calls


def _final_answer(messages: list[Any]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return str(msg.content)
    return ""


def _first_shortlisted_ref(messages: list[Any]) -> str | None:
    for msg in messages:
        if isinstance(msg, ToolMessage) and msg.name == "search_jobs":
            payload = json.loads(str(msg.content))
            listings = (payload.get("result") or {}).get("listings", [])
            if listings:
                return str(listings[0]["referenznummer"])
    return None


def main() -> int:
    model = build_real_model(config.CHAT_MODEL, config.REASONING_EFFORT)
    conn = storage.get_connection(str(DB_PATH))
    profile = Profile.model_validate(
        yaml.safe_load((PROJECT_ROOT / "data" / "samples" / "profile_alex.yaml").read_text())
    )
    ctx = AgentContext(
        job_source=FixtureSource(), profile=profile, extraction_model=model, conn=conn
    )
    cfg = {"configurable": {"thread_id": THREAD_ID}}
    turns: list[dict[str, Any]] = []

    # --- (1a) the demo search --------------------------------------------
    agent = build_agent(model, conn)
    result = agent.invoke(
        {"messages": [HumanMessage(QUERY)], "user_id": "alex"}, config=cfg, context=ctx
    )
    seen_so_far = len(result["messages"])
    ref = _first_shortlisted_ref(result["messages"])
    turns.append(
        {
            "label": "1a_demo_search",
            "user_message": QUERY,
            "tool_calls": _tool_calls_of(result["messages"]),
            "final_answer": _final_answer(result["messages"]),
        }
    )

    # --- (1b) save one listing, with approval ----------------------------
    save_message = f"Save listing {ref} to the tracker as saved."
    result = agent.invoke({"messages": [HumanMessage(save_message)]}, config=cfg, context=ctx)
    if agent.get_state(cfg).interrupts:
        result = agent.invoke(
            Command(resume={"decisions": [{"type": "approve"}]}), config=cfg, context=ctx
        )
    new_messages = result["messages"][seen_so_far:]
    turns.append(
        {
            "label": "1b_save_with_approval",
            "user_message": save_message,
            "referenznummer": ref,
            "tool_calls": _tool_calls_of(new_messages),
            "final_answer": _final_answer(new_messages),
        }
    )
    seen_so_far = len(result["messages"])

    # --- (2) "What have I saved?" ----------------------------------------
    ask_message = "What have I saved?"
    result = agent.invoke({"messages": [HumanMessage(ask_message)]}, config=cfg, context=ctx)
    new_messages = result["messages"][seen_so_far:]
    tool_calls = _tool_calls_of(new_messages)
    turns.append(
        {
            "label": "2_what_have_i_saved",
            "user_message": ask_message,
            "tool_calls": tool_calls,
            "final_answer": _final_answer(new_messages),
            "used_list_tracker": any(c["name"] == "list_tracker" for c in tool_calls),
        }
    )
    seen_so_far = len(result["messages"])

    # --- (3) the demo query again -----------------------------------------
    result = agent.invoke({"messages": [HumanMessage(QUERY)]}, config=cfg, context=ctx)
    new_messages = result["messages"][seen_so_far:]
    turns.append(
        {
            "label": "3_demo_search_again",
            "user_message": QUERY,
            "referenznummer_saved_earlier": ref,
            "tool_calls": _tool_calls_of(new_messages),
            "final_answer": _final_answer(new_messages),
        }
    )
    seen_so_far = len(result["messages"])

    # --- (2 again) "What have I saved?", list_tracker disabled -----------
    tools_without_list_tracker = [t for t in AGENT_TOOLS if t.name != "list_tracker"]
    agent_no_list_tracker = build_agent(model, conn, tools=tools_without_list_tracker)
    result = agent_no_list_tracker.invoke(
        {"messages": [HumanMessage(ask_message)]}, config=cfg, context=ctx
    )
    new_messages = result["messages"][seen_so_far:]
    tool_calls = _tool_calls_of(new_messages)
    turns.append(
        {
            "label": "2b_what_have_i_saved_list_tracker_disabled",
            "user_message": ask_message,
            "tool_calls": tool_calls,
            "final_answer": _final_answer(new_messages),
            "used_list_tracker": any(c["name"] == "list_tracker" for c in tool_calls),
        }
    )

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(
            {
                "query": QUERY,
                "model": config.CHAT_MODEL,
                "reasoning_effort": config.REASONING_EFFORT,
                "turns": turns,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"Results: {RESULTS_PATH}")
    for turn in turns:
        print(f"- {turn['label']}: tools={[c['name'] for c in turn['tool_calls']]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
