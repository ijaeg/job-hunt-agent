"""Real-model demo-mode check: a memory saved in one thread applies in a new one (FR-15 AC2, AC4).

Thread 1 asks to exclude "bayoonet AG" - the employer of referenznummer
12117-YF-48852-YF-S, one of D-10's recorded München search results - and
approves the resulting ``remember`` call. Thread 2 is a *new* thread id on
the same DB, so ``LoadMemoryContextMiddleware`` (this work package) has
nothing from thread 1's own message history to go on; it must come from
the store. It runs D-10's recorded München search and records whether that
employer's listing carries "excluded by you" and whether the agent's own
reply mentions the stored exclusion.

No ad text is written anywhere (CLAUDE.md invariant 4): only tool
names/arguments, the resulting card categories/exclusion reasons and the
final assistant messages are recorded.

Usage (needs OPENROUTER_API_KEY):
    uv run python scripts/wp07_memory_check.py

Writes:
    eval/results/wp07_memory_check.json

Related: FR-15 AC2, FR-15 AC4, D-6, D-10, WP-07
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from job_hunt_agent import storage, ui_view  # noqa: E402
from job_hunt_agent.agent import build_agent  # noqa: E402
from job_hunt_agent.ba_client import FixtureSource  # noqa: E402
from job_hunt_agent.context import AgentContext  # noqa: E402
from job_hunt_agent.llm import build_real_model  # noqa: E402
from job_hunt_agent.models import Profile  # noqa: E402

DB_PATH = PROJECT_ROOT / "data" / "wp07_memory_check.sqlite"
RESULTS_PATH = PROJECT_ROOT / "eval" / "results" / "wp07_memory_check.json"

#: Employer of 12117-YF-48852-YF-S in D-10's recorded München search results
#: (data/samples/fixtures/listings.json, data/samples/fixtures/recorded_searches.json).
EXCLUDED_EMPLOYER = "bayoonet AG"
EXCLUDED_REF = "12117-YF-48852-YF-S"

THREAD_1_MESSAGE = f"Never show me jobs from {EXCLUDED_EMPLOYER} again."
THREAD_2_MESSAGE = "Find Softwareentwickler jobs in München."


def _tool_calls_of(messages: list[Any]) -> list[dict[str, Any]]:
    calls = []
    for msg in messages:
        if isinstance(msg, AIMessage):
            for tc in msg.tool_calls:
                calls.append({"name": tc["name"], "args": tc["args"]})
    return calls


def _final_text_of(messages: list[Any]) -> str:
    if not messages:
        return ""
    last = messages[-1]
    return str(last.content) if isinstance(last, AIMessage) else ""


def main() -> int:
    if DB_PATH.exists():
        DB_PATH.unlink()  # a fresh store every run - no leftover memories from a prior check

    model = build_real_model()
    conn = storage.get_connection(str(DB_PATH))
    agent = build_agent(model, conn)

    profile = Profile.model_validate(
        yaml.safe_load((PROJECT_ROOT / "data" / "samples" / "profile_alex.yaml").read_text())
    )
    ctx = AgentContext(
        job_source=FixtureSource(), profile=profile, extraction_model=model, conn=conn
    )

    # --- Thread 1: save the exclusion, with approval ------------------------
    cfg1 = {"configurable": {"thread_id": "wp07-thread-1"}}
    t1_result = agent.invoke(
        {"messages": [HumanMessage(THREAD_1_MESSAGE)], "user_id": "alex"}, config=cfg1, context=ctx
    )
    t1_interrupted = bool(agent.get_state(cfg1).interrupts)
    t1_tool_calls = _tool_calls_of(t1_result["messages"])
    if t1_interrupted:
        t1_result = agent.invoke(
            Command(resume={"decisions": [{"type": "approve"}]}), config=cfg1, context=ctx
        )
    t1_final_answer = _final_text_of(t1_result["messages"])
    stored_memories = [
        {**m, "created_at": m["created_at"].isoformat()}
        for m in storage.list_memories(conn, "alex")
    ]

    # --- Thread 2: a new thread id, no shared message history ---------------
    cfg2 = {"configurable": {"thread_id": "wp07-thread-2"}}
    t2_result = agent.invoke(
        {"messages": [HumanMessage(THREAD_2_MESSAGE)], "user_id": "alex"}, config=cfg2, context=ctx
    )
    t2_messages = t2_result["messages"]
    t2_tool_calls = _tool_calls_of(t2_messages)
    t2_final_answer = _final_text_of(t2_messages)
    memory_context_present = any(getattr(m, "name", None) == "memory_context" for m in t2_messages)

    state = agent.get_state(cfg2).values
    cards = ui_view.build_cards(
        state.get("shortlist", []), state.get("summaries", {}), state.get("assessments", {})
    )
    excluded_card = next((c for c in cards if c.referenznummer == EXCLUDED_REF), None)

    result = {
        "excluded_employer": EXCLUDED_EMPLOYER,
        "excluded_referenznummer": EXCLUDED_REF,
        "thread_1_message": THREAD_1_MESSAGE,
        "thread_1_tool_calls": t1_tool_calls,
        "thread_1_interrupted_for_approval": t1_interrupted,
        "thread_1_final_answer": t1_final_answer,
        "stored_memories_after_thread_1": stored_memories,
        "thread_2_message": THREAD_2_MESSAGE,
        "thread_2_tool_sequence": [c["name"] for c in t2_tool_calls],
        "thread_2_memory_context_message_injected": memory_context_present,
        "excluded_listing_was_assessed": excluded_card is not None,
        "excluded_listing_exclusion_reasons": excluded_card.exclusion_reasons
        if excluded_card
        else None,
        "excluded_listing_marked_excluded_by_you": bool(
            excluded_card and any("excluded by you" in r for r in excluded_card.exclusion_reasons)
        ),
        "thread_2_final_answer": t2_final_answer,
        "thread_2_answer_mentions_exclusion": EXCLUDED_EMPLOYER.lower() in t2_final_answer.lower(),
    }
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Thread 1 tool calls: {[c['name'] for c in t1_tool_calls]}")
    print(f"Stored memories after thread 1: {stored_memories}")
    print(f"Thread 2 tool sequence: {result['thread_2_tool_sequence']}")
    print(f"Memory context message injected in thread 2: {memory_context_present}")
    print(f"Excluded listing exclusion reasons: {result['excluded_listing_exclusion_reasons']}")
    print(f"Thread 2 answer mentions the exclusion: {result['thread_2_answer_mentions_exclusion']}")
    print(f"\nResults: {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
