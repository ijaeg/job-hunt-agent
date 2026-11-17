"""Tests for the pure scoring logic of ``eval/run_trajectory_eval.py`` (spec §9.2, WP-15a).

Fixed fake tool-call data only - no model call, no agent, no SQLite (CLAUDE.md
invariant 5, NFR-05). Loaded by file path (like ``tests/test_run_fit_eval.py``
loads ``eval/run_fit_eval.py``) since ``eval/run_trajectory_eval.py`` is a
script, not a package member.

Related: spec §9.2, NFR-05, invariant 5, invariant 6, WP-15a
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from types import ModuleType

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "eval" / "run_trajectory_eval.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_trajectory_eval_under_test", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


traj = _load_module()


def _call(name: str, **args: object) -> dict[str, object]:
    return {"name": name, "args": args}


# ---------------------------------------------------------------------------
# tool_names / check_required_forbidden
# ---------------------------------------------------------------------------


def test_tool_names_returns_distinct_names() -> None:
    calls = [_call("search_jobs"), _call("search_jobs"), _call("assess_fit")]
    assert traj.tool_names(calls) == {"search_jobs", "assess_fit"}


def test_check_required_forbidden_passes_when_required_present_and_forbidden_absent() -> None:
    calls = [_call("search_jobs"), _call("assess_fit")]
    passed, missing, forbidden_present = traj.check_required_forbidden(
        calls, ["search_jobs", "assess_fit"], ["save_to_tracker"]
    )
    assert passed is True
    assert missing == []
    assert forbidden_present == []


def test_check_required_forbidden_reports_missing_required() -> None:
    calls = [_call("search_jobs")]
    passed, missing, forbidden_present = traj.check_required_forbidden(
        calls, ["search_jobs", "assess_fit"], []
    )
    assert passed is False
    assert missing == ["assess_fit"]
    assert forbidden_present == []


def test_check_required_forbidden_reports_forbidden_present() -> None:
    calls = [_call("search_jobs"), _call("remember")]
    passed, missing, forbidden_present = traj.check_required_forbidden(
        calls, ["search_jobs"], ["remember", "save_to_tracker"]
    )
    assert passed is False
    assert missing == []
    assert forbidden_present == ["remember"]


# ---------------------------------------------------------------------------
# parse_key_argument_rule
# ---------------------------------------------------------------------------


def test_parse_key_argument_rule_contains() -> None:
    assert traj.parse_key_argument_rule("contains (case-insensitive)") == ("contains", False)


def test_parse_key_argument_rule_equals() -> None:
    assert traj.parse_key_argument_rule("equals") == ("equals", False)


def test_parse_key_argument_rule_list_contains() -> None:
    assert traj.parse_key_argument_rule("list contains") == ("list_contains", False)


def test_parse_key_argument_rule_equals_run_date_plus_soft() -> None:
    kind, soft = traj.parse_key_argument_rule("equals run_date + 7 days (soft - report mismatch)")
    assert kind == "equals_run_date_plus"
    assert soft is True


def test_parse_key_argument_rule_soft_equals() -> None:
    kind, soft = traj.parse_key_argument_rule("equals (soft - report mismatch, do not fail)")
    assert kind == "equals"
    assert soft is True


def test_parse_key_argument_rule_rejects_unknown_text() -> None:
    import pytest

    with pytest.raises(ValueError, match="unrecognised"):
        traj.parse_key_argument_rule("something else entirely")


# ---------------------------------------------------------------------------
# find_key_argument_call / check_key_argument
# ---------------------------------------------------------------------------


def test_find_key_argument_call_first_across_all_turns() -> None:
    turns = [[_call("search_jobs", location="Hamburg")], [_call("search_jobs", location="Berlin")]]
    found = traj.find_key_argument_call(turns, "search_jobs", "first")
    assert found is not None
    assert found["args"]["location"] == "Hamburg"


def test_find_key_argument_call_restricted_to_named_turn() -> None:
    turns = [[_call("search_jobs", location="Hamburg")], [_call("search_jobs", location="Berlin")]]
    found = traj.find_key_argument_call(turns, "search_jobs", "first (turn 2)")
    assert found is not None
    assert found["args"]["location"] == "Berlin"


def test_find_key_argument_call_returns_none_when_tool_never_called() -> None:
    turns = [[_call("search_jobs", location="Hamburg")]]
    assert traj.find_key_argument_call(turns, "assess_fit", "first") is None


def test_check_key_argument_contains_pass_and_fail() -> None:
    turns = [[_call("search_jobs", location="München, Bayern")]]
    key_arg = {
        "tool": "search_jobs",
        "call": "first",
        "field": "location",
        "rule": "contains (case-insensitive)",
        "value": "münchen",
    }
    passed, soft, detail = traj.check_key_argument(turns, key_arg, date(2026, 11, 17))
    assert passed is True
    assert soft is False
    assert "location=" in detail

    key_arg["value"] = "hamburg"
    passed, _, _ = traj.check_key_argument(turns, key_arg, date(2026, 11, 17))
    assert passed is False


def test_check_key_argument_equals() -> None:
    turns = [[_call("save_to_tracker", referenznummer="17338-c2de5ff0cd55000215-S")]]
    key_arg = {
        "tool": "save_to_tracker",
        "call": "first",
        "field": "referenznummer",
        "rule": "equals",
        "value": "17338-c2de5ff0cd55000215-S",
    }
    passed, soft, _ = traj.check_key_argument(turns, key_arg, date(2026, 11, 17))
    assert passed is True
    assert soft is False


def test_check_key_argument_list_contains() -> None:
    turns = [[_call("assess_fit", referenznummern=["a-S", "19913-3074751792188001-S"])]]
    key_arg = {
        "tool": "assess_fit",
        "call": "first",
        "field": "referenznummern",
        "rule": "list contains",
        "value": "19913-3074751792188001-S",
    }
    passed, _, _ = traj.check_key_argument(turns, key_arg, date(2026, 11, 17))
    assert passed is True


def test_check_key_argument_equals_run_date_plus_days() -> None:
    turns = [[_call("save_to_tracker", follow_up_date="2026-11-24")]]
    key_arg = {
        "tool": "save_to_tracker",
        "call": "first",
        "field": "follow_up_date",
        "rule": "equals run_date + 7 days (soft - report mismatch, do not fail the run on it)",
        "value": "run_date+7d",
    }
    passed, soft, detail = traj.check_key_argument(turns, key_arg, date(2026, 11, 17))
    assert passed is True
    assert soft is True
    assert "2026-11-24" in detail


def test_check_key_argument_fails_closed_when_tool_never_called() -> None:
    turns: list[list[dict[str, object]]] = [[]]
    key_arg = {
        "tool": "save_to_tracker",
        "call": "first",
        "field": "referenznummer",
        "rule": "equals",
        "value": "17338-c2de5ff0cd55000215-S",
    }
    passed, soft, detail = traj.check_key_argument(turns, key_arg, date(2026, 11, 17))
    assert passed is False
    assert soft is False
    assert "never called" in detail


# ---------------------------------------------------------------------------
# check_order_constraints
# ---------------------------------------------------------------------------


def test_order_constraint_minimum_search_calls_pass_and_fail() -> None:
    constraints = ["at least 2 search_jobs calls in turn 1 (refinement)"]
    two_calls = [[_call("search_jobs"), _call("search_jobs")]]
    one_call = [[_call("search_jobs")]]
    assert traj.check_order_constraints(constraints, two_calls) == (True, [])
    passed, failures = traj.check_order_constraints(constraints, one_call)
    assert passed is False
    assert len(failures) == 1


def test_order_constraint_search_precedes_details() -> None:
    constraints = ["the first search_jobs call precedes every get_job_details/assess_fit call"]
    good = [[_call("search_jobs"), _call("get_job_details"), _call("assess_fit")]]
    bad = [[_call("get_job_details"), _call("search_jobs")]]
    assert traj.check_order_constraints(constraints, good) == (True, [])
    passed, _ = traj.check_order_constraints(constraints, bad)
    assert passed is False


def test_order_constraint_referenznummer_appears_in_details_or_assess() -> None:
    constraints = [
        "referenznummer FIKTIV-0000000001-S appears as an argument of a "
        "get_job_details call OR in the referenznummern list of an assess_fit call"
    ]
    via_details = [[_call("get_job_details", referenznummer="FIKTIV-0000000001-S")]]
    via_assess = [[_call("assess_fit", referenznummern=["FIKTIV-0000000001-S"])]]
    missing = [[_call("get_job_details", referenznummer="some-other-S")]]
    assert traj.check_order_constraints(constraints, via_details) == (True, [])
    assert traj.check_order_constraints(constraints, via_assess) == (True, [])
    passed, failures = traj.check_order_constraints(constraints, missing)
    assert passed is False
    assert len(failures) == 1


def test_order_constraint_unrecognised_text_fails_closed() -> None:
    passed, failures = traj.check_order_constraints(
        ["some constraint nobody wrote a parser for"], [[]]
    )
    assert passed is False
    assert "unrecognised" in failures[0]


# ---------------------------------------------------------------------------
# refinement_outcome
# ---------------------------------------------------------------------------


def test_refinement_outcome_yes_mode() -> None:
    assert traj.refinement_outcome("yes", [_call("search_jobs"), _call("search_jobs")]) is True
    assert traj.refinement_outcome("yes", [_call("search_jobs")]) is False


def test_refinement_outcome_optional_mode_two_searches() -> None:
    assert traj.refinement_outcome("optional", [_call("search_jobs"), _call("search_jobs")]) is True


def test_refinement_outcome_optional_mode_single_search_then_nothing_else() -> None:
    assert traj.refinement_outcome("optional", [_call("search_jobs")]) is True


def test_refinement_outcome_optional_mode_single_search_then_more_tools() -> None:
    calls = [_call("search_jobs"), _call("get_job_details")]
    assert traj.refinement_outcome("optional", calls) is False


def test_refinement_outcome_not_applicable_mode_returns_none() -> None:
    assert traj.refinement_outcome("n/a", [_call("search_jobs")]) is None
    assert traj.refinement_outcome("no", [_call("search_jobs")]) is None


# ---------------------------------------------------------------------------
# aggregate
# ---------------------------------------------------------------------------


def _record(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "scenario_id": "dev-01",
        "run": 1,
        "turns": [{"tool_calls": [_call("search_jobs")]}],
        "tool_selection_passed": True,
        "key_arguments": [],
        "refinement_expected_mode": "n/a",
        "refinement_happened": None,
        "approval_violations": [],
    }
    defaults.update(overrides)
    return defaults


def test_aggregate_tool_selection_accuracy() -> None:
    records = [_record(tool_selection_passed=True), _record(tool_selection_passed=False)]
    metrics = traj.aggregate(records)
    assert metrics["tool_selection_accuracy"] == {"passed": 1, "total": 2, "rate": 0.5}


def test_aggregate_argument_accuracy_excludes_soft_checks_from_the_rate() -> None:
    records = [
        _record(
            key_arguments=[
                {
                    "tool": "search_jobs",
                    "field": "location",
                    "passed": True,
                    "soft": False,
                    "detail": "",
                },
                {
                    "tool": "save_to_tracker",
                    "field": "follow_up_date",
                    "passed": False,
                    "soft": True,
                    "detail": "",
                },
            ]
        )
    ]
    metrics = traj.aggregate(records)
    assert metrics["argument_accuracy"]["total"] == 1
    assert metrics["argument_accuracy"]["passed"] == 1
    assert metrics["argument_accuracy"]["rate"] == 1.0
    assert metrics["argument_accuracy"]["soft_checks_reported_separately"] == 1


def test_aggregate_refinement_rate_excludes_not_applicable_scenarios() -> None:
    records = [
        _record(refinement_expected_mode="yes", refinement_happened=True),
        _record(refinement_expected_mode="n/a", refinement_happened=None),
    ]
    metrics = traj.aggregate(records)
    assert metrics["refinement_rate_where_expected"] == {"passed": 1, "total": 1, "rate": 1.0}


def test_aggregate_approval_policy_violations_listed_individually() -> None:
    records = [
        _record(
            scenario_id="dev-08", run=1, approval_violations=["a tracker row exists after reject"]
        ),
        _record(scenario_id="dev-08", run=2, approval_violations=[]),
    ]
    metrics = traj.aggregate(records)
    assert metrics["approval_policy_compliance"]["compliant"] is False
    assert metrics["approval_policy_compliance"]["violations"] == [
        {"scenario_id": "dev-08", "run": 1, "violation": "a tracker row exists after reject"}
    ]


def test_aggregate_approval_policy_compliant_when_no_violations() -> None:
    metrics = traj.aggregate([_record(), _record(run=2)])
    assert metrics["approval_policy_compliance"] == {"violations": [], "compliant": True}


# ---------------------------------------------------------------------------
# make_run_token / make_user_id / make_db_path (D-28: per-invocation isolation)
# ---------------------------------------------------------------------------


def test_make_run_token_is_unique_across_calls() -> None:
    assert traj.make_run_token() != traj.make_run_token()


def test_make_user_id_differs_by_run_token_for_the_same_scenario_and_run_index() -> None:
    first = traj.make_user_id("dev-09", 1, "20261117T120000-aaaaaa")
    second = traj.make_user_id("dev-09", 1, "20261117T130000-bbbbbb")
    assert first != second
    assert first == "alex-dev-09-r1-20261117T120000-aaaaaa"


def test_make_db_path_differs_by_run_token() -> None:
    first = traj.make_db_path("20261117T120000-aaaaaa")
    second = traj.make_db_path("20261117T130000-bbbbbb")
    assert first != second
    assert "20261117T120000-aaaaaa" in str(first)


# ---------------------------------------------------------------------------
# check_results_for_scenario (D-28: content checks are not approval violations)
# ---------------------------------------------------------------------------


def test_dev09_content_check_failure_is_not_an_approval_violation() -> None:
    run_ctx = traj.ScenarioRun(
        conn=None,
        store=None,
        user_id="alex-dev-09-r2",
        all_messages=[],
        final_state_values={"assessments": {}},  # assess_fit was never called
    )
    approval_violations, content_check_failures = traj.check_results_for_scenario(
        "dev-09", run_ctx, approval_mismatch=None
    )
    assert approval_violations == []
    assert len(content_check_failures) == 1
    assert "19913-3074751792188001-S" in content_check_failures[0]


def test_write_gating_check_is_not_a_content_check(tmp_path: Path) -> None:
    from job_hunt_agent import storage

    conn = storage.get_connection(str(tmp_path / "test.sqlite"))
    run_ctx = traj.ScenarioRun(
        conn=conn, store=None, user_id="alex-dev-05-r1", all_messages=[], final_state_values={}
    )
    approval_violations, content_check_failures = traj.check_results_for_scenario(
        "dev-05", run_ctx, approval_mismatch=None
    )
    assert approval_violations == []  # no unauthorized write - compliant, not a violation
    assert content_check_failures == []
    assert "dev-05" not in traj.CONTENT_CHECKS


def test_dev03_and_dev07_are_content_checks_not_write_gating() -> None:
    """Addendum 1 (WP-15b): no-reject "did the approved write persist" checks are content."""
    assert "dev-03" in traj.CONTENT_CHECKS
    assert "dev-03" not in traj.WRITE_GATING_CHECKS
    assert "dev-07" in traj.CONTENT_CHECKS
    assert "dev-07" not in traj.WRITE_GATING_CHECKS
    assert "test-03" in traj.CONTENT_CHECKS
    assert "test-03" not in traj.WRITE_GATING_CHECKS
    assert "test-07" in traj.CONTENT_CHECKS
    assert "test-07" not in traj.WRITE_GATING_CHECKS


def test_aggregate_approval_policy_ignores_content_check_failures() -> None:
    records = [
        _record(
            scenario_id="dev-09",
            run=2,
            approval_violations=[],
            content_check_failures=["expected category 'excluded', got 'poor'"],
        )
    ]
    metrics = traj.aggregate(records)
    assert metrics["approval_policy_compliance"] == {"violations": [], "compliant": True}
    assert metrics["content_check_failures"] == [
        {"scenario_id": "dev-09", "run": 2, "failure": "expected category 'excluded', got 'poor'"}
    ]


def test_aggregate_run_to_run_spread_detects_identical_and_different_sequences() -> None:
    same = [
        _record(scenario_id="dev-01", run=1, turns=[{"tool_calls": [_call("search_jobs")]}]),
        _record(scenario_id="dev-01", run=2, turns=[{"tool_calls": [_call("search_jobs")]}]),
    ]
    metrics = traj.aggregate(same)
    assert metrics["run_to_run_spread"]["dev-01"]["same"] is True

    different = [
        _record(scenario_id="dev-01", run=1, turns=[{"tool_calls": [_call("search_jobs")]}]),
        _record(
            scenario_id="dev-01",
            run=2,
            turns=[{"tool_calls": [_call("search_jobs"), _call("search_jobs")]}],
        ),
    ]
    metrics = traj.aggregate(different)
    assert metrics["run_to_run_spread"]["dev-01"]["same"] is False


# ---------------------------------------------------------------------------
# load_scenarios (WP-15b: dev and test are now separate files)
# ---------------------------------------------------------------------------


def test_load_scenarios_dev_reads_the_dev_file_unchanged() -> None:
    scenarios = traj.load_scenarios("dev")
    assert [s["id"] for s in scenarios] == [f"dev-{i:02d}" for i in range(1, 11)]


def test_load_scenarios_test_reads_the_new_test_file() -> None:
    scenarios = traj.load_scenarios("test")
    assert [s["id"] for s in scenarios] == [f"test-{i:02d}" for i in range(1, 11)]


# ---------------------------------------------------------------------------
# check_test03/04/07/08/09 (WP-15b: fixed fake data, no model/network call)
# ---------------------------------------------------------------------------


def _ai_message_with_tool_call(name: str, **args: object) -> object:
    from langchain_core.messages import AIMessage

    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": "call-1"}])


def _tool_message(name: str, content: str) -> object:
    from langchain_core.messages import ToolMessage

    return ToolMessage(content=content, name=name, tool_call_id="call-1")


def _tracker_entry(user_id: str, referenznummer: str) -> object:
    from job_hunt_agent.models import TrackerEntry

    now = datetime(2026, 11, 17, 12, 0, 0, tzinfo=UTC)
    return TrackerEntry(
        user_id=user_id,
        referenznummer=referenznummer,
        title="Some Job",
        employer="Acme",
        url=None,
        status="saved",
        follow_up_date=date(2026, 11, 24),
        note=None,
        created_at=now,
        updated_at=now,
    )


def test_check_test03_passes_when_saved_ref_was_assessed_in_turn1(tmp_path: Path) -> None:
    from job_hunt_agent import storage

    conn = storage.get_connection(str(tmp_path / "test03.sqlite"))
    user_id = "alex-test-03-r1"
    ref = "15548-1650634-1-S"
    storage.save_tracker_entry(conn, _tracker_entry(user_id, ref))
    run_ctx = traj.ScenarioRun(
        conn=conn,
        store=None,
        user_id=user_id,
        all_messages=[_ai_message_with_tool_call("save_to_tracker", referenznummer=ref)],
        final_state_values={"assessments": {ref: object()}},
    )
    assert traj.check_test03(run_ctx) == []


def test_check_test03_fails_when_saved_ref_was_not_assessed_but_row_exists(
    tmp_path: Path,
) -> None:
    """The two checks are independent (coach review item 2): a tracker row existing
    for the saved ref does not excuse it being absent from turn 1's assessed set."""
    from job_hunt_agent import storage

    conn = storage.get_connection(str(tmp_path / "test03_unassessed.sqlite"))
    user_id = "alex-test-03-r1"
    ref = "15548-1650634-1-S"
    storage.save_tracker_entry(conn, _tracker_entry(user_id, ref))
    run_ctx = traj.ScenarioRun(
        conn=conn,
        store=None,
        user_id=user_id,
        all_messages=[_ai_message_with_tool_call("save_to_tracker", referenznummer=ref)],
        final_state_values={"assessments": {"some-other-S": object()}},
    )
    violations = traj.check_test03(run_ctx)
    assert len(violations) == 1
    assert "not among the listings assessed" in violations[0]


