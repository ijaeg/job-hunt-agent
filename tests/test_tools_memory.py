"""Tests for :mod:`job_hunt_agent.tools.memory` (FR-15).

Related: FR-15 AC1, D-6
"""

from __future__ import annotations

import json
from typing import Any

from conftest import run_tool_turn
from langgraph.store.memory import InMemoryStore

from job_hunt_agent.context import AgentContext
from job_hunt_agent.models import Profile
from job_hunt_agent.tools.memory import memory_key, remember


def _profile() -> Profile:
    return Profile(
        skills=["Python"],
        seniority="senior",
        location="Hamburg",
        radius_km=25,
        remote_preference="hybrid",
        german_level="basic",
        english_level="native",
    )


class FakeSource:
    def search(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def get_details(self, referenznummer: str) -> Any:
        raise NotImplementedError


def _context() -> AgentContext:
    return AgentContext(
        job_source=FakeSource(), profile=_profile(), extraction_model=None, conn=None
    )


def _tool_result_content(result: dict[str, Any]) -> dict[str, Any]:
    for message in result["messages"]:
        if message.__class__.__name__ == "ToolMessage":
            return json.loads(message.content)
    raise AssertionError("no ToolMessage in result")


def test_remember_stores_an_excluded_employer() -> None:
    """FR-15 AC1: the item lands in the store, namespaced per user (D-6)."""
    store = InMemoryStore()
    run_tool_turn(
        [remember],
        [
            [
                {
                    "name": "remember",
                    "args": {"kind": "excluded_employer", "value": "Acme Staffing GmbH"},
                }
            ],
            "done",
        ],
        _context(),
        initial_state={"user_id": "alex"},
        store=store,
    )
    key = memory_key("excluded_employer", "Acme Staffing GmbH")
    item = store.get(("memories", "alex"), key)
    assert item is not None
    assert item.value["kind"] == "excluded_employer"
    assert item.value["value"] == "Acme Staffing GmbH"


def test_remember_is_idempotent_by_kind_and_value() -> None:
    """Saving the same item twice updates the one entry, not a duplicate."""
    store = InMemoryStore()
    args = {"name": "remember", "args": {"kind": "preference", "value": "remote only"}}
    run_tool_turn(
        [remember],
        [[args], "ok"],
        _context(),
        initial_state={"user_id": "alex"},
        store=store,
        thread_id="t1",
    )
    run_tool_turn(
        [remember],
        [[args], "ok"],
        _context(),
        initial_state={"user_id": "alex"},
        store=store,
        thread_id="t2",
    )
    items = store.search(("memories", "alex"))
    assert len(items) == 1


def test_remember_rejects_unknown_kind() -> None:
    """An unknown ``kind`` is rejected without writing anything."""
    store = InMemoryStore()
    result = run_tool_turn(
        [remember],
        [[{"name": "remember", "args": {"kind": "note", "value": "x"}}], "done"],
        _context(),
        initial_state={"user_id": "alex"},
        store=store,
    )
    content = _tool_result_content(result)
    assert content["result"] is None
    assert "kind" in content["not_applicable_reason"].lower()
    assert store.search(("memories", "alex")) == []


def test_remember_isolates_memories_per_user() -> None:
    """Two users' memories do not collide (same kind/value, different namespace)."""
    store = InMemoryStore()
    args = {"name": "remember", "args": {"kind": "preference", "value": "hybrid only"}}
    run_tool_turn(
        [remember],
        [[args], "ok"],
        _context(),
        initial_state={"user_id": "alex"},
        store=store,
        thread_id="t1",
    )
    run_tool_turn(
        [remember],
        [[args], "ok"],
        _context(),
        initial_state={"user_id": "sam"},
        store=store,
        thread_id="t2",
    )
    assert len(store.search(("memories", "alex"))) == 1
    assert len(store.search(("memories", "sam"))) == 1
