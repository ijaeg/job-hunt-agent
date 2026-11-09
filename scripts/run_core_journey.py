"""Console run of the core journey (spec §3.2 S1, S2, S3, S4, S6) with the real model.

Runs one continuous thread against the **live** BA API (job_source=BAClient) so
S1 can show genuine refinement (D-10: the committed 43-listing fixture set can
never report more than ~6 results, so demo mode cannot exercise the ">50,
narrow" direction - see docs/decisions/D-10-demo-search-semantics.md).
Approvals are scripted, not interactive: S3 approves, S4 rejects.

No ad text is written anywhere by this script (CLAUDE.md invariant 4): the
per-scenario record keeps only tool names/arguments, timings, token counts
and the final assistant message, never a raw ToolMessage payload (which
would contain ad text from get_job_details/assess_fit).

Usage (needs OPENROUTER_API_KEY):
    uv run python scripts/run_core_journey.py

Writes:
    eval/results/core_journey_wp03.json   full per-scenario record
    spikes/NOTES.md                       appends a "WP-03 core journey" summary
    docs/decisions/D-12-latency.md         only if S1 exceeds 60 s (NFR-03, R-4)

Related: FR-01-FR-10, FR-13, FR-20-FR-23, spec §3.2, §9.2, §9.5, NFR-03, D-10, D-12
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from job_hunt_agent import config, storage  # noqa: E402
from job_hunt_agent.agent import build_agent  # noqa: E402
from job_hunt_agent.ba_client import BAClient  # noqa: E402
from job_hunt_agent.context import AgentContext  # noqa: E402
from job_hunt_agent.llm import build_real_model  # noqa: E402
from job_hunt_agent.models import Profile  # noqa: E402

DB_PATH = PROJECT_ROOT / "data" / "core_journey_run.sqlite"
RESULTS_PATH = PROJECT_ROOT / "eval" / "results" / "core_journey_wp03.json"
NOTES_PATH = PROJECT_ROOT / "spikes" / "NOTES.md"
D12_PATH = PROJECT_ROOT / "docs" / "decisions" / "D-12-latency.md"
S1_LATENCY_BUDGET_SECONDS = 60.0


def _tool_calls_of(messages: list[Any]) -> list[dict[str, Any]]:
    calls = []
    for msg in messages:
        if isinstance(msg, AIMessage):
            for tc in msg.tool_calls:
                calls.append({"name": tc["name"], "args": tc["args"]})
    return calls


def _token_usage_of(messages: list[Any]) -> dict[str, int]:
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.usage_metadata:
            usage: dict[str, Any] = dict(msg.usage_metadata)
            for key in totals:
                totals[key] += usage.get(key, 0) or 0
    return totals


def _assess_fit_extraction_seconds(messages: list[Any]) -> float | None:
    """Reads the latency note ``assess_fit`` appends to its own ``ToolResult.notes``."""
    for msg in messages:
        if isinstance(msg, ToolMessage) and msg.name == "assess_fit":
            content = json.loads(str(msg.content))
            for note in content.get("notes", []):
                if note.startswith("assess_fit extraction:"):
                    return float(note.split(":")[1].strip().rstrip("s").split("s")[0])
    return None


def _final_text_of(messages: list[Any]) -> str:
    if not messages:
        return ""
    last = messages[-1]
    return str(last.content) if isinstance(last, AIMessage) else ""


def run_scenario(
    agent: Any,
    cfg: dict[str, Any],
    ctx: AgentContext,
    label: str,
    user_message: str | None,
    *,
    resume_decision: str | None = None,
    messages_before: int = 0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Runs one turn (or a resume) and records a no-ad-text summary of it.

    ``agent.invoke()`` returns the full, cumulative thread state - ``messages_before``
    (the message count going in) is what lets this function report only the
    *new* messages this call added, not the whole history again.
    """
    started = time.perf_counter()
    if resume_decision is not None:
        payload: Any = Command(resume={"decisions": [{"type": resume_decision}]})
    else:
        assert user_message is not None
        payload = {"messages": [HumanMessage(user_message)], "user_id": "alex"}

    result = agent.invoke(payload, config=cfg, context=ctx)
    elapsed = time.perf_counter() - started
    new_messages = result["messages"][messages_before:]

    interrupted = bool(agent.get_state(cfg).interrupts)
    record: dict[str, Any] = {
        "scenario": label,
        "user_message": user_message,
        "resume_decision": resume_decision,
        "elapsed_seconds": round(elapsed, 2),
        "tool_calls": _tool_calls_of(new_messages),
        "token_usage": _token_usage_of(new_messages),
        "interrupted_after": interrupted,
        "final_message": _final_text_of(new_messages) if not interrupted else None,
        "assess_fit_extraction_seconds": _assess_fit_extraction_seconds(new_messages),
        "message_count_after": len(result["messages"]),
    }
    print(f"[{label}] {elapsed:.1f}s, tools={[c['name'] for c in record['tool_calls']]}")
    return record, result