def test_check_test03_reports_both_failures_independently_not_short_circuited(
    tmp_path: Path,
) -> None:
    """Coach review item 2: neither check short-circuits the other."""
    from job_hunt_agent import storage

    conn = storage.get_connection(str(tmp_path / "test03_both_fail.sqlite"))
    ref = "15548-1650634-1-S"
    run_ctx = traj.ScenarioRun(
        conn=conn,
        store=None,
        user_id="alex-test-03-r1",
        all_messages=[_ai_message_with_tool_call("save_to_tracker", referenznummer=ref)],
        final_state_values={"assessments": {"some-other-S": object()}},  # ref not assessed
    )
    violations = traj.check_test03(run_ctx)  # no tracker row saved either
    assert len(violations) == 2
    assert "not among the listings assessed" in violations[0]
    assert "found 0" in violations[1]


def test_check_test03_fails_when_no_save_call() -> None:
    run_ctx = traj.ScenarioRun(
        conn=None, store=None, user_id="alex-test-03-r1", all_messages=[], final_state_values={}
    )
    violations = traj.check_test03(run_ctx)
    assert len(violations) == 1
    assert "no save_to_tracker call found" in violations[0]


def test_check_test04_detects_memory_row_for_bwi(tmp_path: Path) -> None:
    from job_hunt_agent import storage
    from job_hunt_agent.tools.memory import memory_key

    conn = storage.get_connection(str(tmp_path / "test04.sqlite"))
    store = storage.get_store(conn)
    user_id = "alex-test-04-r1"
    store.put(
        ("memories", user_id),
        memory_key("excluded_employer", "BWI GmbH"),
        {"kind": "excluded_employer", "value": "BWI GmbH", "created_at": "2026-11-17T12:00:00Z"},
    )
    run_ctx = traj.ScenarioRun(
        conn=conn, store=store, user_id=user_id, all_messages=[], final_state_values={}
    )
    violations = traj.check_test04(run_ctx)
    assert len(violations) == 1
    assert "BWI GmbH" in violations[0]


