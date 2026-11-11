"""Real-model check for parallel tool calls (FR-20 AC1, FR-20 AC2, D-19, WP-11).

Runs the demo query "Find Softwareentwickler jobs in München." (one of D-10's
recorded searches, so the fixture set actually returns listings for it) 5
times, each on a fresh thread, against demo mode (``FixtureSource``,
invariant 6). For each run, records whether the turn completed (reached
``assess_fit``), how many ``search_jobs`` calls the model proposed vs. how
many actually ran, whether any single step proposed more than one tool call
(parallel tool calling) and for which tool(s), and any error. This is a
real-model run only to observe whether the model actually produces parallel
tool calls in practice and whether the new state reducers/``SearchCallLimitMiddleware``
(state.py, middleware/limits.py) hold up outside the scripted-model tests -
it is not itself a regression test (``tests/test_middleware_limits.py``,
``tests/test_tools_search.py``/``test_tools_details.py``/``test_tools_assess.py``
already force parallel calls deterministically).

No ad text is written anywhere (CLAUDE.md invariant 4): only tool
names/arguments and step-level counts.

Usage (needs OPENROUTER_API_KEY):
    uv run python scripts/wp11_parallel_check.py

Writes:
    eval/results/wp11_parallel_check.json

Related: FR-20 AC1, FR-20 AC2, spec §5.3, §5.4, D-19, WP-11
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

from job_hunt_agent import config, storage  # noqa: E402
from job_hunt_agent.agent import build_agent  # noqa: E402
from job_hunt_agent.ba_client import FixtureSource  # noqa: E402
from job_hunt_agent.context import AgentContext  # noqa: E402
from job_hunt_agent.llm import build_real_model  # noqa: E402
from job_hunt_agent.models import Profile  # noqa: E402

DB_PATH = PROJECT_ROOT / "data" / "wp11_parallel_check.sqlite"
RESULTS_PATH = PROJECT_ROOT / "eval" / "results" / "wp11_parallel_check.json"
QUERY = "Find Softwareentwickler jobs in München."
RUNS = 5


def _steps_of(messages: list[Any]) -> list[list[dict[str, Any]]]:
    """One entry per model step: the tool calls that ``AIMessage`` proposed."""
    steps = []
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            steps.append([{"name": tc["name"], "args": tc["args"]} for tc in msg.tool_calls])
    return steps


def run_once(run_index: int) -> dict[str, Any]:
    model = build_real_model(config.CHAT_MODEL, config.REASONING_EFFORT)
    conn = storage.get_connection(str(DB_PATH))
    agent = build_agent(model, conn)
    profile = Profile.model_validate(
        yaml.safe_load((PROJECT_ROOT / "data" / "samples" / "profile_alex.yaml").read_text())
    )
    ctx = AgentContext(
        job_source=FixtureSource(), profile=profile, extraction_model=model, conn=conn
    )
    cfg = {"configurable": {"thread_id": f"wp11-parallel-check-{run_index}"}}

    record: dict[str, Any] = {
        "run": run_index,
        "error": None,
        "completed_assess_fit": False,
        "search_jobs_proposed": 0,
        "search_jobs_executed": 0,
        "parallel_steps": [],
        "steps": [],
    }
    try:
        result = agent.invoke(
            {"messages": [HumanMessage(QUERY)], "user_id": "alex"}, config=cfg, context=ctx
        )
    except Exception as exc:  # noqa: BLE001 - recorded, not raised, so one failure doesn't stop the run
        record["error"] = f"{type(exc).__name__}: {exc}"
        return record

    steps = _steps_of(result["messages"])
    record["steps"] = steps
    record["completed_assess_fit"] = any(
        call["name"] == "assess_fit" for step in steps for call in step
    )
    record["search_jobs_proposed"] = sum(
        1 for step in steps for call in step if call["name"] == "search_jobs"
    )
    record["search_jobs_executed"] = sum(
        1
        for msg in result["messages"]
        if msg.__class__.__name__ == "ToolMessage" and msg.name == "search_jobs"
    )
    record["final_shortlist_size"] = len(result.get("shortlist", []))
    for i, step in enumerate(steps):
        if len(step) > 1:
            record["parallel_steps"].append({"step": i, "tools": [c["name"] for c in step]})

    print(
        f"[run {run_index}] completed={record['completed_assess_fit']} "
        f"search_jobs proposed={record['search_jobs_proposed']} "
        f"executed={record['search_jobs_executed']} "
        f"parallel_steps={len(record['parallel_steps'])}"
    )
    return record


def main() -> int:
    records = [run_once(i) for i in range(1, RUNS + 1)]

    errors = [r for r in records if r["error"]]
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(
            {
                "query": QUERY,
                "model": config.CHAT_MODEL,
                "reasoning_effort": config.REASONING_EFFORT,
                "runs": records,
                "summary": {
                    "total_runs": len(records),
                    "completed_runs": sum(1 for r in records if r["completed_assess_fit"]),
                    "runs_with_parallel_steps": sum(1 for r in records if r["parallel_steps"]),
                    "error_runs": len(errors),
                },
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nResults: {RESULTS_PATH}")
    if errors:
        print(f"{len(errors)} run(s) errored - see the results file.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
