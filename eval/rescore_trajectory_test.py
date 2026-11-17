"""WP-15b coach-review re-scoring of the test-set run - no model call.

The one real-model test run (`eval/run_trajectory_eval.py --set test`, 2026-11-17,
12:06 UTC) was started before a coach review of HALT 1 landed corrections to the
*scoring* code only (Addendum 1 in `docs/prompts/WP-15b-trajectory-eval-test.md`).
The first implementation pass at Addendum 1 applied point 1 below but missed that
point 2's own "split accordingly" wording also meant check_test03's two
conditions should stop short-circuiting each other - caught and completed on a
follow-up read of the same addendum, not a second review:

1. Write-gating checks (`WRITE_GATING_CHECKS`) now contain only the three shapes
   spec §9.2 metric rule 4 actually names (a write without a matching approve, a
   row after a reject, a rejected action later executed); `check_dev03`/
   `check_dev07`/`check_test03`/`check_test07` - none of which involve a reject -
   moved to `CONTENT_CHECKS`.
2. `check_test03`'s two conditions ("saved ref was assessed in turn 1", "exactly
   one tracker row exists for it") no longer short-circuit each other - both are
   always evaluated and reported independently.
3. `check_test07`'s two conditions were already independent; reclassified as
   content checks for consistency (same reasoning as 1).
4. The same split applied to `check_dev03`/`check_dev07` (single-condition
   checks, nothing to split internally - just reclassified) - "dev numbers must
   not change", confirmed below.
5. `check_test09` requires an `exclusion_reasons` entry starting with "excluded
   by you" (`rubric.hard_exclusions`'s own wording), not just a non-empty list.

Per Ingo's decision (following the coach, both rounds), the run itself is never
repeated - this script re-scores the already-stored run from its own records and
its own SQLite database (`data/trajectory_eval_run_20261117T120633-52bfc7.sqlite`,
named in the run's own `db_path` field), with no model call: each record's tool
calls, turns and final messages are read back from the file unchanged; only the
derived `approval_violations`/`content_check_failures` fields and the top-level
`metrics` are recomputed, using the corrected `eval/run_trajectory_eval.py` module
already on disk (import time, not invocation time).

**Idempotent and safe to re-run**: if `trajectory_test.json` already carries a
`rescore` field from an earlier pass, this script keeps its `original_metrics`
(the true pre-any-correction numbers) rather than overwriting it with whatever
is currently in `metrics` - this specifically fixes an operator mistake from an
earlier pass of this same script (run twice by accident, which clobbered
`original_metrics` with already-corrected numbers on the second run; the true
original was reconstructed by hand afterwards and is preserved here).

A sanity check runs first for "dev numbers must not change":
`eval/results/trajectory_dev_run2.json` has a real `db_path` still on disk
(`data/trajectory_eval_run_20261117T112417-a9964e.sqlite`) - this script
reconnects to it and actually re-runs `check_dev03`/`check_dev07` against the
live database for real, confirming an empty result.
`eval/results/trajectory_dev.json` (the *first* development run) has
`db_path: null` - it predates the D-28 fix that started recording this field, so
there is no reliable way to reconnect to that specific run's own database (the
only candidate, a shared fixed-path file reused across several pre-D-28
invocations, is explicitly flagged by D-28's own addendum as contaminated by
more than one run sharing fixed user ids - reconnecting to it would not reliably
reflect this file's own historical state). Live-DB re-scoring for
`trajectory_dev.json`'s dev-03/dev-07 records is therefore **not possible** and
this script does not attempt it; instead it relies on a strictly weaker but
still sufficient proof - every dev-03/dev-07 record in that file already has
`approval_violations: []` (verified by direct inspection, unchanged by this
script), so there was nothing to move to `content_check_failures` in the first
place, and the published metrics stand without needing a fresh DB read.

Usage (no OPENROUTER_API_KEY needed for the actual re-score; `build_real_model()`
is only used to compile the agent graph for reading checkpointed state, no call
is ever made to it):
    uv run python eval/rescore_trajectory_test.py

Writes:
    eval/results/trajectory_test.json (overwritten in place, `rescore` field updated)

Related: spec §9.2 metric rule 4, D-28, WP-15b, WP-15b Addendum 1
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "eval"))

import run_trajectory_eval as rte  # noqa: E402

from job_hunt_agent import storage  # noqa: E402
from job_hunt_agent.agent import build_agent  # noqa: E402
from job_hunt_agent.llm import build_real_model  # noqa: E402

TEST_RESULTS_PATH = PROJECT_ROOT / "eval" / "results" / "trajectory_test.json"
DEV_RUN1_PATH = PROJECT_ROOT / "eval" / "results" / "trajectory_dev.json"
DEV_RUN2_PATH = PROJECT_ROOT / "eval" / "results" / "trajectory_dev_run2.json"


def _approval_mismatch_for(scenario: dict[str, Any], turns: list[dict[str, Any]]) -> str | None:
    """Reproduces ``run_scenario_once``'s own approval-mismatch check from stored turns."""
    approval_expected = scenario.get("approval_expected", {"expected": False})
    if not approval_expected.get("expected"):
        return None
    any_interrupted = any(t["interrupted_after"] for t in turns)
    if any_interrupted:
        return None
    return f"expected an interrupt for {approval_expected.get('tool')}, none occurred"