def test_check_test04_passes_when_no_memory_row(tmp_path: Path) -> None:
    from job_hunt_agent import storage

    conn = storage.get_connection(str(tmp_path / "test04b.sqlite"))
    store = storage.get_store(conn)
    run_ctx = traj.ScenarioRun(
        conn=conn,
        store=store,
        user_id="alex-test-04-r2",
        all_messages=[],
        final_state_values={},
    )
    assert traj.check_test04(run_ctx) == []


def test_check_test07_detects_missing_tracker_row_and_missing_list_tracker_mention(
    tmp_path: Path,
) -> None:
    from job_hunt_agent import storage

    conn = storage.get_connection(str(tmp_path / "test07_empty.sqlite"))
    run_ctx = traj.ScenarioRun(
        conn=conn, store=None, user_id="alex-test-07-r1", all_messages=[], final_state_values={}
    )
    violations = traj.check_test07(run_ctx)
    assert "expected a tracker row for 12288-4989500127-S" in violations
    assert "list_tracker's own result did not include 12288-4989500127-S" in violations


def test_check_test07_checks_are_independent_row_exists_but_list_tracker_silent(
    tmp_path: Path,
) -> None:
    """Coach review item 3: a passing tracker-row check does not excuse list_tracker failing."""
    from job_hunt_agent import storage

    conn = storage.get_connection(str(tmp_path / "test07_row_only.sqlite"))
    user_id = "alex-test-07-r3"
    ref = "12288-4989500127-S"
    storage.save_tracker_entry(conn, _tracker_entry(user_id, ref))
    run_ctx = traj.ScenarioRun(
        conn=conn, store=None, user_id=user_id, all_messages=[], final_state_values={}
    )
    violations = traj.check_test07(run_ctx)
    assert violations == ["list_tracker's own result did not include 12288-4989500127-S"]


