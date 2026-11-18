"""Headless real-model smoke run of the WP-04 Streamlit UI's demo query.

Drives the exact same ``agent.stream(..., stream_mode="updates")`` + status-
label logic ``app.py``'s ``run_turn`` uses (imported from ``app.py`` itself,
not duplicated) against the real model, in demo mode (``FixtureSource``,
D-10), for the München "Softwareentwickler" query confirmed in WP-03 to
trigger autonomous narrowing (103 results > 50). Not a pytest test - every
other test in this package mocks the model (CLAUDE.md invariant 5); this
script is the one real-model check CLAUDE.md's "Checks before hand-over" #2
requires for any change to tools, prompts, middleware or the agent.

With ``--runs N`` (N >= 1), instead runs S1 N times on a fresh thread each
(D-12, WP-05): elapsed seconds, the full tool-call sequence (deduplicated by
``tool_call`` id only, not collapsed by name, so repeated ``search_jobs``
calls - refinement, FR-03 AC3 - are visible), ``assess_fit`` extraction
seconds, listings assessed, card count and token usage per run, plus
median/mean/min/max, completion rate (runs that reached ``assess_fit``) and
refinement rate across runs, written to
``eval/results/latency_s1_wp05.json``. Reuses the same model/context/profile
setup as the default smoke run - see ``_build_context`` - rather than
duplicating it in a second script.

No ad text is written anywhere (CLAUDE.md invariant 4): only tool
names/arguments, status labels, timings and card counts are recorded.

Usage (needs OPENROUTER_API_KEY):
    uv run python scripts/ui_smoke_wp04.py
    uv run python scripts/ui_smoke_wp04.py --runs 5

Writes:
    eval/results/ui_smoke_wp04.json       (default, single run)
    eval/results/latency_s1_wp05.json     (--runs N)

Related: FR-07, FR-16 AC2, NFR-03, D-10, D-12, WP-04 "Real-model smoke run", WP-05
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from job_hunt_agent import config, storage, ui_view  # noqa: E402
from job_hunt_agent.agent import build_agent  # noqa: E402
from job_hunt_agent.ba_client import FixtureSource  # noqa: E402
from job_hunt_agent.context import AgentContext  # noqa: E402
from job_hunt_agent.llm import build_real_model  # noqa: E402
from job_hunt_agent.models import Profile  # noqa: E402

DB_PATH = PROJECT_ROOT / "data" / "ui_smoke_wp04.sqlite"
LATENCY_DB_PATH = PROJECT_ROOT / "data" / "latency_s1_wp05.sqlite"
RESULTS_PATH = PROJECT_ROOT / "eval" / "results" / "ui_smoke_wp04.json"
LATENCY_RESULTS_PATH = PROJECT_ROOT / "eval" / "results" / "latency_s1_wp05.json"
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


def _build_context(db_path: Path) -> tuple[Any, Any, AgentContext]:
    """Builds the model, agent and demo-mode context shared by both run modes."""
    model = build_real_model()
    conn = storage.get_connection(str(db_path))
    agent = build_agent(model, conn)
    profile = Profile.model_validate(
        yaml.safe_load((PROJECT_ROOT / "data" / "samples" / "profile_alex.yaml").read_text())
    )
    ctx = AgentContext(
        job_source=FixtureSource(), profile=profile, extraction_model=model, conn=conn
    )
    return model, agent, ctx


def _tool_sequence_of(messages: list[Any]) -> list[str]:
    """Full per-call tool sequence, deduplicated by ``tool_call`` id only (Addendum 1 #2).

    Not collapsed by name: a repeated ``search_jobs`` entry is a genuine second call
    (refinement, FR-03 AC3), not an echo. ``agent.invoke()`` (unlike the streaming
    ``stream_mode="updates"`` path ``app.iter_new_tool_calls`` guards against) returns
    each ``AIMessage`` once, so the id-dedup here is a defensive guarantee, not a fix
    for an observed duplicate.
    """
    seen_ids: set[str] = set()
    names: list[str] = []
    for msg in messages:
        if not isinstance(msg, AIMessage):
            continue
        for tc in msg.tool_calls:
            call_id = tc.get("id")
            if call_id is not None:
                if call_id in seen_ids:
                    continue
                seen_ids.add(call_id)
            names.append(tc["name"])
    return names


def _token_usage_of(messages: list[Any]) -> dict[str, int]:
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.usage_metadata:
            usage: dict[str, Any] = dict(msg.usage_metadata)
            for key in totals:
                totals[key] += usage.get(key, 0) or 0
    return totals


def _assess_fit_stats_of(messages: list[Any]) -> tuple[float, int]:
    """Sums ``assess_fit`` extraction seconds (from its own notes) and listings assessed."""
    extraction_seconds = 0.0
    listings_assessed = 0
    for msg in messages:
        if not (isinstance(msg, ToolMessage) and msg.name == "assess_fit"):
            continue
        content = json.loads(str(msg.content))
        for note in content.get("notes", []):
            if note.startswith("assess_fit extraction:"):
                extraction_seconds += float(note.split(":")[1].strip().rstrip("s").split("s")[0])
        listings_assessed += len((content.get("result") or {}).get("assessed") or [])
    return extraction_seconds, listings_assessed


def run_s1_once(
    agent: Any, ctx: AgentContext, thread_id: str, query: str = DEMO_QUERY
) -> dict[str, Any]:
    """Runs S1 once on a fresh thread and records the D-12 latency metrics.

    ``query`` defaults to the D-10/D-12 München wording so existing callers are
    unaffected; WP-16b's wording check passes alternative wordings (spec §3.2).
    """
    cfg = {"configurable": {"thread_id": thread_id}}
    started = time.perf_counter()
    result = agent.invoke(
        {"messages": [HumanMessage(query)], "user_id": "alex"}, config=cfg, context=ctx
    )
    elapsed = time.perf_counter() - started

    messages = result["messages"]
    tool_sequence = _tool_sequence_of(messages)
    extraction_seconds, listings_assessed = _assess_fit_stats_of(messages)

    state = agent.get_state(cfg).values
    cards = ui_view.build_cards(
        state.get("shortlist", []), state.get("summaries", {}), state.get("assessments", {})
    )
    visible, excluded = ui_view.order_cards(cards)

    return {
        "thread_id": thread_id,
        "elapsed_seconds": round(elapsed, 2),
        "within_nfr03_budget": elapsed <= S1_LATENCY_BUDGET_SECONDS,
        "tool_sequence": tool_sequence,
        "search_jobs_calls": tool_sequence.count("search_jobs"),
        "reached_assess_fit": "assess_fit" in tool_sequence,
        "assess_fit_extraction_seconds": round(extraction_seconds, 2),
        "listings_assessed": listings_assessed,
        "card_count": {"visible": len(visible), "excluded": len(excluded), "total": len(cards)},
        "token_usage": _token_usage_of(messages),
    }


def _stats(values: list[float]) -> dict[str, float]:
    return {
        "median": round(statistics.median(values), 2),
        "mean": round(statistics.mean(values), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
    }


def run_latency_measurement(n_runs: int) -> int:
    """D-12, Option 1: N fresh-thread S1 runs, median/mean/min/max elapsed (NFR-03).

    Reports the completion rate (runs that actually reached ``assess_fit``, not just
    ``search_jobs``) and the refinement rate (runs with more than one ``search_jobs``
    call, FR-03 AC3) alongside the elapsed-time summary, since a short elapsed time on
    a run that never reached ``assess_fit`` is not a latency result for the budget
    NFR-03 is actually about (Addendum 1 #3).
    """
    _, agent, ctx = _build_context(LATENCY_DB_PATH)

    runs = [run_s1_once(agent, ctx, f"latency-s1-wp05-{i}") for i in range(n_runs)]
    for i, r in enumerate(runs):
        print(f"[run {i}] {r['elapsed_seconds']}s, tools={r['tool_sequence']}")

    completed = [r for r in runs if r["reached_assess_fit"]]
    all_summary = _stats([r["elapsed_seconds"] for r in runs])
    completed_summary = _stats([r["elapsed_seconds"] for r in completed]) if completed else None
    completion_rate = len(completed) / n_runs
    refinement_rate = sum(1 for r in runs if r["search_jobs_calls"] > 1) / n_runs

    result: dict[str, Any] = {
        "demo_query": DEMO_QUERY,
        "model": config.CHAT_MODEL,
        "reasoning_effort": config.REASONING_EFFORT,
        "n_runs": n_runs,
        "s1_latency_budget_seconds": S1_LATENCY_BUDGET_SECONDS,
        "runs": runs,
        "summary": {
            "elapsed_seconds_all_runs": all_summary,
            "elapsed_seconds_completed_runs": completed_summary,
            "n_completed": len(completed),
            "completion_rate": round(completion_rate, 2),
            "refinement_rate": round(refinement_rate, 2),
            "median_within_budget": (
                completed_summary["median"] <= S1_LATENCY_BUDGET_SECONDS
                if completed_summary
                else None
            ),
            "max_within_budget": (
                completed_summary["max"] <= S1_LATENCY_BUDGET_SECONDS if completed_summary else None
            ),
        },
    }
    LATENCY_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    LATENCY_RESULTS_PATH.write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\ncompletion_rate: {completion_rate} ({len(completed)}/{n_runs} reached assess_fit)")
    print(f"refinement_rate: {refinement_rate} (runs with >1 search_jobs call)")
    print(f"elapsed_seconds (all runs): {all_summary}")
    print(f"elapsed_seconds (completed runs only): {completed_summary}")
    print(
        f"median within {S1_LATENCY_BUDGET_SECONDS}s budget: "
        f"{result['summary']['median_within_budget']}; "
        f"max within budget: {result['summary']['max_within_budget']}"
    )
    print(f"Results: {LATENCY_RESULTS_PATH}")
    return 0


def main() -> int:
    app = _load_app_module()
    model, agent, ctx = _build_context(DB_PATH)
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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runs",
        type=int,
        default=None,
        help="Run S1 this many times (fresh thread each) and measure latency (D-12, WP-05) "
        "instead of the default single smoke run.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    sys.exit(run_latency_measurement(args.runs) if args.runs else main())