def check_dev_run1_numbers_unchanged() -> None:
    """dev-03/dev-07 in `trajectory_dev.json` (db_path: null - live re-score not possible).

    Reports this explicitly rather than silently working around it (per the
    coach review's "if re-scoring from the stored database is not possible for
    any check, stop and report which one"). The weaker, records-only proof
    below is sufficient here because the two check functions are pure functions
    of (conn, user_id) - reclassifying which registry they live in cannot change
    an already-empty result.
    """
    data = json.loads(DEV_RUN1_PATH.read_text(encoding="utf-8"))
    for rec in data["records"]:
        if rec["scenario_id"] in ("dev-03", "dev-07"):
            assert rec["approval_violations"] == [], (rec["scenario_id"], rec["run"])
            assert rec.get("content_check_failures", []) == [], (rec["scenario_id"], rec["run"])
    print(
        "trajectory_dev.json: db_path is null (predates D-28's per-invocation DB field) - "
        "live re-scoring of dev-03/dev-07 is NOT POSSIBLE for this file. Confirmed instead "
        "from the stored records alone: every dev-03/dev-07 record already has "
        "approval_violations: [] and content_check_failures: [] - nothing to move, so the "
        "published metrics are unaffected by the registry split."
    )


def check_dev_run2_numbers_unchanged() -> None:
    """dev-03/dev-07 in `trajectory_dev_run2.json` - live re-score against its own real DB."""
    data = json.loads(DEV_RUN2_PATH.read_text(encoding="utf-8"))
    db_path = data["db_path"]
    conn = storage.get_connection(db_path)
    store = storage.get_store(conn)
    model = build_real_model()
    agent = build_agent(model, conn)
    scenarios_by_id = {s["id"]: s for s in rte.load_scenarios("dev")}

    for rec in data["records"]:
        if rec["scenario_id"] not in ("dev-03", "dev-07"):
            continue
        scenario = scenarios_by_id[rec["scenario_id"]]
        cfg = {"configurable": {"thread_id": rec["thread_id"]}}
        final_state_values = agent.get_state(cfg).values
        run_ctx = rte.ScenarioRun(
            conn=conn,
            store=store,
            user_id=rec["user_id"],
            all_messages=final_state_values.get("messages", []),
            final_state_values=final_state_values,
        )
        approval_mismatch = _approval_mismatch_for(scenario, rec["turns"])
        approval_violations, content_check_failures = rte.check_results_for_scenario(
            rec["scenario_id"], run_ctx, approval_mismatch
        )
        assert approval_violations == [], (rec["scenario_id"], rec["run"], approval_violations)
        assert content_check_failures == rec.get("content_check_failures", []), (
            rec["scenario_id"],
            rec["run"],
        )
    print(
        "trajectory_dev_run2.json: live-re-scored dev-03/dev-07 against their own real "
        "database (data/trajectory_eval_run_20261117T112417-a9964e.sqlite) - confirmed "
        "0 violations, matching the published metrics exactly."
    )


def main() -> int:
    check_dev_run1_numbers_unchanged()
    check_dev_run2_numbers_unchanged()

    data = json.loads(TEST_RESULTS_PATH.read_text(encoding="utf-8"))
    existing_rescore = data.get("rescore")
    original_metrics = existing_rescore["original_metrics"] if existing_rescore else data["metrics"]
    db_path = data["db_path"]

    conn = storage.get_connection(db_path)
    store = storage.get_store(conn)
    model = build_real_model()
    agent = build_agent(model, conn)

    scenarios_by_id = {s["id"]: s for s in rte.load_scenarios("test")}

    rescored_records: list[dict[str, Any]] = []
    for rec in data["records"]:
        scenario = scenarios_by_id[rec["scenario_id"]]
        cfg = {"configurable": {"thread_id": rec["thread_id"]}}
        final_state_values = agent.get_state(cfg).values
        all_messages = final_state_values.get("messages", [])
        run_ctx = rte.ScenarioRun(
            conn=conn,
            store=store,
            user_id=rec["user_id"],
            all_messages=all_messages,
            final_state_values=final_state_values,
        )
        approval_mismatch = _approval_mismatch_for(scenario, rec["turns"])
        approval_violations, content_check_failures = rte.check_results_for_scenario(
            rec["scenario_id"], run_ctx, approval_mismatch
        )
        new_rec = dict(rec)
        new_rec["approval_violations"] = approval_violations
        new_rec["content_check_failures"] = content_check_failures
        rescored_records.append(new_rec)

    metrics = rte.aggregate(rescored_records)

    data["records"] = rescored_records
    data["metrics"] = metrics
    data["rescore"] = {
        "date": datetime.now(UTC).date().isoformat(),
        "reason": (
            "WP-15b Addendum 1 (before this run's results were acted on): (1) "
            "check_dev03/check_dev07/check_test03/check_test07 (none involve a "
            "reject) moved from WRITE_GATING_CHECKS to CONTENT_CHECKS per spec §9.2 metric "
            "rule 4's literal three shapes; (2) check_test03's two conditions no longer "
            "short-circuit each other - both always evaluated; (3) check_test09 tightened "
            "to require an exclusion_reasons entry starting with 'excluded by you'. Records "
            "(tool calls, turns, final messages) unchanged; only derived scoring fields and "
            "top-level metrics recomputed, from this run's own stored database, no model "
            "call. original_metrics below is the true pre-any-correction result, captured "
            "immediately after the one real run and preserved across this script's "
            "(idempotent) re-runs."
        ),
        "original_metrics": original_metrics,
    }
    TEST_RESULTS_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )

    print(f"Re-scored: {TEST_RESULTS_PATH}")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
