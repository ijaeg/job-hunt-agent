"""Records S1, S3 and S4 LangSmith traces, and one raw request/response (spec §9.5).

Real model, demo mode (``FixtureSource``, invariant 6), the fictional user "alex"
(D-18) - one thread per scenario pair, tracing forced on via
``job_hunt_agent.tracing`` directly (not through the developer-settings toggle,
since this is a script, not the UI). The raw request/response is captured at the
lowest practical seam - the OpenAI SDK's ``Completions.create`` call - so it is
exactly what went over the wire: the request carries the real tool JSON schemas,
the response the real ``tool_calls``. Capture is self-disabling after the first
hit, so later calls in the same run (a refinement search, an extraction call) are
never touched.

Usage (needs OPENROUTER_API_KEY and LANGSMITH_API_KEY):
    uv run python scripts/run_langsmith_traces.py

Writes:
    eval/results/langsmith_wp10.json     project, run ids, thread ids per scenario
    docs/function_calling_example.json   one redacted raw request/response pair

Related: spec §9.5, FR-18 AC1, D-18, WP-10
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import openai.resources.chat.completions as oai_completions
import yaml
from langchain_core.messages import HumanMessage
from langgraph.types import Command

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from job_hunt_agent import config, storage, tracing  # noqa: E402
from job_hunt_agent.agent import build_agent  # noqa: E402
from job_hunt_agent.ba_client import FixtureSource  # noqa: E402
from job_hunt_agent.context import AgentContext  # noqa: E402
from job_hunt_agent.llm import build_real_model  # noqa: E402
from job_hunt_agent.models import Profile  # noqa: E402

DB_PATH = PROJECT_ROOT / "data" / "langsmith_traces_run.sqlite"
RESULTS_PATH = PROJECT_ROOT / "eval" / "results" / "langsmith_wp10.json"
FUNCTION_CALLING_EXAMPLE_PATH = PROJECT_ROOT / "docs" / "function_calling_example.json"

USER_ID = "alex"

#: Message content longer than this is replaced by a placeholder in the example
#: file (WP-10 Part B step 4: "keep the structure, replace long content with a
#: short placeholder"). High enough that the tool schema's own description and
#: the injected profile context (both short, both already public - our own
#: code/the fictional demo profile, FR-14 AC3) survive untouched; the one thing
#: this threshold is actually tuned to catch is the system prompt (already in
#: prompts/system.md, long and redundant here) and, defensively, ad text should
#: a future re-run of this script ever capture a later call than S1's first one.
MAX_EXAMPLE_CONTENT_CHARS = 1000


class _RawExchangeCapture:
    """Captures the first ``Completions.create`` call's kwargs and parsed response.

    Restores the original method immediately after that first hit, so every
    later model call in the same process (a search refinement, an ``assess_fit``
    extraction call, which uses a different SDK method anyway) is unaffected.
    """

    def __init__(self) -> None:
        self.request: dict[str, Any] | None = None
        self.response: dict[str, Any] | None = None
        self._original = oai_completions.Completions.create

    def __enter__(self) -> _RawExchangeCapture:
        original = self._original

        def _capture(self_inner: Any, **kwargs: Any) -> Any:
            result = original(self_inner, **kwargs)
            if self.request is None:
                self.request = kwargs
                try:
                    self.response = result.parse().model_dump()
                except Exception:  # noqa: BLE001 - best effort; the real run must not fail
                    self.response = None
                oai_completions.Completions.create = original  # type: ignore[method-assign]
            return result

        oai_completions.Completions.create = _capture  # type: ignore[method-assign,assignment]
        return self

    def __exit__(self, *exc_info: object) -> None:
        oai_completions.Completions.create = self._original  # type: ignore[method-assign]


def _run_with_tracer(
    agent: Any,
    cfg: dict[str, Any],
    ctx: AgentContext,
    client: Any,
    *,
    thread_id: str,
    scenario: str,
    payload: Any,
) -> tuple[dict[str, Any], str | None]:
    tracer = tracing.build_tracer(client, demo_mode=True, thread_id=thread_id, scenario=scenario)
    if tracer is None:
        raise RuntimeError("Could not build a LangSmith tracer - check LANGSMITH_API_KEY.")
    run_cfg = {**cfg, "callbacks": [tracer]}
    result = agent.invoke(payload, config=run_cfg, context=ctx)
    run_id = str(tracer.latest_run.id) if tracer.latest_run else None
    print(f"[{scenario}] run_id={run_id}")
    return result, run_id


def _truncate_long_content(obj: Any) -> Any:
    """Replaces any string value over :data:`MAX_EXAMPLE_CONTENT_CHARS` with a
    placeholder naming its original length, recursively - keeps the JSON
    structure intact (WP-10 Part B step 4)."""
    if isinstance(obj, dict):
        return {k: _truncate_long_content(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_truncate_long_content(v) for v in obj]
    if isinstance(obj, str) and len(obj) > MAX_EXAMPLE_CONTENT_CHARS:
        return f"<truncated for this example - {len(obj)} characters in the real call>"
    return obj


def main() -> int:
    if not tracing.langsmith_key_present():
        print(f"{config.LANGSMITH_API_KEY_ENV} is not set - nothing to do.")
        return 1
    client = tracing.build_client()
    if client is None:
        print("Could not build a LangSmith client - check the key and LANGSMITH_ENDPOINT.")
        return 1

    model = build_real_model()
    conn = storage.get_connection(str(DB_PATH))
    agent = build_agent(model, conn)
    profile = Profile.model_validate(
        yaml.safe_load((PROJECT_ROOT / "data" / "samples" / "profile_alex.yaml").read_text())
    )
    ctx = AgentContext(
        job_source=FixtureSource(), profile=profile, extraction_model=model, conn=conn
    )

    records: list[dict[str, Any]] = []

    # One continuous thread for S1 -> S3 -> S4 (same pattern as
    # scripts/run_core_journey.py, WP-03): S3's "#1" needs S1's shortlist to
    # refer to, exactly as it would in the real demo script (spec §3.2).
    thread_id = f"langsmith-demo-{uuid.uuid4().hex[:8]}"
    cfg = {"configurable": {"thread_id": thread_id}}

    # S1: narrowing - also where the raw request/response is captured.
    with _RawExchangeCapture() as capture:
        _, s1_run_id = _run_with_tracer(
            agent,
            cfg,
            ctx,
            client,
            thread_id=thread_id,
            scenario="S1",
            payload={
                "messages": [
                    HumanMessage(
                        "Find Python or AI roles in Hamburg from the last two weeks, "
                        "no temp agencies."
                    )
                ],
                "user_id": USER_ID,
            },
        )
    records.append({"scenario": "S1", "thread_id": thread_id, "run_id": s1_run_id})

    # S3: save -> approve.
    _, s3_propose_run = _run_with_tracer(
        agent,
        cfg,
        ctx,
        client,
        thread_id=thread_id,
        scenario="S3_propose",
        payload={
            "messages": [HumanMessage("Save #1 and remind me in a week.")],
            "user_id": USER_ID,
        },
    )
    records.append({"scenario": "S3_propose", "thread_id": thread_id, "run_id": s3_propose_run})
    if agent.get_state(cfg).interrupts:
        _, s3_approve_run = _run_with_tracer(
            agent,
            cfg,
            ctx,
            client,
            thread_id=thread_id,
            scenario="S3_approve",
            payload=Command(resume={"decisions": [{"type": "approve"}]}),
        )
        records.append({"scenario": "S3_approve", "thread_id": thread_id, "run_id": s3_approve_run})

    # S4: remember -> reject.
    _, s4_propose_run = _run_with_tracer(
        agent,
        cfg,
        ctx,
        client,
        thread_id=thread_id,
        scenario="S4_propose",
        payload={
            "messages": [HumanMessage("Never show me jobs from Acme Staffing GmbH again.")],
            "user_id": USER_ID,
        },
    )
    records.append({"scenario": "S4_propose", "thread_id": thread_id, "run_id": s4_propose_run})
    if agent.get_state(cfg).interrupts:
        _, s4_reject_run = _run_with_tracer(
            agent,
            cfg,
            ctx,
            client,
            thread_id=thread_id,
            scenario="S4_reject",
            payload=Command(resume={"decisions": [{"type": "reject"}]}),
        )
        records.append({"scenario": "S4_reject", "thread_id": thread_id, "run_id": s4_reject_run})

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(
            {
                "project": config.LANGSMITH_PROJECT,
                "endpoint": config.LANGSMITH_ENDPOINT,
                "model": config.CHAT_MODEL,
                "reasoning_effort": config.REASONING_EFFORT,
                "run_date": date.today().isoformat(),
                "run_datetime_utc": datetime.now(UTC).isoformat(),
                "user_id": USER_ID,
                "runs": records,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nResults: {RESULTS_PATH}")

    if capture.request is not None and capture.response is not None:
        example = {
            "note": (
                "Captured at the OpenAI SDK's Completions.create seam during one "
                "real S1 run (spec §9.5) - request and response as actually sent "
                "over the wire. Long content is replaced with a placeholder "
                "(structure kept); no API key or personal data is present."
            ),
            "request": _truncate_long_content(capture.request),
            "response": _truncate_long_content(capture.response),
        }
        FUNCTION_CALLING_EXAMPLE_PATH.write_text(
            json.dumps(example, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Function-calling example: {FUNCTION_CALLING_EXAMPLE_PATH}")
    else:
        print("WARNING: no raw request/response was captured during S1.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
