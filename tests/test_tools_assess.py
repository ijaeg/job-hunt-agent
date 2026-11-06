"""Tests for :mod:`job_hunt_agent.tools.assess` (FR-05).

Related: FR-05 AC1-AC6, FR-06, spec §7, D-4
"""

from __future__ import annotations

import json
from typing import Any

from conftest import run_tool_turn
from langgraph.store.memory import InMemoryStore

from job_hunt_agent import config
from job_hunt_agent.ba_client import BAJobNotFoundError
from job_hunt_agent.context import AgentContext
from job_hunt_agent.models import JobDetails, JobRequirements, Profile, Requirement
from job_hunt_agent.tools.assess import assess_fit, drop_non_verbatim_evidence


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
    def __init__(self, details_by_ref: dict[str, JobDetails | Exception]) -> None:
        self.details_by_ref = details_by_ref
        self.calls: list[str] = []

    def search(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def get_details(self, referenznummer: str) -> JobDetails:
        self.calls.append(referenznummer)
        outcome = self.details_by_ref[referenznummer]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeExtractionModel:
    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def with_structured_output(self, _schema: Any) -> FakeExtractionModel:
        return self

    def invoke(self, messages: list[Any]) -> Any:
        content = messages[0].content
        self.calls.append(content)
        for ref, response in self.responses.items():
            if f"referenznummer: {ref}" in content:
                if isinstance(response, Exception):
                    raise response
                return response
        raise AssertionError(f"no fake response configured for prompt: {content[:200]}")


def _details(ref: str, description: str) -> JobDetails:
    return JobDetails(referenznummer=ref, title="Python Dev", description=description)


def _context(source: FakeSource, model: FakeExtractionModel) -> AgentContext:
    return AgentContext(job_source=source, profile=_profile(), extraction_model=model, conn=None)


def _tool_result_content(result: dict[str, Any]) -> dict[str, Any]:
    for message in result["messages"]:
        if message.__class__.__name__ == "ToolMessage":
            return json.loads(message.content)
    raise AssertionError("no ToolMessage in result")


def _requirements(
    ref: str, skill_name: str = "Python", evidence_de: str = "Python-Kenntnisse"
) -> JobRequirements:
    return JobRequirements(
        referenznummer=ref,
        skills=[
            Requirement(
                name=skill_name,
                required=True,
                evidence_de=evidence_de,
                evidence_en="Python knowledge",
            )
        ],
        seniority="senior",
        german_level="basic",
        english_required=True,
        summary_en="A role.",
    )


def test_drop_non_verbatim_evidence_keeps_matching_quotes() -> None:
    reqs = _requirements("A-1-S", evidence_de="Python-Kenntnisse")
    filtered, dropped = drop_non_verbatim_evidence(reqs, "Wir suchen Python-Kenntnisse bei dir.")
    assert dropped == 0
    assert len(filtered.skills) == 1


def test_drop_non_verbatim_evidence_drops_non_substring_quotes() -> None:
    """FR-05 AC2: a quote that is not verbatim in the ad text is dropped and counted."""
    reqs = _requirements("A-1-S", evidence_de="Erfahrung mit Rust")
    filtered, dropped = drop_non_verbatim_evidence(reqs, "Wir suchen Python-Kenntnisse.")
    assert dropped == 1
    assert filtered.skills == []


def test_assess_fit_happy_path_updates_state() -> None:
    """A successful assessment lands in ``assessments`` and ``shortlist`` (FR-05 AC5)."""
    ad_text = "Wir suchen jemanden mit Python-Kenntnisse. " * 20
    source = FakeSource({"A-1-S": _details("A-1-S", ad_text)})
    model = FakeExtractionModel({"A-1-S": _requirements("A-1-S", evidence_de="Python-Kenntnisse")})
    result = run_tool_turn(
        [assess_fit],
        [[{"name": "assess_fit", "args": {"referenznummern": ["A-1-S"]}}], "done"],
        _context(source, model),
    )
    assert "A-1-S" in result["assessments"]
    assert result["shortlist"] == ["A-1-S"]
    content = _tool_result_content(result)
    assert content["result"]["dropped_evidence"] == 0
    assert len(content["result"]["assessed"]) == 1


def test_assess_fit_rejects_more_than_eight_listings() -> None:
    """FR-05 AC6: more than 8 listings is rejected without fetching anything."""
    source = FakeSource({})
    model = FakeExtractionModel({})
    refs = [f"REF-{i}-S" for i in range(config.MAX_LISTINGS_PER_ASSESS_FIT_CALL + 1)]
    result = run_tool_turn(
        [assess_fit],
        [[{"name": "assess_fit", "args": {"referenznummern": refs}}], "done"],
        _context(source, model),
    )
    content = _tool_result_content(result)
    assert content["result"] is None
    assert "8" in content["not_applicable_reason"]
    assert source.calls == []


def test_assess_fit_counts_dropped_evidence() -> None:
    """FR-05 AC2: a non-verbatim evidence quote is dropped and counted."""
    ad_text = "Wir suchen jemanden mit guten Python-Kenntnissen."
    source = FakeSource({"A-1-S": _details("A-1-S", ad_text)})
    model = FakeExtractionModel(
        {"A-1-S": _requirements("A-1-S", evidence_de="Dieser Satz steht nicht in der Anzeige.")}
    )
    result = run_tool_turn(
        [assess_fit],
        [[{"name": "assess_fit", "args": {"referenznummern": ["A-1-S"]}}], "done"],
        _context(source, model),
    )
    content = _tool_result_content(result)
    assert content["result"]["dropped_evidence"] == 1
    assessment = result["assessments"]["A-1-S"]
    assert assessment.rubric["skills"] == "unknown"


def test_assess_fit_skips_listing_with_failed_details_fetch() -> None:
    """A 404 on one listing is noted and skipped; other listings still get assessed."""
    ad_text = "Wir suchen jemanden mit Python-Kenntnisse. " * 20
    source = FakeSource({"A-1-S": BAJobNotFoundError("gone"), "B-2-S": _details("B-2-S", ad_text)})
    model = FakeExtractionModel({"B-2-S": _requirements("B-2-S", evidence_de="Python-Kenntnisse")})
    result = run_tool_turn(
        [assess_fit],
        [[{"name": "assess_fit", "args": {"referenznummern": ["A-1-S", "B-2-S"]}}], "done"],
        _context(source, model),
    )
    assert "A-1-S" not in result["assessments"]
    assert "B-2-S" in result["assessments"]
    content = _tool_result_content(result)
    assert any("A-1-S" in note for note in content["notes"])


def test_assess_fit_skips_listing_with_failed_extraction() -> None:
    """An extraction failure is noted and skipped, not raised into the UI."""
    ad_text = "Wir suchen jemanden mit Python-Kenntnisse. " * 20
    source = FakeSource({"A-1-S": _details("A-1-S", ad_text)})
    model = FakeExtractionModel({"A-1-S": RuntimeError("model unavailable")})
    result = run_tool_turn(
        [assess_fit],
        [[{"name": "assess_fit", "args": {"referenznummern": ["A-1-S"]}}], "done"],
        _context(source, model),
    )
    assert "A-1-S" not in result["assessments"]
    content = _tool_result_content(result)
    assert any("A-1-S" in note for note in content["notes"])


def test_assess_fit_applies_excluded_employer_from_memory() -> None:
    """FR-15 AC4: an employer excluded in long-term memory triggers a hard exclusion."""
    ad_text = "Wir suchen jemanden mit Python-Kenntnisse. " * 20
    details = JobDetails(
        referenznummer="A-1-S",
        title="Python Dev",
        employer="Acme Staffing GmbH",
        description=ad_text,
    )
    source = FakeSource({"A-1-S": details})
    model = FakeExtractionModel({"A-1-S": _requirements("A-1-S", evidence_de="Python-Kenntnisse")})
    store = InMemoryStore()
    store.put(
        ("memories", "alex"), "k1", {"kind": "excluded_employer", "value": "Acme Staffing GmbH"}
    )
    result = run_tool_turn(
        [assess_fit],
        [[{"name": "assess_fit", "args": {"referenznummern": ["A-1-S"]}}], "done"],
        _context(source, model),
        initial_state={"user_id": "alex"},
        store=store,
    )
    assessment = result["assessments"]["A-1-S"]
    assert assessment.category == "excluded"
    assert any("excluded by you" in r for r in assessment.exclusion_reasons)
