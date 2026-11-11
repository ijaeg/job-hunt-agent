"""Tests for :mod:`job_hunt_agent.tools.tracker` (FR-09).

Related: FR-09 AC1-AC3
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from conftest import run_tool_turn

from job_hunt_agent import storage
from job_hunt_agent.context import AgentContext
from job_hunt_agent.models import JobSummary, Profile, TrackerEntry
from job_hunt_agent.tools.tracker import list_tracker, save_to_tracker, validate_follow_up_date


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
        raise AssertionError("get_details should not be called when a summary is cached")


@pytest.fixture
def conn(tmp_path: Path) -> Any:
    return storage.get_connection(str(tmp_path / "test.sqlite"))


def _context(conn: Any) -> AgentContext:
    return AgentContext(
        job_source=FakeSource(), profile=_profile(), extraction_model=None, conn=conn
    )


def _tool_result_content(result: dict[str, Any]) -> dict[str, Any]:
    for message in result["messages"]:
        if message.__class__.__name__ == "ToolMessage":
            return json.loads(message.content)
    raise AssertionError("no ToolMessage in result")


def test_validate_follow_up_date_accepts_today() -> None:
    parsed, error = validate_follow_up_date(date.today().isoformat())
    assert error is None
    assert parsed == date.today()


def test_validate_follow_up_date_rejects_the_past() -> None:
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    parsed, error = validate_follow_up_date(yesterday)
    assert parsed is None
    assert error is not None
    assert "today or later" in error


def test_validate_follow_up_date_rejects_malformed_input() -> None:
    parsed, error = validate_follow_up_date("not-a-date")
    assert parsed is None
    assert "not a valid date" in error  # type: ignore[operator]


def test_validate_follow_up_date_accepts_none() -> None:
    assert validate_follow_up_date(None) == (None, None)


def test_save_to_tracker_writes_and_returns_the_entry(conn: Any) -> None:
    """FR-09 AC1: the entry is written and returned with its fields."""
    result = run_tool_turn(
        [save_to_tracker],
        [
            [
                {
                    "name": "save_to_tracker",
                    "args": {"referenznummer": "A-1-S", "status": "saved"},
                }
            ],
            "done",
        ],
        _context(conn),
        initial_state={
            "user_id": "alex",
            "summaries": {"A-1-S": JobSummary(referenznummer="A-1-S", title="Python Dev")},
        },
    )
    content = _tool_result_content(result)
    assert content["result"]["status"] == "saved"
    stored = storage.get_tracker_entry(conn, "alex", "A-1-S")
    assert stored is not None
    assert stored.title == "Python Dev"


def test_save_to_tracker_is_idempotent(conn: Any) -> None:
    """FR-09 AC1: saving the same listing twice updates, not duplicates."""
    call = {
        "name": "save_to_tracker",
        "args": {"referenznummer": "A-1-S", "status": "saved"},
    }
    run_tool_turn(
        [save_to_tracker],
        [[call], "ok"],
        _context(conn),
        initial_state={
            "user_id": "alex",
            "summaries": {"A-1-S": JobSummary(referenznummer="A-1-S", title="Python Dev")},
        },
        thread_id="t1",
    )
    call2 = {
        "name": "save_to_tracker",
        "args": {"referenznummer": "A-1-S", "status": "applied"},
    }
    run_tool_turn(
        [save_to_tracker],
        [[call2], "ok"],
        _context(conn),
        initial_state={
            "user_id": "alex",
            "summaries": {"A-1-S": JobSummary(referenznummer="A-1-S", title="Python Dev")},
        },
        thread_id="t2",
    )
    entries = storage.list_tracker_entries(conn, "alex")
    assert len(entries) == 1
    assert entries[0].status == "applied"


def test_save_to_tracker_rejects_invalid_follow_up_date(conn: Any) -> None:
    """FR-09 AC2: an invalid date returns ``not_applicable_reason``, writes nothing."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    result = run_tool_turn(
        [save_to_tracker],
        [
            [
                {
                    "name": "save_to_tracker",
                    "args": {
                        "referenznummer": "A-1-S",
                        "status": "saved",
                        "follow_up_date": yesterday,
                    },
                }
            ],
            "done",
        ],
        _context(conn),
        initial_state={
            "user_id": "alex",
            "summaries": {"A-1-S": JobSummary(referenznummer="A-1-S", title="Python Dev")},
        },
    )
    content = _tool_result_content(result)
    assert content["result"] is None
    assert "today or later" in content["not_applicable_reason"]
    assert storage.get_tracker_entry(conn, "alex", "A-1-S") is None


