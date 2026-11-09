"""Real-model demo-mode check: S1 then S2, for FR-08 AC1/AC2 (D-11, WP-05).

S1 ("Find Softwareentwickler jobs in München.", D-10's recorded München
search) builds the shortlist; S2 ("Why is #3 only partial?") must be answered
from the already-computed ``assessments`` in state, with **no new tool
call**, citing the rubric dimension and the evidence (FR-08 AC1, AC2) - which
only works end to end once ``FitAssessment.matches``/``gaps`` carry the
German quote and English translation (D-11, this work package).

No ad text is written anywhere (CLAUDE.md invariant 4): only tool
names/arguments, the resulting card categories and the final assistant
messages are recorded.

Usage (needs OPENROUTER_API_KEY):
    uv run python scripts/s1_s2_check.py

Writes:
    eval/results/wp05_s1_s2.json

Related: FR-05 AC4, FR-07 AC1, FR-08 AC1-AC2, D-10, D-11, WP-05
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml
from langchain_core.messages import AIMessage, HumanMessage

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from job_hunt_agent import storage, ui_view  # noqa: E402
from job_hunt_agent.agent import build_agent  # noqa: E402
from job_hunt_agent.ba_client import FixtureSource  # noqa: E402
from job_hunt_agent.context import AgentContext  # noqa: E402
from job_hunt_agent.llm import build_real_model  # noqa: E402
from job_hunt_agent.models import Profile  # noqa: E402

DB_PATH = PROJECT_ROOT / "data" / "s1_s2_check.sqlite"
RESULTS_PATH = PROJECT_ROOT / "eval" / "results" / "wp05_s1_s2.json"

#: D-10's recorded München search (103 results > 50, triggers refinement).
S1_MESSAGE = "Find Softwareentwickler jobs in München."
S2_MESSAGE = "Why is #3 only partial?"


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
    model = build_real_model()
    conn = storage.get_connection(str(DB_PATH))
    agent = build_agent(model, conn)

    profile = Profile.model_validate(
        yaml.safe_load((PROJECT_ROOT / "data" / "samples" / "profile_alex.yaml").read_text())
    )
    ctx = AgentContext(
        job_source=FixtureSource(), profile=profile, extraction_model=model, conn=conn
    )
    cfg = {"configurable": {"thread_id": "s1-s2-check"}}

    s1_result = agent.invoke(
        {"messages": [HumanMessage(S1_MESSAGE)], "user_id": "alex"}, config=cfg, context=ctx
    )
    s1_tool_calls = _tool_calls_of(s1_result["messages"])
    n_after_s1 = len(s1_result["messages"])

    state = agent.get_state(cfg).values
    cards = ui_view.build_cards(
        state.get("shortlist", []), state.get("summaries", {}), state.get("assessments", {})
    )
    visible, excluded = ui_view.order_cards(cards)
    card_categories = [c.category for c in visible] + [c.category for c in excluded]

    s2_result = agent.invoke(
        {"messages": [HumanMessage(S2_MESSAGE)], "user_id": "alex"}, config=cfg, context=ctx
    )
    s2_new_messages = s2_result["messages"][n_after_s1:]
    s2_tool_calls = _tool_calls_of(s2_new_messages)
    s2_answer = _final_text_of(s2_new_messages)

    result = {
        "s1_message": S1_MESSAGE,
        "s1_tool_sequence": [c["name"] for c in s1_tool_calls],
        "s1_card_categories": card_categories,
        "s1_card_count": len(cards),
        "s2_message": S2_MESSAGE,
        "s2_new_tool_calls": s2_tool_calls,
        "s2_answered_without_new_tool_call": s2_tool_calls == [],
        "s2_answer": s2_answer,
    }
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"S1 tools: {result['s1_tool_sequence']}")
    print(f"S1 card categories: {card_categories}")
    print(f"S2 new tool calls: {s2_tool_calls} (none expected)")
    print(f"S2 answer:\n{s2_answer}")
    print(f"\nResults: {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