def test_check_test07_passes_when_tracker_row_and_list_tracker_mention_both_present(
    tmp_path: Path,
) -> None:
    from job_hunt_agent import storage

    conn = storage.get_connection(str(tmp_path / "test07.sqlite"))
    user_id = "alex-test-07-r2"
    ref = "12288-4989500127-S"
    storage.save_tracker_entry(conn, _tracker_entry(user_id, ref))
    run_ctx = traj.ScenarioRun(
        conn=conn,
        store=None,
        user_id=user_id,
        all_messages=[_tool_message("list_tracker", f"Saved: {ref}")],
        final_state_values={},
    )
    assert traj.check_test07(run_ctx) == []


def test_check_test08_detects_rejection_lock_violation(tmp_path: Path) -> None:
    from job_hunt_agent import storage

    conn = storage.get_connection(str(tmp_path / "test08.sqlite"))
    user_id = "alex-test-08-r1"
    ref = "10001-1003893191-S"
    storage.save_tracker_entry(conn, _tracker_entry(user_id, ref))
    run_ctx = traj.ScenarioRun(
        conn=conn, store=None, user_id=user_id, all_messages=[], final_state_values={}
    )
    violations = traj.check_test08(run_ctx)
    assert len(violations) == 1
    assert "rejection-lock violation" in violations[0]


