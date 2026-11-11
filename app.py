"""Streamlit entry point for the core journey (spec §11, NFR-01).

Layout and wiring only (NFR-04): no prompt text, no business logic. Pure
helpers for the shortlist cards live in ``src/job_hunt_agent/ui_view.py``;
the agent, tools and middleware live in ``src/job_hunt_agent/``. Start with
``uv run streamlit run app.py``.

Scope (WP-04): the core journey only - chat, shortlist cards, "Save to
tracker", the approval flow, and demo-mode switching. The tracker page,
memory page, profile form, thread list and developer settings are later
work packages.

Related: FR-01 AC1, FR-07, FR-09, FR-10 AC2, FR-10 AC5, FR-16, FR-17 AC1,
FR-19 AC1-AC2, NFR-01, NFR-03, NFR-04, D-5, D-10, D-11
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import streamlit as st
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langgraph.types import Command

# Streamlit inserts the *entry* script's own directory into sys.path while
# it runs (so `streamlit run app.py` lets both this file and pages/*.py
# import sibling root modules), but a page tested directly via
# ``AppTest.from_file`` or a module loaded by raw ``importlib`` (as
# tests/test_app.py's ``_load_app_module`` does) gets no such help - so this
# file adds its own directory explicitly before importing ``ui_shared``.
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from job_hunt_agent import config, steps_view, storage, ui_view, usage, user_view  # noqa: E402
from job_hunt_agent.agent import AGENT_TOOLS, build_agent  # noqa: E402
from job_hunt_agent.ba_client import BAClient, FixtureSource, JobSource  # noqa: E402
from job_hunt_agent.context import AgentContext  # noqa: E402
from job_hunt_agent.llm import build_real_model  # noqa: E402
from ui_shared import (  # noqa: E402
    CHAT_MODEL_KEY,
    DEMO_MODE_AUTO_MESSAGE_KEY,
    DEMO_MODE_KEY,
    GET_JOB_DETAILS_ENABLED_KEY,
    LIST_TRACKER_ENABLED_KEY,
    REASONING_EFFORT_KEY,
    build_run_callbacks,
    ensure_developer_settings_initialized,
    get_connection,
    last_turn_usage_records,
    load_profile_or_none,
    record_turn_usage,
    render_usage_summary,
    render_user_sidebar,
    session_usage_records,
)

_STATUS_LABELS: dict[str, str] = {
    "search_jobs": "Searching the job board…",
    "assess_fit": "Assessing fit…",
}

#: Wall-clock seconds per tool-call id, for turns run in *this* session only
#: (FR-17 AC1's steps panel) - a fresh Python process starts this empty, so a
#: resumed older thread's calls are simply never in it (shown as "-").
TOOL_CALL_DURATIONS_KEY = "_tool_call_durations"

st.set_page_config(page_title="Job Hunt Agent", layout="wide")


# ---------------------------------------------------------------------------
# A scripted model for tests only (``JOB_HUNT_FAKE_MODEL=1``), never active
# otherwise. Mirrors ``spikes/hitl_app.py``'s ``ScriptedChatModel`` (D-5) -
# referenced, not imported, per that work package's instruction. Only the
# main ReAct loop is faked this way; ``assess_fit``'s separate extraction
# model is not exercised by this work package's AppTest scenarios.
#
# A real ``BaseChatModel`` subclass (not a bare duck-typed object, as before
# WP-09): ``create_agent``'s model node only threads ``config`` (and its
# ``callbacks``) into a model's own ``invoke()`` call through the full
# ``Runnable``/``BaseChatModel`` protocol - confirmed in WP-09's "Check
# first" that a plain object's ``.invoke(messages)`` is called with no
# config at all. Subclassing properly is what makes FR-18 AC2's usage
# tracking exercisable in AppTest without a real OpenRouter call.
# ---------------------------------------------------------------------------

#: Fixed usage every scripted turn reports (FR-18 AC2's AppTest coverage) -
#: not meant to resemble a real call's token counts, just non-zero and
#: distinguishable in assertions.
_SCRIPTED_USAGE_METADATA: dict[str, Any] = {
    "input_tokens": 11,
    "output_tokens": 7,
    "total_tokens": 18,
    "output_token_details": {"reasoning": 0},
}
_SCRIPTED_RESPONSE_METADATA: dict[str, Any] = {
    "model_name": "scripted/fake-model",
    "token_usage": {"cost": 0.0001},
}


class _ScriptedModel(BaseChatModel):
    """Pops the next turn from ``st.session_state["_scripted_turns"]``; no network call."""

    @property
    def _llm_type(self) -> str:
        return "job-hunt-scripted-model"

    def bind_tools(
        self, tools: Any, *, tool_choice: str | None = None, **kwargs: Any
    ) -> Runnable[Any, AIMessage]:
        del tools, tool_choice, kwargs  # scripted tool calls ignore what was actually bound
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        queue: list[Any] = st.session_state.get("_scripted_turns", [])
        if not queue:
            message = AIMessage(content="(scripted model: no more turns)")
        else:
            spec = queue.pop(0)
            st.session_state["_scripted_turns"] = queue
            if isinstance(spec, str):
                message = AIMessage(content=spec)
            else:
                tool_calls = [
                    {"name": call["name"], "args": call["args"], "id": f"call_{i}_{call['name']}"}
                    for i, call in enumerate(spec)
                ]
                message = AIMessage(content="", tool_calls=tool_calls)
        message = message.model_copy(
            update={
                "usage_metadata": _SCRIPTED_USAGE_METADATA,
                "response_metadata": _SCRIPTED_RESPONSE_METADATA,
            }
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


# ---------------------------------------------------------------------------
# Cached resources (D-5, FR-10 AC5): built once per process, not per rerun.
# ---------------------------------------------------------------------------


@st.cache_resource
def get_model(model: str, reasoning_effort: str) -> Any:
    """Cached per (model, reasoning_effort) - switching either in developer
    settings (FR-18 AC1) builds (and then reuses) a distinct client."""
    if os.getenv("JOB_HUNT_FAKE_MODEL") == "1":
        return _ScriptedModel()
    return build_real_model(model, reasoning_effort)


@st.cache_resource
def get_fixture_source() -> FixtureSource:
    return FixtureSource()


@st.cache_resource
def get_live_source() -> BAClient:
    return BAClient()


# ---------------------------------------------------------------------------
# Thread id (FR-16 AC3): kept in the URL so a browser reload keeps the thread.
# ---------------------------------------------------------------------------


def get_or_create_thread_id() -> str:
    thread_id = st.query_params.get("thread_id")
    if not thread_id:
        thread_id = str(uuid.uuid4())
        st.query_params["thread_id"] = thread_id
    return thread_id


def start_new_thread() -> None:
    st.query_params["thread_id"] = str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Running one agent turn, with progress labels (FR-16 AC2)
# ---------------------------------------------------------------------------


def _status_label(name: str, args: dict[str, Any], counts: dict[str, int]) -> str | None:
    if name == "get_job_details":
        counts["job_details"] = counts.get("job_details", 0) + 1
        return f"Reading {counts['job_details']} listing(s)…"
    return _STATUS_LABELS.get(name)


def iter_new_tool_calls(step: dict[str, Any], seen_tool_call_ids: set[str]) -> list[Any]:
    """Extracts genuinely new tool calls from one ``stream_mode="updates"`` step.

    Several middleware ``before_model``/``after_model`` hooks (e.g. the
    built-in ``PIIMiddleware``) return an update carrying the *whole*
    ``messages`` list, not just the newly proposed one - the same
    ``AIMessage`` (same tool call ``id``) then reappears in several steps
    of the same ``agent.stream(...)`` call. ``seen_tool_call_ids`` is
    mutated in place so a caller iterating many steps only ever gets each
    call once, however many times it is echoed.

    Related: FR-16 AC2
    """
    new_calls: list[Any] = []
    for update in step.values():
        if not isinstance(update, dict):
            continue
        for msg in update.get("messages", []):
            if not isinstance(msg, AIMessage):
                continue
            for tool_call in msg.tool_calls:
                tool_call_id = tool_call.get("id")
                if tool_call_id is not None:
                    if tool_call_id in seen_tool_call_ids:
                        continue
                    seen_tool_call_ids.add(tool_call_id)
                new_calls.append(tool_call)
    return new_calls


def iter_new_tool_message_ids(step: dict[str, Any], seen_tool_message_ids: set[str]) -> list[str]:
    """Extracts genuinely new ``ToolMessage`` ids from one stream step (FR-17 AC1).

    Mirrors :func:`iter_new_tool_calls`'s dedup trick - the same ``ToolMessage``
    can be echoed by a later middleware step (e.g. ``PIIMiddleware`` scrubbing
    its content), which must not be mistaken for the tool call finishing a
    second time. Used by :func:`run_turn` to mark the first moment a tool
    call's result is seen, for the steps panel's duration column.
    """
    new_ids: list[str] = []
    for update in step.values():
        if not isinstance(update, dict):
            continue
        for msg in update.get("messages", []):
            if not isinstance(msg, ToolMessage) or msg.tool_call_id is None:
                continue
            if msg.tool_call_id in seen_tool_message_ids:
                continue
            seen_tool_message_ids.add(msg.tool_call_id)
            new_ids.append(msg.tool_call_id)
    return new_ids


def _build_run_cfg(cfg: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
    """Adds the usage-tracking callback and, when on, a LangSmith tracer (D-18)
    to one agent call's config. Scenario tags are not known here - that is only
    ever set by the dedicated trace-recording script (WP-10 Part B step 3).

    Related: FR-18 AC1, AC2, spec §9.5, D-18
    """
    callbacks: list[Any] = []
    if ctx.usage_tracker is not None:
        callbacks.append(ctx.usage_tracker.agent_loop)
    callbacks.extend(
        build_run_callbacks(
            cfg["configurable"]["thread_id"], st.session_state.get(DEMO_MODE_KEY, False)
        )
    )
    return {**cfg, "callbacks": callbacks} if callbacks else cfg


def run_turn(agent: Any, cfg: dict[str, Any], ctx: AgentContext, payload: Any) -> None:
    """Runs one agent turn (or a resume), showing progress labels as tool calls arrive.

    Never lets an exception reach the page (invariant 7, CLAUDE.md): a
    failure becomes a friendly ``st.error`` and the chat stays usable.
    Also times every tool call for the steps panel (FR-17 AC1): started
    when it is first proposed, stopped when its ``ToolMessage`` is first
    seen, kept in ``st.session_state[TOOL_CALL_DURATIONS_KEY]`` for the
    rest of this session.

    Related: FR-16 AC2, FR-17 AC1, invariant 7
    """
    counts: dict[str, int] = {}
    seen_tool_call_ids: set[str] = set()
    seen_tool_message_ids: set[str] = set()
    started_at: dict[str, float] = {}
    durations = st.session_state.setdefault(TOOL_CALL_DURATIONS_KEY, {})
    run_cfg = _build_run_cfg(cfg, ctx)
    try:
        with st.status("Thinking…", expanded=False) as status:
            for step in agent.stream(payload, config=run_cfg, context=ctx, stream_mode="updates"):
                for tool_call in iter_new_tool_calls(step, seen_tool_call_ids):
                    started_at[tool_call["id"]] = time.perf_counter()
                    label = _status_label(tool_call["name"], tool_call["args"], counts)
                    if label:
                        status.update(label=label)
                for tool_call_id in iter_new_tool_message_ids(step, seen_tool_message_ids):
                    start = started_at.get(tool_call_id)
                    if start is not None:
                        durations[tool_call_id] = time.perf_counter() - start
            status.update(label="Done", state="complete")
    except Exception:  # noqa: BLE001 - never a stack trace in the UI (invariant 7)
        st.error(
            "Something went wrong while talking to the job board or the model. Please try again."
        )


# ---------------------------------------------------------------------------
# Chat history (FR-01 AC1): read from the checkpointer, never from session state.
# ---------------------------------------------------------------------------


def _duration_text(duration_seconds: float | None) -> str:
    return f"{duration_seconds:.1f}s" if duration_seconds is not None else "-"


def render_step_row(step: steps_view.StepRow) -> None:
    """One line of an "Agent steps" expander (FR-17 AC1)."""
    parallel_tag = " · parallel" if step.parallel else ""
    result_text = step.short_result if step.short_result is not None else "pending"
    st.caption(
        f"**{step.tool}**{parallel_tag} · `{step.args_text}` · {result_text} · "
        f"{_duration_text(step.duration_seconds)}"
    )


def render_chat_history(messages: list[Any], durations: dict[str, float] | None = None) -> None:
    """Renders one chat bubble per turn plus its "Agent steps" expander (FR-01 AC1, FR-17 AC1).

    ``durations`` only ever holds entries for turns run in the current
    session (``run_turn``'s stream loop) - a resumed older thread's steps
    render with no duration ("-"), per WP-12's decision.
    """
    for turn in steps_view.split_into_turns(messages):
        for msg in turn:
            if steps_view.is_user_turn_message(msg):
                st.chat_message("user").write(str(msg.content))
            elif isinstance(msg, AIMessage) and msg.content:
                st.chat_message("assistant").write(str(msg.content))
        steps = steps_view.build_turn_steps(turn, durations)
        if steps:
            with st.expander(f"Agent steps ({len(steps)})", expanded=False):
                for step in steps:
                    render_step_row(step)


# ---------------------------------------------------------------------------
# Approval UI (FR-10 AC2, AC5)
# ---------------------------------------------------------------------------


def _render_edit_form(name: str, args: dict[str, Any], key_prefix: str) -> dict[str, Any]:
    edited = dict(args)
    if name == "save_to_tracker":
        edited["status"] = st.selectbox(
            "Status",
            ["saved", "applied", "rejected"],
            index=["saved", "applied", "rejected"].index(args.get("status", "saved")),
            key=f"{key_prefix}_status",
        )
        follow_up = st.text_input(
            "Follow-up date (YYYY-MM-DD, optional)",
            value=args.get("follow_up_date") or "",
            key=f"{key_prefix}_follow_up",
        )
        edited["follow_up_date"] = follow_up or None
        edited["note"] = st.text_input(
            "Note (optional)", value=args.get("note") or "", key=f"{key_prefix}_note"
        )
    elif name == "remember":
        edited["kind"] = st.selectbox(
            "Kind",
            ["excluded_employer", "preference"],
            index=["excluded_employer", "preference"].index(args.get("kind", "preference")),
            key=f"{key_prefix}_kind",
        )
        edited["value"] = st.text_input(
            "Value", value=args.get("value", ""), key=f"{key_prefix}_value"
        )
    return edited


def render_approval(
    agent: Any, cfg: dict[str, Any], ctx: AgentContext, interrupt_value: Any
) -> None:
    """Renders Approve/Edit/Reject for every pending action request (FR-10 AC2, AC5).

    Reads the pending interrupt from ``agent.get_state(cfg).interrupts``
    (never from ``st.session_state``) and resumes with
    ``Command(resume={"decisions": [...]})`` on the same thread once every
    action request in this interrupt has a decision. In the common case of
    one pending action, clicking Approve or Reject resumes immediately;
    Edit reveals a form with its own "Save edited action" button.
    ``st.session_state["_pending_decisions"]`` only ever tracks decisions
    for the *current* interrupt - it is cleared the moment all of them are
    collected and the resume is sent.
    """
    requests = interrupt_value["action_requests"]
    decided: dict[int, dict[str, Any]] = st.session_state.setdefault("_pending_decisions", {})

    for i, action in enumerate(requests):
        if i in decided:
            continue
        name, args = action["name"], action["args"]
        st.warning(f"Approval needed: `{name}`")
        st.json(args)

        if st.session_state.get(f"approval_editing_{i}"):
            edited_args = _render_edit_form(name, args, f"approval_edit_{i}")
            if st.button("Save edited action", key=f"approval_save_edit_{i}"):
                decided[i] = {"type": "edit", "edited_action": {"name": name, "args": edited_args}}
                st.session_state[f"approval_editing_{i}"] = False
        else:
            approve_col, edit_col, reject_col = st.columns(3)
            if approve_col.button("Approve", key=f"approval_approve_{i}"):
                decided[i] = {"type": "approve"}
            if edit_col.button("Edit", key=f"approval_edit_btn_{i}"):
                st.session_state[f"approval_editing_{i}"] = True
                st.rerun()
            if reject_col.button("Reject", key=f"approval_reject_{i}"):
                decided[i] = {"type": "reject"}

    if len(decided) == len(requests):
        decisions = [decided[i] for i in range(len(requests))]
        st.session_state.pop("_pending_decisions", None)
        run_cfg = _build_run_cfg(cfg, ctx)
        try:
            agent.invoke(Command(resume={"decisions": decisions}), config=run_cfg, context=ctx)
        except Exception:  # noqa: BLE001 - invariant 7
            st.error("Could not apply that decision. Please try again.")
        record_turn_usage(ctx.usage_tracker)
        st.rerun()


# ---------------------------------------------------------------------------
# Shortlist cards (FR-07)
# ---------------------------------------------------------------------------


def render_card(card: ui_view.CardData) -> None:
    with st.container(border=True):
        st.markdown(f"**[{card.title}]({card.url})**")
        meta = " · ".join(
            str(part)
            for part in (
                card.employer,
                card.location,
                f"{card.distance_km:.0f} km" if card.distance_km is not None else None,
                card.published_date,
            )
            if part
        )
        if meta:
            st.caption(meta)
        if card.remote_type:
            remote = (
                f"Remote: {card.remote_type} ({card.remote_percent}%)"
                if card.remote_percent is not None
                else f"Remote: {card.remote_type}"
            )
            st.caption(remote)

        st.markdown(f"**Fit: {card.category}**")
        if card.exclusion_reasons:
            st.caption("Excluded: " + "; ".join(card.exclusion_reasons))
        note = ui_view.low_evidence_note(card.low_evidence)
        if note:
            st.caption(note)
        if card.matches:
            st.markdown("Top matches:")
            for match in card.matches:
                st.caption(f'✓ {match.name} — "{match.evidence_de}" ({match.evidence_en})')
        if card.gaps:
            with st.expander("Gaps"):
                for gap in card.gaps:
                    st.caption(f'{gap.name} — "{gap.evidence_de}" ({gap.evidence_en})')
        if card.unknown:
            with st.expander("Not mentioned"):
                for item in card.unknown:
                    st.caption(item)

        if st.button("Save to tracker", key=f"save_{card.referenznummer}"):
            st.session_state["pending_message"] = (
                f'Save "{card.title}" ({card.referenznummer}) to the tracker.'
            )
            st.rerun()


def render_shortlist(
    shortlist: list[str], summaries: dict[str, Any], assessments: dict[str, Any]
) -> None:
    cards = ui_view.build_cards(shortlist, summaries, assessments)
    visible, excluded = ui_view.order_cards(cards)
    if not visible and not excluded:
        st.caption("No shortlisted listings yet - ask the agent to search for something.")
        return
    for card in visible:
        render_card(card)
    if excluded:
        with st.expander(f"Excluded ({len(excluded)})"):
            for card in excluded:
                render_card(card)


# ---------------------------------------------------------------------------
# Thread list (FR-13 AC2): resume or delete one of the selected user's threads.
# ---------------------------------------------------------------------------


def render_thread_list(conn: Any, user_id: str, checkpointer: Any, current_thread_id: str) -> None:
    """Sidebar list of ``user_id``'s threads, newest first; resume or delete each one.

    Deleting a thread removes it from both the checkpointer
    (``SqliteSaver.delete_thread``) and the ``threads`` registry
    (``storage.delete_thread_record``); deleting the currently open thread
    opens a new empty one instead of leaving the page pointed at a thread
    id that no longer exists.

    Related: FR-13 AC2, D-15
    """
    threads = storage.list_threads(conn, user_id)
    if not threads:
        return
    st.caption("Threads")
    for thread in threads:
        is_current = thread.thread_id == current_thread_id
        with st.container(border=True):
            st.caption(thread.title or "(untitled)")
            resume_col, delete_col = st.columns(2)
            with resume_col:
                if st.button(
                    "Current" if is_current else "Resume",
                    key=f"resume_thread_{thread.thread_id}",
                    disabled=is_current,
                ):
                    st.query_params["thread_id"] = thread.thread_id
                    st.rerun()
            with delete_col:
                confirm_key = f"confirm_delete_thread_{thread.thread_id}"
                if st.session_state.get(confirm_key):
                    yes_col, no_col = st.columns(2)
                    if yes_col.button("Yes", key=f"delete_thread_yes_{thread.thread_id}"):
                        checkpointer.delete_thread(thread.thread_id)
                        storage.delete_thread_record(conn, user_id, thread.thread_id)
                        st.session_state.pop(confirm_key, None)
                        if is_current:
                            start_new_thread()
                        st.rerun()
                    if no_col.button("No", key=f"delete_thread_cancel_{thread.thread_id}"):
                        st.session_state.pop(confirm_key, None)
                        st.rerun()
                elif st.button("Delete", key=f"delete_thread_{thread.thread_id}"):
                    st.session_state[confirm_key] = True
                    st.rerun()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    st.title("Job Hunt Agent")

    conn = get_connection(os.getenv("DB_PATH", config.DB_PATH))
    user_id = render_user_sidebar(conn)
    ensure_developer_settings_initialized()

    try:
        model = get_model(st.session_state[CHAT_MODEL_KEY], st.session_state[REASONING_EFFORT_KEY])
    except RuntimeError:
        # invariant 7: a missing API key is a friendly message, never a stack trace.
        st.error(f"{config.OPENROUTER_API_KEY_ENV} is not set. Add it to .env and restart.")
        st.stop()
        return

    profile = load_profile_or_none(conn, user_id)
    demo_mode = st.session_state[DEMO_MODE_KEY]

    with st.sidebar:
        if st.button("New search"):
            start_new_thread()
            st.rerun()
        st.caption("Token usage and cost this session")
        render_usage_summary(*session_usage_records())

    if profile is None:
        # Goal 2 (WP-08): a user without a profile sees a hint, not the chat -
        # nothing is seeded silently for anyone but ui_shared.DEFAULT_USER_ID.
        st.info("This user has no profile yet.")
        st.page_link("pages/3_Profile.py", label="Go to the Profile page to create one")
        return

    job_source: JobSource
    if demo_mode:
        st.info("Demo data – not live listings")
        auto_message = st.session_state.get(DEMO_MODE_AUTO_MESSAGE_KEY)
        if auto_message:
            st.caption(auto_message)
        job_source = get_fixture_source()
    else:
        job_source = get_live_source()

    thread_id = get_or_create_thread_id()

    with st.sidebar:
        render_thread_list(conn, user_id, storage.get_checkpointer(conn), thread_id)

    tools = AGENT_TOOLS
    if not st.session_state[GET_JOB_DETAILS_ENABLED_KEY]:
        # assess_fit loads details itself regardless (spec §6.1), so the core
        # journey still works with this tool disabled (FR-18 AC1).
        tools = [t for t in tools if t.name != "get_job_details"]
    if not st.session_state[LIST_TRACKER_ENABLED_KEY]:
        tools = [t for t in tools if t.name != "list_tracker"]

    cfg = {"configurable": {"thread_id": thread_id}}
    ctx = AgentContext(
        job_source=job_source,
        profile=profile,
        extraction_model=model,
        conn=conn,
        usage_tracker=usage.new_turn_usage_tracker(),
    )
    agent = build_agent(model, conn, tools=tools)

    state = agent.get_state(cfg)
    values = state.values or {}
    messages = values.get("messages", [])

    chat_col, shortlist_col = st.columns([2, 1])

    with shortlist_col:
        st.subheader("Shortlist")
        render_shortlist(
            values.get("shortlist", []), values.get("summaries", {}), values.get("assessments", {})
        )

    with chat_col:
        render_chat_history(messages, st.session_state.get(TOOL_CALL_DURATIONS_KEY))
        last_agent_loop, last_extraction = last_turn_usage_records()
        if last_agent_loop or last_extraction:
            with st.expander("Last turn's token usage and cost", expanded=False):
                # Addendum 1 to WP-09: the model names come from the usage
                # records themselves (response metadata, UsageCallbackHandler),
                # not from the current developer-settings value, so this
                # caption shows which model actually answered this turn even
                # if the setting changed since.
                models = sorted({r.model for r in [*last_agent_loop, *last_extraction]})
                st.caption(
                    f"Model: {', '.join(models)} · "
                    f"reasoning effort: {st.session_state[REASONING_EFFORT_KEY]}"
                )
                render_usage_summary(last_agent_loop, last_extraction)

        if state.interrupts:
            render_approval(agent, cfg, ctx, state.interrupts[0].value)
            return

        pending_message = st.session_state.pop("pending_message", None)
        user_input = pending_message or st.chat_input("Describe the job you're looking for...")
        if user_input:
            st.chat_message("user").write(user_input)
            storage.touch_thread(
                conn, user_id, thread_id, user_view.thread_title(user_input), datetime.now(UTC)
            )
            run_turn(
                agent,
                cfg,
                ctx,
                {"messages": [HumanMessage(user_input)], "user_id": user_id},
            )
            record_turn_usage(ctx.usage_tracker)
            st.rerun()


if __name__ == "__main__":
    main()
