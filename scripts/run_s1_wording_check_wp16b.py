"""S1 wording check for the WP-16b demo (spec §3.2, D-10, D-12).

Runs three candidate wordings of the demo script's S1 request, 5 times each on a
fresh thread, in demo mode (``FixtureSource``) against the real model (config
defaults: ``openai/gpt-5-mini``, reasoning effort ``low``), and records whether
each run refines the search after the 103-result München match (FR-03 AC1/AC3)
and reaches ``assess_fit`` with at least one listing assessed. This chooses how
S1 is demoed for the review; it does not change the agent, a tool or a prompt
(CLAUDE.md invariant 6: evaluation runs on the fixture set, so results are
reproducible).

Reuses ``scripts/ui_smoke_wp04.py``'s per-run measurement
(``run_s1_once``/``_build_context``) with the query parametrised instead of fixed,
rather than duplicating that logic.

No ad text is written anywhere (CLAUDE.md invariant 4): only tool names/arguments,
timings and counts are recorded.

Usage (needs OPENROUTER_API_KEY):
    uv run python scripts/run_s1_wording_check_wp16b.py

Writes:
    eval/results/s1_wording_wp16b.json

Related: spec §3.2, FR-03 AC1/AC3, NFR-03, D-10, D-12, WP-16b
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from ui_smoke_wp04 import _build_context, run_s1_once  # noqa: E402

from job_hunt_agent import config  # noqa: E402

DB_PATH = PROJECT_ROOT / "data" / "s1_wording_wp16b.sqlite"
RESULTS_PATH = PROJECT_ROOT / "eval" / "results" / "s1_wording_wp16b.json"
N_RUNS = 5

WORDINGS: dict[str, str] = {
    "W1": "Find Softwareentwickler jobs in München.",
    "W2": "Find Softwareentwickler jobs in München, posted in the last 4 weeks.",
    "W3": "Find Softwareentwickler jobs in München from the last 4 weeks, no temp agencies.",
}


def _stats(values: list[float]) -> dict[str, float]:
    return {
        "median": round(statistics.median(values), 2),
        "mean": round(statistics.mean(values), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
    }


def main() -> int:
    _, agent, ctx = _build_context(DB_PATH)

    results: dict[str, Any] = {
        "model": config.CHAT_MODEL,
        "reasoning_effort": config.REASONING_EFFORT,
        "n_runs_per_wording": N_RUNS,
        "wordings": WORDINGS,
        "runs": {},
        "summary": {},
    }

    for label, query in WORDINGS.items():
        runs = []
        for i in range(N_RUNS):
            thread_id = f"s1-wording-wp16b-{label}-{i}"
            record = run_s1_once(agent, ctx, thread_id, query=query)
            refined = record["search_jobs_calls"] > 1
            complete = refined and record["listings_assessed"] > 0
            record["refined"] = refined
            record["complete"] = complete
            runs.append(record)
            print(
                f"[{label} run {i}] {record['elapsed_seconds']}s, "
                f"refined={refined}, listings_assessed={record['listings_assessed']}, "
                f"complete={complete}"
            )
        results["runs"][label] = runs

        complete_runs = [r for r in runs if r["complete"]]
        elapsed_all = _stats([r["elapsed_seconds"] for r in runs])
        results["summary"][label] = {
            "query": query,
            "complete_of_5": len(complete_runs),
            "refined_of_5": sum(1 for r in runs if r["refined"]),
            "shortlist_shown_of_5": sum(1 for r in runs if r["listings_assessed"] > 0),
            "elapsed_seconds_all_runs": elapsed_all,
            "elapsed_seconds_median": elapsed_all["median"],
            "elapsed_seconds_max": elapsed_all["max"],
        }

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n--- Summary ---")
    for label, summary in results["summary"].items():
        print(
            f"{label} ({summary['query']!r}): "
            f"complete {summary['complete_of_5']}/5, "
            f"median {summary['elapsed_seconds_median']}s, "
            f"max {summary['elapsed_seconds_max']}s"
        )
    print(f"\nResults: {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