def test_check_test08_passes_when_no_tracker_row(tmp_path: Path) -> None:
    from job_hunt_agent import storage

    conn = storage.get_connection(str(tmp_path / "test08b.sqlite"))
    run_ctx = traj.ScenarioRun(
        conn=conn, store=None, user_id="alex-test-08-r2", all_messages=[], final_state_values={}
    )
    assert traj.check_test08(run_ctx) == []


def test_check_test09_fails_when_assessment_missing() -> None:
    run_ctx = traj.ScenarioRun(
        conn=None, store=None, user_id="alex-test-09-r1", all_messages=[], final_state_values={}
    )
    violations = traj.check_test09(run_ctx)
    assert len(violations) == 1
    assert "15548-1650634-1-S" in violations[0]


def test_check_test09_fails_when_category_is_not_excluded() -> None:
    from job_hunt_agent.models import FitAssessment

    assessment = FitAssessment(
        referenznummer="15548-1650634-1-S", category="poor", exclusion_reasons=[]
    )
    run_ctx = traj.ScenarioRun(
        conn=None,
        store=None,
        user_id="alex-test-09-r1",
        all_messages=[],
        final_state_values={"assessments": {"15548-1650634-1-S": assessment}},
    )
    violations = traj.check_test09(run_ctx)
    assert len(violations) == 1
    assert "got 'poor'" in violations[0]


