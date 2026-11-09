"""Streamlit entry point for the core journey (spec §11, NFR-01).

Layout and wiring only (NFR-04): no prompt text, no business logic. Pure
helpers for the shortlist cards live in ``src/job_hunt_agent/ui_view.py``;
the agent, tools and middleware live in ``src/job_hunt_agent/``. Start with
``uv run streamlit run app.py``.

Scope (WP-04): the core journey only - chat, shortlist cards, "Save to
tracker", the approval flow, and demo-mode switching. The tracker page,
memory page, profile form, thread list and developer settings are later
work packages.

Related: FR-01 AC1, FR-07, FR-09, FR-10 AC2, FR-10 AC5, FR-16, FR-19 AC1-AC2,
NFR-01, NFR-03, NFR-04, D-5, D-10, D-11
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import streamlit as st
import yaml
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from job_hunt_agent import config, storage, ui_view
from job_hunt_agent.agent import build_agent
from job_hunt_agent.ba_client import BAClient, FixtureSource, JobSource
from job_hunt_agent.context import AgentContext
from job_hunt_agent.llm import build_real_model
from job_hunt_agent.models import Profile

#: No authentication yet (spec §2.2); every run is this one demo user.
USER_ID = "alex"

_PROFILE_SEED_PATH = config.PROJECT_ROOT / "data" / "samples" / "profile_alex.yaml"

_STATUS_LABELS: dict[str, str] = {
    "search_jobs": "Searching the job board…",
    "assess_fit": "Assessing fit…",
}

st.set_page_config(page_title="Job Hunt Agent", layout="wide")


# ---------------------------------------------------------------------------
# A scripted model for tests only (``JOB_HUNT_FAKE_MODEL=1``), never active
# otherwise. Mirrors ``spikes/hitl_app.py``'s ``ScriptedChatModel`` (D-5) -
# referenced, not imported, per that work package's instruction. Only the
# main ReAct loop is faked this way; ``assess_fit``'s separate extraction
# model is not exercised by this work package's AppTest scenarios.
# ---------------------------------------------------------------------------


class _ScriptedModel:
    """Pops the next turn from ``st.session_state["_scripted_turns"]``; no network call."""

    def bind_tools(self, _tools: Any, **_kwargs: Any) -> _ScriptedModel:
        return self

    def invoke(self, _messages: list[Any], **_kwargs: Any) -> AIMessage:
        queue: list[Any] = st.session_state.get("_scripted_turns", [])
        if not queue:
            return AIMessage(content="(scripted model: no more turns)")
        spec = queue.pop(0)
        st.session_state["_scripted_turns"] = queue
        if isinstance(spec, str):
            return AIMessage(content=spec)
        tool_calls = [
            {"name": call["name"], "args": call["args"], "id": f"call_{i}_{call['name']}"}
            for i, call in enumerate(spec)
        ]
        return AIMessage(content="", tool_calls=tool_calls)


# ---------------------------------------------------------------------------
# Cached resources (D-5, FR-10 AC5): built once per process, not per rerun.
# ---------------------------------------------------------------------------


@st.cache_resource
def get_connection(db_path: str) -> Any:
    """One shared SQLite connection for the checkpointer, store, tracker and profile (D-5)."""
    return storage.get_connection(db_path)


@st.cache_resource
def get_model() -> Any:
    if os.getenv("JOB_HUNT_FAKE_MODEL") == "1":
        return _ScriptedModel()
    return build_real_model()


@st.cache_resource
def get_fixture_source() -> FixtureSource:
    return FixtureSource()


@st.cache_resource
def get_live_source() -> BAClient:
    return BAClient()


def load_or_seed_profile(conn: Any, user_id: str) -> Profile:
    """Loads the stored profile, or seeds it from the demo profile once (FR-14 AC1)."""
    profile = storage.load_profile(conn, user_id)
    if profile is not None:
        return profile
    data = yaml.safe_load(_PROFILE_SEED_PATH.read_text(encoding="utf-8"))
    profile = Profile.model_validate(data)
    storage.save_profile(conn, user_id, profile)
    return profile


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


def run_turn(agent: Any, cfg: dict[str, Any], ctx: AgentContext, payload: Any) -> None:
    """Runs one agent turn (or a resume), showing progress labels as tool calls arrive.

    Never lets an exception reach the page (invariant 7, CLAUDE.md): a
    failure becomes a friendly ``st.error`` and the chat stays usable.

    Related: FR-16 AC2, invariant 7
    """
    counts: dict[str, int] = {}
    seen_tool_call_ids: set[str] = set()
    try:
        with st.status("Thinking…", expanded=False) as status:
            for step in agent.stream(payload, config=cfg, context=ctx, stream_mode="updates"):
                for tool_call in iter_new_tool_calls(step, seen_tool_call_ids):
                    label = _status_label(tool_call["name"], tool_call["args"], counts)
                    if label:
                        status.update(label=label)
            status.update(label="Done", state="complete")
    except Exception:  # noqa: BLE001 - never a stack trace in the UI (invariant 7)
        st.error(
            "Something went wrong while talking to the job board or the model. Please try again."
        )


# ---------------------------------------------------------------------------
# Chat history (FR-01 AC1): read from the checkpointer, never from session state.
# ---------------------------------------------------------------------------


def render_chat_history(messages: list[Any]) -> None:
    for msg in messages:
        if isinstance(msg, HumanMessage) and msg.content and msg.name != "profile_context":
            # "profile_context" (middleware/profile_context.py) is injected for the
            # model, not something the user said - never shown as a chat bubble.
            st.chat_message("user").write(str(msg.content))
        elif isinstance(msg, AIMessage) and msg.content:
            st.chat_message("assistant").write(str(msg.content))


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
        try:
            agent.invoke(Command(resume={"decisions": decisions}), config=cfg, context=ctx)
        except Exception:  # noqa: BLE001 - invariant 7
            st.error("Could not apply that decision. Please try again.")
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
                st.caption(f"✓ {match}")
        if card.gaps:
            with st.expander("Gaps"):
                for gap in card.gaps:
                    st.caption(gap)
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
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    st.title("Job Hunt Agent")

    try:
        model = get_model()
    except RuntimeError:
        # invariant 7: a missing API key is a friendly message, never a stack trace.
        st.error(f"{config.OPENROUTER_API_KEY_ENV} is not set. Add it to .env and restart.")
        st.stop()
        return

    conn = get_connection(os.getenv("DB_PATH", config.DB_PATH))
    profile = load_or_seed_profile(conn, USER_ID)

    with st.sidebar:
        demo_mode = st.toggle("Demo mode", value=True)
        if st.button("New search"):
            start_new_thread()
            st.rerun()

    job_source: JobSource
    if demo_mode:
        st.info("Demo data – not live listings")
        job_source = get_fixture_source()
    else:
        job_source = get_live_source()

    thread_id = get_or_create_thread_id()
    cfg = {"configurable": {"thread_id": thread_id}}
    ctx = AgentContext(job_source=job_source, profile=profile, extraction_model=model, conn=conn)
    agent = build_agent(model, conn)

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
        render_chat_history(messages)

        if state.interrupts:
            render_approval(agent, cfg, ctx, state.interrupts[0].value)
            return

        pending_message = st.session_state.pop("pending_message", None)
        user_input = pending_message or st.chat_input("Describe the job you're looking for...")
        if user_input:
            st.chat_message("user").write(user_input)
            run_turn(
                agent,
                cfg,
                ctx,
                {"messages": [HumanMessage(user_input)], "user_id": USER_ID},
            )
            st.rerun()


if __name__ == "__main__":
    main()