def main() -> int:
    model = build_real_model()
    conn = storage.get_connection(str(DB_PATH))
    agent = build_agent(model, conn)

    profile = Profile.model_validate(
        yaml.safe_load((PROJECT_ROOT / "data" / "samples" / "profile_alex.yaml").read_text())
    )
    ctx = AgentContext(job_source=BAClient(), profile=profile, extraction_model=model, conn=conn)
    cfg = {"configurable": {"thread_id": "core-journey-wp03"}}

    records: list[dict[str, Any]] = []
    n = 0  # running message count, so each call only reports its own new messages

    # S1: search -> (possible refinement) -> details -> assess_fit -> shortlist.
    s1_record, s1_result = run_scenario(
        agent,
        cfg,
        ctx,
        "S1",
        "Find Python or AI roles in Hamburg from the last two weeks, no temp agencies.",
        messages_before=n,
    )
    n = s1_record["message_count_after"]
    s1_search_calls = sum(1 for c in s1_record["tool_calls"] if c["name"] == "search_jobs")
    s1_record["refinement_shown"] = s1_search_calls > 1
    records.append(s1_record)

    if s1_record["elapsed_seconds"] > S1_LATENCY_BUDGET_SECONDS:
        write_d12_latency_decision(s1_record)
        print(
            f"S1 took {s1_record['elapsed_seconds']}s > {S1_LATENCY_BUDGET_SECONDS}s budget; "
            f"wrote {D12_PATH}. Continuing with the remaining scenarios anyway."
        )

    # S2: follow-up question, answered from state, no new tool call expected.
    s2_record, _ = run_scenario(agent, cfg, ctx, "S2", "Why is #3 only partial?", messages_before=n)
    n = s2_record["message_count_after"]
    records.append(s2_record)

    # S3: save #1, approve.
    s3_record, _ = run_scenario(
        agent, cfg, ctx, "S3_propose", "Save #1 and remind me in a week.", messages_before=n
    )
    n = s3_record["message_count_after"]
    records.append(s3_record)
    if s3_record["interrupted_after"]:
        s3_resume, _ = run_scenario(
            agent, cfg, ctx, "S3_approve", None, resume_decision="approve", messages_before=n
        )
        n = s3_resume["message_count_after"]
        records.append(s3_resume)

    # S4: exclude an employer actually seen in S1's results; reject the proposal.
    employer = _pick_an_employer(s1_result) or "Acme Staffing GmbH"
    s4_record, _ = run_scenario(
        agent,
        cfg,
        ctx,
        "S4_propose",
        f"Never show me jobs from {employer} again.",
        messages_before=n,
    )
    n = s4_record["message_count_after"]
    records.append(s4_record)
    if s4_record["interrupted_after"]:
        s4_resume, _ = run_scenario(
            agent, cfg, ctx, "S4_reject", None, resume_decision="reject", messages_before=n
        )
        n = s4_resume["message_count_after"]
        records.append(s4_resume)

    # S6: off-topic, no tool call expected.
    s6_record, _ = run_scenario(
        agent, cfg, ctx, "S6", "What's the weather in Hamburg?", messages_before=n
    )
    records.append(s6_record)

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(
            {
                "model": config.CHAT_MODEL,
                "reasoning_effort": config.REASONING_EFFORT,
                "scenarios": records,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    append_notes_summary(records)
    print(f"\nResults: {RESULTS_PATH}\nSummary appended to: {NOTES_PATH}")
    return 0


def _pick_an_employer(s1_result: dict[str, Any]) -> str | None:
    for msg in s1_result["messages"]:
        if isinstance(msg, ToolMessage) and msg.name == "search_jobs":
            content = json.loads(str(msg.content))
            listings = (content.get("result") or {}).get("listings") or []
            for listing in listings:
                if listing.get("employer"):
                    return str(listing["employer"])
    return None


def write_d12_latency_decision(s1_record: dict[str, Any]) -> None:
    D12_PATH.write_text(
        f"""# D-12: S1 latency over the NFR-03 60 s budget

## Question

S1 ("Find Python or AI roles in Hamburg...") took {s1_record["elapsed_seconds"]} s against
the real model, exceeding the NFR-03 budget of {S1_LATENCY_BUDGET_SECONDS} s
(risk R-4, spec §14). What should change?

## Context

Recorded tool sequence: {[c["name"] for c in s1_record["tool_calls"]]}.
`assess_fit` extraction alone took
{s1_record.get("assess_fit_extraction_seconds")} s
({config.MAX_CONCURRENT_EXTRACTIONS} concurrent calls, model
`{config.CHAT_MODEL}`, reasoning effort `{config.REASONING_EFFORT}`).
Full per-scenario timing: `eval/results/core_journey_wp03.json`.

## Options

1. Lower `REASONING_EFFORT` to `"minimal"` for the extraction call only
   (`assess_fit`), keeping the main agent loop at `"low"`.
2. Reduce listings assessed per `assess_fit` call (currently
   `config.MAX_LISTINGS_PER_ASSESS_FIT_CALL = 8`).
3. Shrink the extraction schema (fewer/shorter fields in
   `JobRequirements`) to reduce output tokens.

## Recommendation

(Fill in after comparing the three levers' actual effect on this run's
numbers - not pre-judged here.)

## Consequences

To be filled in once a lever is chosen; would touch `config.py` and/or
`tools/assess.py`, `prompts/extract_requirements.md`.

**Decision:**
""",
        encoding="utf-8",
    )


def append_notes_summary(records: list[dict[str, Any]]) -> None:
    lines = [
        "",
        "## WP-03 core journey: real-model console run (2026-11-06)",
        "",
        "Script: `scripts/run_core_journey.py`. One continuous thread, live BA API "
        "(job_source=BAClient, D-10), real model. Full record (no ad text): "
        "`eval/results/core_journey_wp03.json`.",
        "",
        "| Scenario | Elapsed (s) | Tools called | Tokens (in/out) |",
        "|---|---|---|---|",
    ]
    for r in records:
        tools = ", ".join(c["name"] for c in r["tool_calls"]) or "(none)"
        usage = r["token_usage"]
        lines.append(
            f"| {r['scenario']} | {r['elapsed_seconds']} | {tools} | "
            f"{usage['input_tokens']}/{usage['output_tokens']} |"
        )
    s1 = records[0]
    lines.append("")
    lines.append(
        f"- S1 refinement shown: {s1.get('refinement_shown')} "
        f"({sum(1 for c in s1['tool_calls'] if c['name'] == 'search_jobs')} search_jobs calls)."
    )
    lines.append(
        f"- S1 within the {S1_LATENCY_BUDGET_SECONDS}s NFR-03 budget: "
        f"{s1['elapsed_seconds'] <= S1_LATENCY_BUDGET_SECONDS}."
    )
    lines.append("")
    with NOTES_PATH.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
