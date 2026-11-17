"""Explanation-consistency measurement runner (D-13 Option 2, spec FR-08, WP-15c).

Runs the 3 threads of ``eval/explanation_set.yaml`` twice each against the real
model in demo mode (``FixtureSource``, invariant 6), on a fresh thread, a fresh
synthetic user id and a fresh SQLite file per *invocation* of this script (same
``make_run_token``/``make_db_path``/``make_user_id`` pattern as
``eval/run_trajectory_eval.py``, D-28 - a scenario id/run index alone repeats
every invocation, so without this a later invocation's model could see an
earlier invocation's own long-term memory). Each thread opens with one message
assessing 3 named listings, then asks 4 neutral follow-up questions, scored with
``eval/explanation_checks.py``'s five pure checks (C1-C5) against the thread's own
stored ``FitAssessment`` objects and each turn's own tool calls.

Nothing in the agent, a prompt, a tool or the middleware is changed by this
script (WP-15c: one measurement run, reported as it is, no tuning here).

No ad text, profile content or personal name is ever written to the results file
(CLAUDE.md invariant 4): only tool names, referenznummern, the model's follow-up
answers (free text *about* the ad, not the ad text itself), and the check
results.

Usage (needs OPENROUTER_API_KEY):
    uv run python eval/run_explanation_check.py

Writes:
    eval/results/explanation_check.json

Related: D-13, FR-08 AC1, FR-08 AC2, spec §6.3, §9, invariant 2, invariant 4,
invariant 6, D-28, WP-15c
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from langchain_core.messages import AIMessage

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "eval"))

from _agent_run_helpers import run_one_turn  # noqa: E402
from explanation_checks import (  # noqa: E402
    check_category_consistency,
    check_match_gap_consistency,
    check_no_new_tool_call,
    check_quote_fidelity,
    check_turn_d,
)

from job_hunt_agent import config, storage  # noqa: E402
from job_hunt_agent.agent import build_agent  # noqa: E402
from job_hunt_agent.ba_client import FixtureSource  # noqa: E402
from job_hunt_agent.context import AgentContext  # noqa: E402
from job_hunt_agent.llm import build_real_model  # noqa: E402
from job_hunt_agent.models import Profile  # noqa: E402

QUESTION_SET_PATH = PROJECT_ROOT / "eval" / "explanation_set.yaml"
FIXTURES_PATH = PROJECT_ROOT / "data" / "samples" / "fixtures" / "listings.json"
RESULTS_DIR = PROJECT_ROOT / "eval" / "results"
RUNS_PER_THREAD = 2


def make_run_token(now: datetime | None = None) -> str:
    """A per-invocation token isolating one script execution from any other (D-28)."""
    now = now or datetime.now(UTC)
    return f"{now.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"


def make_db_path(run_token: str) -> Path:
    """This invocation's own SQLite file, never shared with another execution (D-28)."""
    return PROJECT_ROOT / "data" / f"explanation_check_run_{run_token}.sqlite"


def make_user_id(thread_id: str, run_index: int, run_token: str) -> str:
    """This invocation's own synthetic user id for one thread-run (D-28)."""
    return f"alex-{thread_id}-r{run_index}-{run_token}"


def load_question_set() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(QUESTION_SET_PATH.read_text(encoding="utf-8"))
    return data


def load_title_employer_by_ref() -> dict[str, tuple[str, str]]:
    """Title/employer for every fixture listing, keyed by referenznummer (C3)."""
    listings = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    return {
        listing["referenznummer"]: (listing.get("title", ""), listing.get("employer", ""))
        for listing in listings
    }


def _tool_calls_of(messages: list[Any]) -> list[dict[str, Any]]:
    calls = []
    for msg in messages:
        if isinstance(msg, AIMessage):
            for tc in msg.tool_calls:
                calls.append({"name": tc["name"], "args": tc["args"]})
    return calls


