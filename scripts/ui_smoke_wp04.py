"""Headless real-model smoke run of the WP-04 Streamlit UI's demo query.

Drives the exact same ``agent.stream(..., stream_mode="updates")`` + status-
label logic ``app.py``'s ``run_turn`` uses (imported from ``app.py`` itself,
not duplicated) against the real model, in demo mode (``FixtureSource``,
D-10), for the München "Softwareentwickler" query confirmed in WP-03 to
trigger autonomous narrowing (103 results > 50). Not a pytest test - every
other test in this package mocks the model (CLAUDE.md invariant 5); this
script is the one real-model check CLAUDE.md's "Checks before hand-over" #2
requires for any change to tools, prompts, middleware or the agent.

No ad text is written anywhere (CLAUDE.md invariant 4): only tool
names/arguments, status labels, timings and card counts are recorded.

Usage (needs OPENROUTER_API_KEY):
    uv run python scripts/ui_smoke_wp04.py

Writes:
    eval/results/ui_smoke_wp04.json

Related: FR-07, FR-16 AC2, NFR-03, D-10, WP-04 "Real-model smoke run"
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from langchain_core.messages import HumanMessage

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from job_hunt_agent import storage, ui_view  # noqa: E402
from job_hunt_agent.agent import build_agent  # noqa: E402
from job_hunt_agent.ba_client import FixtureSource  # noqa: E402
from job_hunt_agent.context import AgentContext  # noqa: E402
from job_hunt_agent.llm import build_real_model  # noqa: E402
from job_hunt_agent.models import Profile  # noqa: E402

DB_PATH = PROJECT_ROOT / "data" / "ui_smoke_wp04.sqlite"
RESULTS_PATH = PROJECT_ROOT / "eval" / "results" / "ui_smoke_wp04.json"
S1_LATENCY_BUDGET_SECONDS = 60.0

#: The recorded München search (data/samples/fixtures/recorded_searches.json):
#: "Softwareentwickler" / München, total 103 - confirmed in D-10 follow-up 2
#: to trigger autonomous narrowing (>50) end-to-end to assess_fit.
DEMO_QUERY = "Find Softwareentwickler jobs in München."


def _load_app_module() -> Any:
    """Loads app.py by path to reuse its status-label logic without duplicating it."""
    spec = importlib.util.spec_from_file_location("app_under_smoke_test", PROJECT_ROOT / "app.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    app = _load_app_module()
    model = build_real_model()
    conn = storage.get_connection(str(DB_PATH))
    agent = build_agent(model, conn)

    profile = Profile.model_validate(
        yaml.safe_load((PROJECT_ROOT / "data" / "samples" / "profile_alex.yaml").read_text())
    )
    ctx = AgentContext(
        job_source=FixtureSource(), profile=profile, extraction_model=model, conn=conn
    )
    cfg = {"configurable": {"thread_id": "ui-smoke-wp04"}}

    tool_calls: list[dict[str, Any]] = []
    status_labels: list[str] = []
    counts: dict[str, int] = {}
    seen_tool_call_ids: set[str] = set()

    started = time.perf_counter()
    for step in agent.stream(
        {"messages": [HumanMessage(DEMO_QUERY)], "user_id": "alex"},
        config=cfg,
        context=ctx,
        stream_mode="updates",
    ):
        for tool_call in app.iter_new_tool_calls(step, seen_tool_call_ids):
            tool_calls.append({"name": tool_call["name"], "args": tool_call["args"]})
            label = app._status_label(tool_call["name"], tool_call["args"], counts)
            if label:
                status_labels.append(label)
    elapsed = time.perf_counter() - started

    state = agent.get_state(cfg).values
    cards = ui_view.build_cards(
        state.get("shortlist", []), state.get("summaries", {}), state.get("assessments", {})
    )
    visible, excluded = ui_view.order_cards(cards)

    result = {
        "demo_query": DEMO_QUERY,
        "model": model.model_name,
        "elapsed_seconds": round(elapsed, 2),
        "within_nfr03_budget": elapsed <= S1_LATENCY_BUDGET_SECONDS,
        "tool_sequence": [c["name"] for c in tool_calls],
        "tool_calls": tool_calls,
        "status_labels_shown": status_labels,
        "card_count": {"visible": len(visible), "excluded": len(excluded), "total": len(cards)},
        "card_categories": [c.category for c in visible] + [c.category for c in excluded],
    }
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[ui_smoke_wp04] {elapsed:.1f}s, tools={result['tool_sequence']}")
    print(f"card_count={result['card_count']}, status_labels={status_labels}")
    if not result["within_nfr03_budget"]:
        print(f"WARNING: {elapsed:.1f}s exceeds the {S1_LATENCY_BUDGET_SECONDS}s NFR-03 budget.")
    print(f"Results: {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
