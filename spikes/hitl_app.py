"""Spike D-5: approval with interrupt and resume in Streamlit (FR-10).

Two dummy tools, `find_item` (read) and `save_item` (write, gated by
`HumanInTheLoopMiddleware`), on a `SqliteSaver` checkpointer. Proves, before
the real agent is built:

  1. Does the interrupt survive a Streamlit rerun and an app restart?
  2. After reject, does the model propose the same call again - is it
     interrupted again?
  3. A rejection-lock middleware (spec §5.4 #4): which hook and which
     position relative to `HumanInTheLoopMiddleware` drop an already
     rejected proposal before the interrupt?
  4. SQLite connection handling across Streamlit reruns.

Findings are written up in the "D-5" section of `spikes/NOTES.md`; this file
is the executable proof.

Call:
    uv run streamlit run spikes/hitl_app.py

Set HITL_FAKE_MODEL=1 to run against a deterministic scripted model instead
of the real OpenRouter model (used by the automated AppTest in
spikes/test_hitl_app.py, so no API key or network call is needed there).
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, NotRequired

import streamlit as st
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, AgentState, HumanInTheLoopMiddleware
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from pydantic import SecretStr

from job_hunt_agent import config

#: Overridable so tests use an isolated file instead of the demo database.
_DEFAULT_DB_PATH = Path(__file__).resolve().parent / "fixtures" / "d5.sqlite"
DB_PATH = Path(os.getenv("HITL_DB_PATH", str(_DEFAULT_DB_PATH)))

# ---------------------------------------------------------------------------
# Dummy tools
# ---------------------------------------------------------------------------

_CATALOG: dict[str, str] = {
    "widget": "a small plastic widget",
    "gadget": "an electronic gadget",
    "gizmo": "a mysterious gizmo",
}


@tool
def find_item(query: str) -> dict[str, Any]:
    """Look up an item in the catalog by name. Read-only, never gated."""
    query = query.lower()
    for name, description in _CATALOG.items():
        if query in name:
            return {"name": name, "description": description}
    return {"name": None, "description": "not found"}


@tool
def save_item(name: str, note: str) -> dict[str, Any]:
    """Save an item to the tracker. A write action, gated by approval (FR-10)."""
    return {"saved": True, "name": name, "note": note}


# ---------------------------------------------------------------------------
# Rejection-lock middleware (spec §5.4 #4, FR-10 AC3)
# ---------------------------------------------------------------------------


def hash_call(name: str, args: dict[str, Any]) -> str:
    """Stable hash of a tool name and its arguments, for the rejection lock."""
    payload = json.dumps({"name": name, "args": args}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


class RejectionLockState(AgentState):
    """Adds `rejected_actions` to the agent state (spec §5.3)."""

    rejected_actions: NotRequired[list[str]]


class RejectionLockMiddleware(AgentMiddleware):
    """Drops a tool call identical to one already rejected in this thread.

    Finding of D-5: `after_model` hooks run in REVERSE middleware-list order
    (the last-listed middleware's `after_model` runs first), while
    `before_model` hooks run in forward order. So this middleware must be
    listed AFTER `HumanInTheLoopMiddleware` in `middleware=[...]` for its
    `after_model` to strip a repeated call BEFORE HITL's own `after_model`
    would otherwise raise a second interrupt for it.

    `before_model` scans the message history for HITL's reject `ToolMessage`s
    (`status == "error"`, content starting with "User rejected the tool call
    for") and records a hash of the original call into `rejected_actions`.
    `after_model` then strips any later proposal with a matching hash from the
    newest `AIMessage.tool_calls`, replacing it with the same message (same
    id, so the state reducer updates it in place) carrying an explanatory
    note instead - the agent explains rather than re-asking (FR-10 AC3).

    Related: FR-10 AC3, spec §5.3, §5.4 #4
    """

    state_schema = RejectionLockState

    def before_model(self, state: RejectionLockState, runtime: Any) -> dict[str, Any] | None:
        messages: list[BaseMessage] = state["messages"]
        call_by_id: dict[str, tuple[str, dict[str, Any]]] = {}
        for msg in messages:
            if isinstance(msg, AIMessage):
                for tc in msg.tool_calls:
                    call_by_id[tc["id"]] = (tc["name"], tc["args"])

        rejected = set(state.get("rejected_actions", []))
        before = set(rejected)
        for msg in messages:
            if (
                isinstance(msg, ToolMessage)
                and msg.status == "error"
                and "User rejected the tool call for" in str(msg.content)
            ):
                call = call_by_id.get(msg.tool_call_id)
                if call:
                    rejected.add(hash_call(*call))

        if rejected == before:
            return None
        return {"rejected_actions": sorted(rejected)}

    def after_model(self, state: RejectionLockState, runtime: Any) -> dict[str, Any] | None:
        messages: list[BaseMessage] = state["messages"]
        last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        if not last_ai or not last_ai.tool_calls:
            return None

        rejected = set(state.get("rejected_actions", []))
        if not rejected:
            return None

        kept, dropped_names = [], []
        for tc in last_ai.tool_calls:
            if hash_call(tc["name"], tc["args"]) in rejected:
                dropped_names.append(tc["name"])
            else:
                kept.append(tc)

        if not dropped_names:
            return None

        note = (
            f"\n\n(Not repeating {', '.join(dropped_names)}: this exact action was "
            "already rejected in this conversation.)"
        )
        new_ai = AIMessage(content=(last_ai.content or "") + note, tool_calls=kept, id=last_ai.id)
        return {"messages": [new_ai]}


# ---------------------------------------------------------------------------
# Model and agent
# ---------------------------------------------------------------------------


def _turn_spec_to_message(spec: str | list[dict[str, Any]]) -> AIMessage:
    """Turn one scripted-turn spec from `st.session_state["_scripted_turns"]` into a reply.

    A spec is either a plain string (a final answer) or a list of
    ``{"name": ..., "args": ...}`` dicts (one or more tool calls).
    """
    if isinstance(spec, str):
        return AIMessage(content=spec)
    tool_calls = [
        {"name": call["name"], "args": call["args"], "id": f"call_{i}_{call['name']}"}
        for i, call in enumerate(spec)
    ]
    return AIMessage(content="", tool_calls=tool_calls)


class ScriptedChatModel:
    """Deterministic stand-in for `HITL_FAKE_MODEL=1`; no network calls.

    Pops the next turn from `st.session_state["_scripted_turns"]` instead of
    holding its own queue, so the remaining script survives a Streamlit
    rerun (a fresh `ScriptedChatModel` is built on every rerun, but session
    state persists) while a brand-new `AppTest` (simulated restart) starts
    with its own, separately pre-set queue.

    Related: NFR-06 (every LLM call in tests is mocked)
    """

    def bind_tools(self, _tools: Any, **_kwargs: Any) -> ScriptedChatModel:
        return self

    def invoke(self, _messages: list[BaseMessage], **_kwargs: Any) -> AIMessage:
        queue: list[Any] = st.session_state.get("_scripted_turns", [])
        if not queue:
            return AIMessage(content="(scripted model: no more replies)")
        spec = queue.pop(0)
        st.session_state["_scripted_turns"] = queue
        return _turn_spec_to_message(spec)


def build_real_model() -> Any:
    from langchain_openai import ChatOpenAI

    api_key = os.getenv(config.OPENROUTER_API_KEY_ENV, "").strip()
    if not api_key:
        raise RuntimeError(f"{config.OPENROUTER_API_KEY_ENV} is not set.")
    return ChatOpenAI(
        model=config.CHAT_MODEL,
        base_url=config.OPENROUTER_BASE_URL,
        api_key=SecretStr(api_key),
        timeout=config.OPENROUTER_TIMEOUT_SECONDS,
        max_retries=0,
        extra_body={
            "reasoning": {"effort": config.REASONING_EFFORT},
            "provider": config.PROVIDER_PREFERENCES,
        },
    )


@st.cache_resource
def get_connection(db_path: str) -> sqlite3.Connection:
    """One shared connection across Streamlit reruns (D-5 question 4).

    `check_same_thread=False` is safe: `SqliteSaver` serialises access with
    its own lock (see the langgraph docstring). `st.cache_resource` caches
    this per Python process (keyed by `db_path`), so every rerun of the
    script reuses the same connection instead of opening a new one; clearing
    the cache (`get_connection.clear()`) and calling this again is how the
    test simulates an app restart.
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path, check_same_thread=False)


def build_agent() -> Any:
    """Build a fresh agent graph. Cheap (no network I/O at construction time),
    so it is rebuilt on every Streamlit rerun; only the SQLite connection
    (`get_connection`) is cached (D-5 question 4).
    """
    model: Any = ScriptedChatModel() if os.getenv("HITL_FAKE_MODEL") == "1" else build_real_model()
    checkpointer = SqliteSaver(get_connection(str(DB_PATH)))
    return create_agent(
        model,
        tools=[find_item, save_item],
        middleware=[
            HumanInTheLoopMiddleware(interrupt_on={"save_item": True}),
            RejectionLockMiddleware(),  # listed AFTER HITL - see the docstring above
        ],
        checkpointer=checkpointer,
    )


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------


def render_message(msg: BaseMessage) -> None:
    if isinstance(msg, HumanMessage):
        st.chat_message("user").write(str(msg.content))
    elif isinstance(msg, AIMessage):
        if msg.content:
            st.chat_message("assistant").write(str(msg.content))
        for tc in msg.tool_calls:
            st.chat_message("assistant").caption(f"-> called `{tc['name']}`({tc['args']})")
    elif isinstance(msg, ToolMessage):
        st.chat_message("assistant").caption(f"tool result: {msg.content}")


def main() -> None:
    st.set_page_config(page_title="D-5 HITL spike")
    st.title("D-5 spike: approval with interrupt and resume")

    thread_id = st.sidebar.text_input("Thread ID", value="demo-thread")
    st.sidebar.caption("Reuse the same ID after an app restart to resume the thread.")
    config_dict = {"configurable": {"thread_id": thread_id}}

    agent = build_agent()
    state = agent.get_state(config_dict)
    messages: list[BaseMessage] = state.values.get("messages", []) if state.values else []

    for msg in messages:
        render_message(msg)

    if state.interrupts:
        interrupt_value = state.interrupts[0].value
        for action in interrupt_value["action_requests"]:
            st.warning(f"Approval needed: `{action['name']}`({action['args']})")
            col1, col2, col3 = st.columns(3)
            if col1.button("Approve", key="approve"):
                agent.invoke(Command(resume={"decisions": [{"type": "approve"}]}), config_dict)
                st.rerun()
            if col2.button("Reject", key="reject"):
                agent.invoke(
                    Command(resume={"decisions": [{"type": "reject", "message": "Not now."}]}),
                    config_dict,
                )
                st.rerun()
            if col3.button("Edit note", key="edit"):
                edited = dict(action["args"])
                edited["note"] = edited.get("note", "") + " (edited by reviewer)"
                agent.invoke(
                    Command(
                        resume={
                            "decisions": [
                                {
                                    "type": "edit",
                                    "edited_action": {"name": action["name"], "args": edited},
                                }
                            ]
                        }
                    ),
                    config_dict,
                )
                st.rerun()
    else:
        user_input = st.chat_input("Ask to find or save an item...")
        if user_input:
            agent.invoke({"messages": [HumanMessage(user_input)]}, config_dict)
            st.rerun()


if __name__ == "__main__":
    main()