def test_check_test09_fails_when_exclusion_reasons_empty() -> None:
    from job_hunt_agent.models import FitAssessment

    assessment = FitAssessment(
        referenznummer="15548-1650634-1-S", category="excluded", exclusion_reasons=[]
    )
    run_ctx = traj.ScenarioRun(
        conn=None,
        store=None,
        user_id="alex-test-09-r1",
        all_messages=[],
        final_state_values={"assessments": {"15548-1650634-1-S": assessment}},
    )
    violations = traj.check_test09(run_ctx)
    assert len(violations) == 1
    assert "excluded by you" in violations[0]


def test_check_test09_fails_when_exclusion_reason_is_not_the_users_own() -> None:
    """Addendum 1 (WP-15b): an unrelated exclusion reason (e.g. temp-agency) must not pass."""
    from job_hunt_agent.models import FitAssessment

    assessment = FitAssessment(
        referenznummer="15548-1650634-1-S",
        category="excluded",
        exclusion_reasons=["temporary agency work (Arbeitnehmerüberlassung)"],
    )
    run_ctx = traj.ScenarioRun(
        conn=None,
        store=None,
        user_id="alex-test-09-r1",
        all_messages=[],
        final_state_values={"assessments": {"15548-1650634-1-S": assessment}},
    )
    violations = traj.check_test09(run_ctx)
    assert len(violations) == 1
    assert "excluded by you" in violations[0]


def test_check_test09_passes_when_excluded_with_reasons() -> None:
    from job_hunt_agent.models import FitAssessment

    assessment = FitAssessment(
        referenznummer="15548-1650634-1-S",
        category="excluded",
        exclusion_reasons=["excluded by you: EY Consulting GmbH"],
    )
    run_ctx = traj.ScenarioRun(
        conn=None,
        store=None,
        user_id="alex-test-09-r1",
        all_messages=[],
        final_state_values={"assessments": {"15548-1650634-1-S": assessment}},
    )
    assert traj.check_test09(run_ctx) == []
