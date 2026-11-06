"""Tests for :mod:`job_hunt_agent.tools.details` (FR-04).

Related: FR-04 AC1-AC5
"""

from __future__ import annotations

import json
from typing import Any

from conftest import run_tool_turn

from job_hunt_agent.ba_client import BAJobNotFoundError, BAUnavailableError
from job_hunt_agent.context import AgentContext
from job_hunt_agent.models import JobDetails, Profile
from job_hunt_agent.tools.details import get_job_details


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
    def __init__(self) -> None:
        self.details: JobDetails | None = None
        self.raise_error: Exception | None = None

    def search(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def get_details(self, referenznummer: str) -> JobDetails:
        if self.raise_error:
            raise self.raise_error
        assert self.details is not None
        return self.details


def _context(source: FakeSource) -> AgentContext:
    return AgentContext(job_source=source, profile=_profile(), extraction_model=None, conn=None)


def _tool_result_content(result: dict[str, Any]) -> dict[str, Any]:
    for message in result["messages"]:
        if message.__class__.__name__ == "ToolMessage":
            return json.loads(message.content)
    raise AssertionError("no ToolMessage in result")


def test_get_job_details_returns_cleaned_details() -> None:
    """A successful fetch returns the (already-cleaned) details (FR-04 AC2)."""
    source = FakeSource()
    source.details = JobDetails(
        referenznummer="A-1-S", title="Python Dev", description="x" * 1000, low_evidence=False
    )
    result = run_tool_turn(
        [get_job_details],
        [[{"name": "get_job_details", "args": {"referenznummer": "A-1-S"}}], "done"],
        _context(source),
    )
    content = _tool_result_content(result)
    assert content["result"]["referenznummer"] == "A-1-S"
    assert content["not_applicable_reason"] is None


def test_get_job_details_404_removes_listing_from_shortlist() -> None:
    """FR-04 AC3: a 404 reports unavailability and drops the ref from the shortlist."""
    source = FakeSource()
    source.raise_error = BAJobNotFoundError("gone")
    result = run_tool_turn(
        [get_job_details],
        [[{"name": "get_job_details", "args": {"referenznummer": "A-1-S"}}], "done"],
        _context(source),
        initial_state={"shortlist": ["A-1-S", "B-2-S"]},
    )
    content = _tool_result_content(result)
    assert content["result"] is None
    assert "no longer available" in content["not_applicable_reason"].lower()
    assert result["shortlist"] == ["B-2-S"]


def test_get_job_details_unavailable_is_not_applicable_reason() -> None:
    """A transient BA failure never raises into the UI (FR-21 AC3, spec §8)."""
    source = FakeSource()
    source.raise_error = BAUnavailableError("boom")
    result = run_tool_turn(
        [get_job_details],
        [[{"name": "get_job_details", "args": {"referenznummer": "A-1-S"}}], "done"],
        _context(source),
    )
    content = _tool_result_content(result)
    assert content["result"] is None
    assert "job board" in content["not_applicable_reason"].lower()