def test_save_to_tracker_rejects_invalid_status(conn: Any) -> None:
    """An unknown status is rejected cleanly."""
    result = run_tool_turn(
        [save_to_tracker],
        [
            [{"name": "save_to_tracker", "args": {"referenznummer": "A-1-S", "status": "maybe"}}],
            "done",
        ],
        _context(conn),
        initial_state={
            "user_id": "alex",
            "summaries": {"A-1-S": JobSummary(referenznummer="A-1-S", title="Python Dev")},
        },
    )
    content = _tool_result_content(result)
    assert content["result"] is None
    assert "status" in content["not_applicable_reason"].lower()


# ---------------------------------------------------------------------------
# list_tracker (FR-12 AC1)
# ---------------------------------------------------------------------------


def _entry(user_id: str, referenznummer: str, title: str = "Python Dev") -> TrackerEntry:
    now = datetime.now(UTC)
    return TrackerEntry(
        user_id=user_id,
        referenznummer=referenznummer,
        title=title,
        employer="Acme",
        url=None,
        status="saved",
        follow_up_date=date(2030, 1, 1),
        note="some note",
        created_at=now,
        updated_at=now,
    )


def test_list_tracker_returns_the_users_entries(conn: Any) -> None:
    """FR-12 AC1: the agent can read back referenznummer/title/employer/status/follow-up."""
    storage.save_tracker_entry(conn, _entry("alex", "A-1-S"))
    result = run_tool_turn(
        [list_tracker],
        [[{"name": "list_tracker", "args": {}}], "done"],
        _context(conn),
        initial_state={"user_id": "alex"},
    )
    content = _tool_result_content(result)
    entries = content["result"]["entries"]
    assert entries == [
        {
            "referenznummer": "A-1-S",
            "title": "Python Dev",
            "employer": "Acme",
            "status": "saved",
            "follow_up_date": "2030-01-01",
        }
    ]


def test_list_tracker_never_includes_the_free_text_note(conn: Any) -> None:
    """Only the fields decided in WP-12 are exposed - never the free-text note."""
    storage.save_tracker_entry(conn, _entry("alex", "A-1-S"))
    result = run_tool_turn(
        [list_tracker],
        [[{"name": "list_tracker", "args": {}}], "done"],
        _context(conn),
        initial_state={"user_id": "alex"},
    )
    content = _tool_result_content(result)
    assert "note" not in content["result"]["entries"][0]


def test_list_tracker_is_empty_for_a_user_with_no_entries(conn: Any) -> None:
    result = run_tool_turn(
        [list_tracker],
        [[{"name": "list_tracker", "args": {}}], "done"],
        _context(conn),
        initial_state={"user_id": "alex"},
    )
    content = _tool_result_content(result)
    assert content["result"]["entries"] == []


def test_list_tracker_is_isolated_per_user(conn: Any) -> None:
    storage.save_tracker_entry(conn, _entry("alex", "A-1-S"))
    storage.save_tracker_entry(conn, _entry("sam", "B-2-S"))
    result = run_tool_turn(
        [list_tracker],
        [[{"name": "list_tracker", "args": {}}], "done"],
        _context(conn),
        initial_state={"user_id": "sam"},
    )
    content = _tool_result_content(result)
    refs = [e["referenznummer"] for e in content["result"]["entries"]]
    assert refs == ["B-2-S"]
