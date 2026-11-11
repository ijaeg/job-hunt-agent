"""Tests for :mod:`job_hunt_agent.tools.search` (FR-02).

Related: FR-02 AC1-AC7, FR-03 AC2, FR-20 AC1
"""

from __future__ import annotations

import json
from typing import Any

from conftest import run_tool_turn

from job_hunt_agent.ba_client import BAUnavailableError
from job_hunt_agent.context import AgentContext
from job_hunt_agent.middleware.limits import SearchCallLimitMiddleware
from job_hunt_agent.models import JobSummary, Profile
from job_hunt_agent.tools.search import search_jobs


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
    def __init__(
        self, summaries: list[JobSummary], total: int, notes: list[str] | None = None
    ) -> None:
        self.summaries = summaries
        self.total = total
        self.notes = notes or []
        self.calls: list[dict[str, Any]] = []
        self.raise_error: Exception | None = None

    def search(
        self,
        keywords: str,
        location: str,
        radius_km: int = 25,
        published_within_days: int = 28,
        exclude_temp_agency: bool = True,
        page: int = 1,
    ) -> tuple[list[JobSummary], int, list[str]]:
        self.calls.append(
            {
                "keywords": keywords,
                "location": location,
                "radius_km": radius_km,
                "published_within_days": published_within_days,
                "exclude_temp_agency": exclude_temp_agency,
                "page": page,
            }
        )
        if self.raise_error:
            raise self.raise_error
        return self.summaries, self.total, self.notes

    def get_details(self, referenznummer: str) -> Any:
        raise NotImplementedError


def _context(source: FakeSource) -> AgentContext:
    return AgentContext(job_source=source, profile=_profile(), extraction_model=None, conn=None)


def _tool_result_content(result: dict[str, Any]) -> dict[str, Any]:
    for message in result["messages"]:
        if message.__class__.__name__ == "ToolMessage":
            return json.loads(message.content)
    raise AssertionError("no ToolMessage in result")


def test_search_jobs_returns_listings_and_updates_seen_refs() -> None:
    """A successful search populates ``seen_refs`` and ``summaries`` (FR-02 AC5)."""
    source = FakeSource([JobSummary(referenznummer="A-1-S", title="Python Dev")], total=1)
    result = run_tool_turn(
        [search_jobs],
        [[{"name": "search_jobs", "args": {"keywords": "Python", "location": "Hamburg"}}], "done"],
        _context(source),
    )
    assert result["seen_refs"] == ["A-1-S"]
    assert "A-1-S" in result["summaries"]
    content = _tool_result_content(result)
    assert content["result"]["total"] == 1
    assert content["result"]["listings"][0]["seen"] is False


def test_search_jobs_marks_previously_seen_listings() -> None:
    """A listing already in ``seen_refs`` comes back with ``seen: true`` (FR-02 AC5)."""
    source = FakeSource([JobSummary(referenznummer="A-1-S", title="Python Dev")], total=1)
    result = run_tool_turn(
        [search_jobs],
        [[{"name": "search_jobs", "args": {"keywords": "Python", "location": "Hamburg"}}], "done"],
        _context(source),
        initial_state={"seen_refs": ["A-1-S"]},
    )
    content = _tool_result_content(result)
    assert content["result"]["listings"][0]["seen"] is True


def test_search_jobs_no_results_is_normal() -> None:
    """FR-02 AC4: an empty result is a normal ``ToolResult``, not an error."""
    source = FakeSource([], total=0)
    result = run_tool_turn(
        [search_jobs],
        [
            [{"name": "search_jobs", "args": {"keywords": "Nonexistent", "location": "Nowhere"}}],
            "done",
        ],
        _context(source),
    )
    content = _tool_result_content(result)
    assert content["not_applicable_reason"] is None
    assert content["result"]["total"] == 0


def test_search_jobs_forwards_clamp_notes() -> None:
    """Clamping/sanitizing notes from ``ba_client`` reach the model (FR-02 AC6, AC7)."""
    source = FakeSource([], total=0, notes=["radius_km clamped from 500 to 200"])
    result = run_tool_turn(
        [search_jobs],
        [[{"name": "search_jobs", "args": {"keywords": "Python", "location": "Hamburg"}}], "done"],
        _context(source),
    )
    content = _tool_result_content(result)
    assert content["notes"] == ["radius_km clamped from 500 to 200"]


def test_search_jobs_ba_error_is_not_applicable_reason_not_exception() -> None:
    """FR-21 AC3 / spec §8: a client error never raises into the UI."""
    source = FakeSource([], total=0)
    source.raise_error = BAUnavailableError("boom")
    result = run_tool_turn(
        [search_jobs],
        [[{"name": "search_jobs", "args": {"keywords": "Python", "location": "Hamburg"}}], "done"],
        _context(source),
    )
    content = _tool_result_content(result)
    assert content["result"] is None
    assert "job board" in content["not_applicable_reason"].lower()


class _DistinctRefsPerCallSource:
    """Returns a different referenznummer on each call (keywords-derived)."""

    def search(self, keywords: str, **_kwargs: Any) -> tuple[list[JobSummary], int, list[str]]:
        ref = f"{keywords.upper()}-1-S"
        return [JobSummary(referenznummer=ref, title=f"{keywords} Dev")], 1, []

    def get_details(self, referenznummer: str) -> Any:
        raise NotImplementedError


def test_two_parallel_search_jobs_calls_both_update_state() -> None:
    """D-19: two search_jobs calls proposed in one step no longer crash.

    Reproduces the WP-10 finding (``InvalidUpdateError`` on ``seen_refs``)
    with the now-merged state: both searches' results end up in
    ``seen_refs``/``summaries``, no duplicates.
    """
    result = run_tool_turn(
        [search_jobs],
        [
            [
                {"name": "search_jobs", "args": {"keywords": "python", "location": "Hamburg"}},
                {"name": "search_jobs", "args": {"keywords": "java", "location": "Berlin"}},
            ],
            "done",
        ],
        _context(_DistinctRefsPerCallSource()),
        middleware=[SearchCallLimitMiddleware()],
    )
    assert sorted(result["seen_refs"]) == ["JAVA-1-S", "PYTHON-1-S"]
    assert len(result["seen_refs"]) == len(set(result["seen_refs"]))
    assert set(result["summaries"]) == set(result["seen_refs"])
