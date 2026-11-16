"""Tests for the pure comparison logic of ``eval/run_fit_eval.py`` (spec §9.3, WP-14).

Fixed fake ``AppResult``/label data only - no model call, no fixture file,
no OpenRouter (CLAUDE.md invariant 5, NFR-05). Loaded by file path (like
``tests/test_label_fit.py`` loads ``scripts/label_fit.py``) since
``eval/run_fit_eval.py`` is a script, not a package member.

Related: spec §7, §9.1, §9.3, NFR-05, invariant 5, invariant 6, D-9, D-20, WP-14
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "eval" / "run_fit_eval.py"


def _load_run_fit_eval_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_fit_eval_under_test", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


fit_eval = _load_run_fit_eval_module()


def _app_result(**overrides: object) -> Any:
    defaults: dict[str, object] = {
        "referenznummer": "11119-TEST-S",
        "run": 1,
        "category": "partial",
        "rubric": {
            "skills": "partly",
            "location_remote": "met",
            "seniority": "met",
            "language": "met",
            "employment_type": "met",
        },
        "exclusion_reasons": [],
        "dropped_evidence": 0,
        "low_evidence": False,
        "extracted_skills": [],
        "extraction_error": None,
    }
    defaults.update(overrides)
    return fit_eval.AppResult(**defaults)


def _label_row(**overrides: str) -> dict[str, str]:
    row = {
        "referenznummer": "11119-TEST-S",
        "category": "partial",
        "skills_verdict": "partly",
        "location_remote_verdict": "met",
        "seniority_verdict": "met",
        "language_verdict": "met",
        "employment_type_verdict": "met",
        "skills_note": "",
        "location_remote_note": "",
        "seniority_note": "",
        "language_note": "",
        "employment_type_note": "",
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# compare_run (agreement)
# ---------------------------------------------------------------------------


def test_compare_run_no_disagreements_when_everything_matches() -> None:
    assert fit_eval.compare_run(_app_result(), _label_row()) == []


def test_compare_run_finds_category_disagreement() -> None:
    disagreements = fit_eval.compare_run(_app_result(category="poor"), _label_row())
    assert len(disagreements) == 1
    d = disagreements[0]
    assert d.field == "category"
    assert d.app_value == "poor"
    assert d.label_value == "partial"
    assert d.cause is None


def test_compare_run_finds_dimension_disagreement_with_note() -> None:
    app = _app_result(rubric={**_app_result().rubric, "location_remote": "not_met"})
    label = _label_row(
        location_remote_verdict="met", location_remote_note="Homeoffice nach Vereinbarung"
    )
    disagreements = fit_eval.compare_run(app, label)
    assert len(disagreements) == 1
    d = disagreements[0]
    assert d.field == "location_remote"
    assert d.app_value == "not_met"
    assert d.label_value == "met"
    assert d.label_note == "Homeoffice nach Vereinbarung"


def test_compare_run_finds_multiple_disagreements() -> None:
    app = _app_result(category="poor", rubric={**_app_result().rubric, "skills": "not_met"})
    disagreements = fit_eval.compare_run(app, _label_row())
    fields = {d.field for d in disagreements}
    assert fields == {"category", "skills"}


# ---------------------------------------------------------------------------
# category_accuracy / confusion_matrix
# ---------------------------------------------------------------------------


def test_category_accuracy_all_correct() -> None:
    pairs = [("strong", "strong"), ("partial", "partial"), ("poor", "poor")]
    assert fit_eval.category_accuracy(pairs) == 1.0


def test_category_accuracy_partial() -> None:
    pairs = [("strong", "strong"), ("partial", "poor"), ("poor", "poor"), ("excluded", "poor")]
    assert fit_eval.category_accuracy(pairs) == 0.5


def test_category_accuracy_empty_is_zero() -> None:
    assert fit_eval.category_accuracy([]) == 0.0


def test_confusion_matrix_counts_by_label_then_app() -> None:
    pairs = [
        ("strong", "strong"),
        ("partial", "poor"),
        ("poor", "poor"),
        ("excluded", "excluded"),
    ]
    matrix = fit_eval.confusion_matrix(pairs)
    assert matrix["strong"]["strong"] == 1
    assert matrix["partial"]["poor"] == 1
    assert matrix["partial"]["strong"] == 0
    assert matrix["poor"]["poor"] == 1
    assert matrix["excluded"]["excluded"] == 1
    assert set(matrix.keys()) == {"strong", "partial", "poor", "excluded"}
    for label_cat in matrix:
        assert set(matrix[label_cat].keys()) == {"strong", "partial", "poor", "excluded"}


def test_confusion_matrix_empty_pairs_is_all_zero() -> None:
    matrix = fit_eval.confusion_matrix([])
    assert all(count == 0 for row in matrix.values() for count in row.values())


# ---------------------------------------------------------------------------
# dimension_agreement
# ---------------------------------------------------------------------------


def test_dimension_agreement_mixed() -> None:
    records = [
        ("skills", "met", "met"),
        ("skills", "partly", "not_met"),
        ("location_remote", "met", "met"),
    ]
    agreement = fit_eval.dimension_agreement(records)
    assert agreement["skills"] == 0.5
    assert agreement["location_remote"] == 1.0


# ---------------------------------------------------------------------------
# run_to_run_agreement
# ---------------------------------------------------------------------------


def test_run_to_run_agreement_all_match() -> None:
    run1 = _app_result(run=1)
    run2 = _app_result(run=2)
    agreement = fit_eval.run_to_run_agreement(run1, run2)
    assert all(agreement.values())
    assert agreement["category"] is True


def test_run_to_run_agreement_detects_mismatch() -> None:
    run1 = _app_result(run=1, category="partial")
    run2 = _app_result(run=2, category="poor")
    agreement = fit_eval.run_to_run_agreement(run1, run2)
    assert agreement["category"] is False


# ---------------------------------------------------------------------------
# attach_cause / summarize_causes (cause classification input/output)
# ---------------------------------------------------------------------------


def test_attach_cause_sets_cause_without_mutating_original() -> None:
    d = fit_eval.compare_run(_app_result(category="poor"), _label_row())[0]
    classified = fit_eval.attach_cause(d, "rubric_rule_or_threshold")
    assert classified.cause == "rubric_rule_or_threshold"
    assert d.cause is None


def test_summarize_causes_counts_per_class() -> None:
    d1 = fit_eval.Disagreement(
        "ref1", 1, "category", "poor", "partial", cause="rubric_rule_or_threshold"
    )
    d2 = fit_eval.Disagreement("ref2", 1, "skills", "not_met", "partly", cause="extraction_error")
    d3 = fit_eval.Disagreement("ref3", 1, "seniority", "met", "partly", cause="extraction_error")
    assert fit_eval.summarize_causes([d1, d2, d3]) == {
        "rubric_rule_or_threshold": 1,
        "extraction_error": 2,
    }


def test_summarize_causes_unclassified_when_cause_missing() -> None:
    d = fit_eval.Disagreement("ref1", 1, "category", "poor", "partial")
    assert fit_eval.summarize_causes([d]) == {"unclassified": 1}