def _final_text_of(messages: list[Any]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return str(msg.content)
    return ""


def _relevant_referenznummern(turn: dict[str, Any]) -> list[str]:
    if "about_referenznummern" in turn:
        return list(turn["about_referenznummern"])
    return [turn["about_referenznummer"]]


def run_thread_once(
    agent: Any,
    ctx: AgentContext,
    thread: dict[str, Any],
    run_index: int,
    run_token: str,
    marker_lists: dict[str, list[str]],
    title_employer_by_ref: dict[str, tuple[str, str]],
) -> dict[str, Any]:
    """Runs one thread's scripted turns once end to end; returns its scored record."""
    thread_id = thread["id"]
    user_id = make_user_id(thread_id, run_index, run_token)
    run_thread_id = f"expl-{thread_id}-r{run_index}-{uuid.uuid4().hex[:8]}"
    cfg = {"configurable": {"thread_id": run_thread_id}}

    turn_records: list[dict[str, Any]] = []
    message_count = 0
    for turn in thread["turns"]:
        new_messages, result = run_one_turn(
            agent, cfg, ctx, user_id, {"user": turn["text"]}, message_count
        )
        if result is not None:
            message_count = len(result["messages"])
        turn_records.append(
            {
                "type": turn["type"],
                "sub_type": turn.get("sub_type"),
                "tool_calls": _tool_calls_of(new_messages),
                "answer": _final_text_of(new_messages),
            }
        )

    final_state_values = agent.get_state(cfg).values
    assessments = final_state_values.get("assessments", {})

    check_records: list[dict[str, Any]] = []
    for turn, record in zip(thread["turns"], turn_records, strict=True):
        if turn["type"] != "follow_up":
            continue
        sub_type = turn["sub_type"]
        answer = record["answer"]
        tool_calls = record["tool_calls"]

        check_record: dict[str, Any] = {"sub_type": sub_type, "answer": answer}

        if sub_type in ("a", "b", "c"):
            check_record["c4_no_new_tool_call"] = check_no_new_tool_call(tool_calls)

        c1_flags = check_quote_fidelity(answer, list(assessments.values()))
        check_record["c1_flags"] = c1_flags

        if sub_type == "d":
            referenznummer = turn["about_referenznummer"]
            c5_passed, c5_detail = check_turn_d(answer, tool_calls, referenznummer)
            check_record["c5_passed"] = c5_passed
            check_record["c5_detail"] = c5_detail

        relevant_refs = [ref for ref in _relevant_referenznummern(turn) if ref in assessments]
        check_record["assessed_at_check_time"] = relevant_refs
        c2_flags: list[dict[str, Any]] = []
        c3_flags: list[dict[str, Any]] = []
        for ref in relevant_refs:
            assessment = assessments[ref]
            title, employer = title_employer_by_ref.get(ref, ("", ""))
            for flag in check_match_gap_consistency(
                answer, assessment, marker_lists["match_markers"], marker_lists["gap_markers"]
            ):
                c2_flags.append({**flag, "referenznummer": ref})
            for flag in check_category_consistency(answer, ref, title, employer, assessment):
                c3_flags.append({**flag, "referenznummer": ref})
        check_record["c2_flags"] = c2_flags
        check_record["c3_flags"] = c3_flags
        check_records.append(check_record)

    return {
        "thread_id": thread_id,
        "run": run_index,
        "user_id": user_id,
        "stored_assessments": {
            ref: assessment.model_dump(mode="json") for ref, assessment in assessments.items()
        },
        "turns": turn_records,
        "checks": check_records,
    }


def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Pass rates per rule, split by run (run 1 / run 2), over all thread-runs."""
    by_run: dict[int, list[dict[str, Any]]] = {1: [], 2: []}
    for record in records:
        for check in record["checks"]:
            by_run[record["run"]].append(check)

    def _rate(checks: list[dict[str, Any]], key: str) -> dict[str, Any]:
        applicable = [c for c in checks if key in c]
        passed = sum(1 for c in applicable if c[key])
        return {
            "passed": passed,
            "total": len(applicable),
            "rate": passed / len(applicable) if applicable else None,
        }

    def _flag_free_rate(checks: list[dict[str, Any]], flags_key: str) -> dict[str, Any]:
        passed = sum(1 for c in checks if not c[flags_key])
        rate = passed / len(checks) if checks else None
        return {"passed": passed, "total": len(checks), "rate": rate}

    metrics_by_run: dict[str, Any] = {}
    all_c2_flags: list[dict[str, Any]] = []
    all_c3_flags: list[dict[str, Any]] = []
    for run_index, checks in by_run.items():
        metrics_by_run[f"run_{run_index}"] = {
            "c1_quote_fidelity": _flag_free_rate(checks, "c1_flags"),
            "c2_match_gap_consistency": _flag_free_rate(checks, "c2_flags"),
            "c3_category_consistency": _flag_free_rate(checks, "c3_flags"),
            "c4_no_new_tool_call": _rate(checks, "c4_no_new_tool_call"),
            "c5_turn_d": _rate(checks, "c5_passed"),
        }
        for check in checks:
            for flag in check["c2_flags"]:
                all_c2_flags.append({"run": run_index, **flag})
            for flag in check["c3_flags"]:
                all_c3_flags.append({"run": run_index, **flag})

    return {
        "by_run": metrics_by_run,
        "all_c2_flags": all_c2_flags,
        "all_c3_flags": all_c3_flags,
    }


def main() -> int:
    question_set = load_question_set()
    threads = question_set["threads"]
    marker_lists = question_set["marker_lists"]
    title_employer_by_ref = load_title_employer_by_ref()

    run_token = make_run_token()
    db_path = make_db_path(run_token)

    model = build_real_model()
    conn = storage.get_connection(str(db_path))
    agent = build_agent(model, conn)

    profile = Profile.model_validate(
        yaml.safe_load((PROJECT_ROOT / "data" / "samples" / "profile_alex.yaml").read_text())
    )
    ctx = AgentContext(
        job_source=FixtureSource(), profile=profile, extraction_model=model, conn=conn
    )

    records: list[dict[str, Any]] = []
    for thread in threads:
        for run_index in range(1, RUNS_PER_THREAD + 1):
            record = run_thread_once(
                agent, ctx, thread, run_index, run_token, marker_lists, title_employer_by_ref
            )
            records.append(record)
            n_c2 = sum(len(c["c2_flags"]) for c in record["checks"])
            n_c3 = sum(len(c["c3_flags"]) for c in record["checks"])
            print(f"[{thread['id']}] run {run_index}: {n_c2} C2 flag(s), {n_c3} C3 flag(s)")

    metrics = aggregate(records)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results_path = RESULTS_DIR / "explanation_check.json"
    results_path.write_text(
        json.dumps(
            {
                "model": config.CHAT_MODEL,
                "reasoning_effort": config.REASONING_EFFORT,
                "run_datetime_utc": datetime.now(UTC).isoformat(),
                "run_token": run_token,
                "db_path": str(db_path),
                "records": records,
                "metrics": metrics,
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )

    print(f"\nResults: {results_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
