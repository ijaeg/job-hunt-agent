"""Fit evaluation (spec §9.3, WP-14): app vs. hand label.

Runs the real ``assess_fit`` extraction-and-rubric code path (reused, not
copied, from ``job_hunt_agent.tools.assess``/``job_hunt_agent.rubric``) over
one set (``dev`` or ``test``) of ``eval/fit_set.yaml`` against the fixture
set (demo mode, invariant 6, NFR-09) and compares the result with Ingo's
hand label (``eval/fit_labels.csv``, D-20).

Each listing is extracted **twice**, independently, so run-to-run spread is
visible (mirrors §9.2's "each scenario runs twice"). The ``JobSummary`` is
built straight from the fixture listing dict exactly as
``ba_client.FixtureSource.search`` would have returned it (same
``distance_km`` the labelling tool showed, WP-13 addendum 2); ``JobDetails``
comes from ``FixtureSource.get_details`` - the same two inputs
``tools/assess.py`` works with, assembled here because no prior
``search_jobs``/``get_job_details`` tool call exists in a standalone script.

The comparison helpers below (agreement, confusion matrix, cause
attachment/summary) are pure and unit-tested with fixed fake data
(``tests/test_run_fit_eval.py``, NFR-05) - they never reach OpenRouter.
Only ``main()`` calls the real model.

Usage (needs OPENROUTER_API_KEY; runs against the fixture set, not the
real BA API):
    uv run python eval/run_fit_eval.py --set dev
    uv run python eval/run_fit_eval.py --set test

Writes:
    eval/results/fit_eval_dev.json / fit_eval_test.json

Related: spec §7, §9.1, §9.3, FR-05 AC2, FR-06, NFR-09, invariant 6, D-9,
D-20, WP-14
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Literal

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from job_hunt_agent import config  # noqa: E402
from job_hunt_agent.ba_client import FixtureSource, _job_summary_from_fixture_listing  # noqa: E402
from job_hunt_agent.llm import build_real_model  # noqa: E402
from job_hunt_agent.models import Profile  # noqa: E402
from job_hunt_agent.rubric import assess as rubric_assess  # noqa: E402
from job_hunt_agent.tools.assess import _extract_one, load_extraction_prompt_template  # noqa: E402

FIT_SET_PATH = PROJECT_ROOT / "eval" / "fit_set.yaml"
FIT_LABELS_PATH = PROJECT_ROOT / "eval" / "fit_labels.csv"
LISTINGS_PATH = PROJECT_ROOT / "data" / "samples" / "fixtures" / "listings.json"
RECORDED_SEARCHES_PATH = PROJECT_ROOT / "data" / "samples" / "fixtures" / "recorded_searches.json"
PROFILE_PATH = PROJECT_ROOT / "data" / "samples" / "profile_alex.yaml"
RESULTS_DIR = PROJECT_ROOT / "eval" / "results"
LABEL_FIT_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "label_fit.py"

#: Rubric dimensions in spec §7's order; keys match ``FitAssessment.rubric``
#: and the ``<dim>_verdict`` columns of ``eval/fit_labels.csv``.
DIMENSIONS: tuple[str, ...] = (
    "skills",
    "location_remote",
    "seniority",
    "language",
    "employment_type",
)

#: Each listing is extracted this many times, independently (spec §9.2's
#: "each scenario runs twice" pattern, applied here to the fit evaluation).
RUNS_PER_LISTING = 2

FIT_CATEGORIES: tuple[str, ...] = ("strong", "partial", "poor", "excluded")

#: Disagreement cause classes (Stage 1, WP-14 prompt step 2). Assigned by
#: the analyst after reading the ad text and the rubric, not inferred here -
#: ``attach_cause``/``summarize_causes`` only record and tally the result.
Cause = Literal[
    "extraction_error",
    "rubric_rule_or_threshold",
    "code_deviation",
    "data_issue",
    "label_ambiguity",
]


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_fit_set(path: Path = FIT_SET_PATH) -> list[dict[str, Any]]:
    """Returns the ``listings`` entries of ``eval/fit_set.yaml``, in file order."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    listings: list[dict[str, Any]] = doc["listings"]
    return listings


def load_labels(path: Path = FIT_LABELS_PATH) -> dict[str, dict[str, str]]:
    """Indexes ``eval/fit_labels.csv`` by ``referenznummer``."""
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {row["referenznummer"]: row for row in csv.DictReader(handle)}


def load_recorded_searches(path: Path = RECORDED_SEARCHES_PATH) -> list[dict[str, Any]]:
    """The 5 recorded D-1 searches - reused to resolve what a distance is relative to."""
    searches: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return searches


def load_label_fit_module(path: Path = LABEL_FIT_SCRIPT_PATH) -> ModuleType:
    """Loads ``scripts/label_fit.py`` by file path (it is a script, not a package member).

    Reused for ``resolve_search_location`` only, so the distance this script
    compares against is described the same way the labelling tool showed it
    (WP-13 addendum 2) - not a copy of that function.
    """
    spec = importlib.util.spec_from_file_location("label_fit_for_fit_eval", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Running the app's own code path (extraction + rubric)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AppResult:
    """One extraction-and-rubric run for one listing."""

    referenznummer: str
    run: int
    category: str
    rubric: dict[str, str]
    exclusion_reasons: list[str]
    dropped_evidence: int
    low_evidence: bool
    extracted_skills: list[dict[str, str]]
    extraction_error: str | None = None


def run_listing(
    model: Any,
    template: str,
    fixture_source: FixtureSource,
    raw_listing: dict[str, Any],
    profile: Profile,
    *,
    runs: int = RUNS_PER_LISTING,
) -> list[AppResult]:
    """Runs ``runs`` independent extraction-and-rubric passes for one listing.

    Mirrors ``tools.assess.assess_fit``'s code path exactly (``_extract_one``
    then ``rubric.assess``), with no excluded employers (no memory store in
    this standalone script) and the ``JobSummary``/``JobDetails`` built as
    described in the module docstring. An extraction failure is recorded as
    ``extraction_error`` instead of raising, matching the tool's own
    "could not be assessed" handling (spec §8) rather than aborting the run.
    """
    ref = raw_listing["referenznummer"]
    summary = _job_summary_from_fixture_listing(raw_listing)
    details = fixture_source.get_details(ref)

    results: list[AppResult] = []
    for run_index in range(1, runs + 1):
        try:
            outcome = _extract_one(model, template, ref, details.description)
        except Exception as exc:  # noqa: BLE001 - recorded, never raised (spec §8)
            outcome = None
            extraction_error: str | None = str(exc)
        else:
            extraction_error = None
        if outcome is None:
            results.append(
                AppResult(
                    referenznummer=ref,
                    run=run_index,
                    category="",
                    rubric={dim: "" for dim in DIMENSIONS},
                    exclusion_reasons=[],
                    dropped_evidence=0,
                    low_evidence=False,
                    extracted_skills=[],
                    extraction_error=extraction_error or "extraction returned no result",
                )
            )
            continue
        requirements, dropped = outcome
        assessment = rubric_assess(summary, details, requirements, profile, excluded_employers=[])
        results.append(
            AppResult(
                referenznummer=ref,
                run=run_index,
                category=assessment.category,
                rubric=dict(assessment.rubric),
                exclusion_reasons=assessment.exclusion_reasons,
                dropped_evidence=dropped,
                low_evidence=assessment.low_evidence,
                extracted_skills=[r.model_dump() for r in requirements.skills],
            )
        )
    return results


# ---------------------------------------------------------------------------
# Comparison logic (pure, unit-tested with fixed fake data - NFR-05)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Disagreement:
    """One field (category or a rubric dimension) where the app and the label differ."""

    referenznummer: str
    run: int
    field: str
    app_value: str
    label_value: str
    label_note: str = ""
    cause: Cause | None = None


def compare_run(app: AppResult, label_row: dict[str, str]) -> list[Disagreement]:
    """Every category/dimension disagreement between one run and its label."""
    disagreements: list[Disagreement] = []
    if app.category != label_row["category"]:
        disagreements.append(
            Disagreement(
                referenznummer=app.referenznummer,
                run=app.run,
                field="category",
                app_value=app.category,
                label_value=label_row["category"],
            )
        )
    for dim in DIMENSIONS:
        app_value = app.rubric[dim]
        label_value = label_row[f"{dim}_verdict"]
        if app_value != label_value:
            disagreements.append(
                Disagreement(
                    referenznummer=app.referenznummer,
                    run=app.run,
                    field=dim,
                    app_value=app_value,
                    label_value=label_value,
                    label_note=label_row.get(f"{dim}_note", ""),
                )
            )
    return disagreements


def category_accuracy(pairs: list[tuple[str, str]]) -> float:
    """Share of ``(label_category, app_category)`` pairs that agree."""
    if not pairs:
        return 0.0
    correct = sum(1 for label_cat, app_cat in pairs if label_cat == app_cat)
    return correct / len(pairs)


def confusion_matrix(pairs: list[tuple[str, str]]) -> dict[str, dict[str, int]]:
    """A 4x4 ``matrix[label_category][app_category] = count`` over ``FIT_CATEGORIES``."""
    matrix: dict[str, dict[str, int]] = {
        label_cat: dict.fromkeys(FIT_CATEGORIES, 0) for label_cat in FIT_CATEGORIES
    }
    for label_cat, app_cat in pairs:
        matrix[label_cat][app_cat] += 1
    return matrix


def dimension_agreement(records: list[tuple[str, str, str]]) -> dict[str, float]:
    """Per-dimension agreement share from ``(dimension, app_value, label_value)`` triples."""
    totals: dict[str, int] = defaultdict(int)
    matches: dict[str, int] = defaultdict(int)
    for dim, app_value, label_value in records:
        totals[dim] += 1
        if app_value == label_value:
            matches[dim] += 1
    return {dim: matches[dim] / totals[dim] for dim in totals}


def run_to_run_agreement(run1: AppResult, run2: AppResult) -> dict[str, bool]:
    """Whether two independent runs of the same listing agree, per field."""
    agreement = {"category": run1.category == run2.category}
    for dim in DIMENSIONS:
        agreement[dim] = run1.rubric[dim] == run2.rubric[dim]
    return agreement


def attach_cause(disagreement: Disagreement, cause: Cause) -> Disagreement:
    """Returns a copy of ``disagreement`` with its cause class set."""
    return replace(disagreement, cause=cause)


def summarize_causes(disagreements: list[Disagreement]) -> dict[str, int]:
    """Counts disagreements per cause class (``"unclassified"`` if none assigned yet)."""
    return dict(Counter(d.cause or "unclassified" for d in disagreements))


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--set",
        choices=["dev", "test"],
        required=True,
        help="Which eval/fit_set.yaml split to run (invariant 6: test is never used for tuning).",
    )
    args = parser.parse_args()

    fit_set = [row for row in load_fit_set() if row["set"] == args.set]
    labels = load_labels()
    raw_listings: list[dict[str, Any]] = json.loads(LISTINGS_PATH.read_text(encoding="utf-8"))
    listings_by_ref = {listing["referenznummer"]: listing for listing in raw_listings}
    recorded_searches = load_recorded_searches()
    label_fit = load_label_fit_module()
    profile = Profile.model_validate(yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8")))
    fixture_source = FixtureSource()
    model = build_real_model()
    template = load_extraction_prompt_template()

    run_range = range(1, RUNS_PER_LISTING + 1)
    pairs_by_run: dict[int, list[tuple[str, str]]] = {run: [] for run in run_range}
    dim_records_by_run: dict[int, list[tuple[str, str, str]]] = {run: [] for run in run_range}
    all_disagreements: list[Disagreement] = []
    listing_records: list[dict[str, Any]] = []
    total_dropped_evidence = 0

    for entry in fit_set:
        ref = entry["referenznummer"]
        label_row = labels[ref]
        search_location = label_fit.resolve_search_location(ref, recorded_searches)
        run_results = run_listing(model, template, fixture_source, listings_by_ref[ref], profile)

        run_payloads: list[dict[str, Any]] = []
        for app_result in run_results:
            total_dropped_evidence += app_result.dropped_evidence
            if app_result.extraction_error is None:
                pairs_by_run[app_result.run].append((label_row["category"], app_result.category))
                for dim in DIMENSIONS:
                    dim_records_by_run[app_result.run].append(
                        (dim, app_result.rubric[dim], label_row[f"{dim}_verdict"])
                    )
                all_disagreements.extend(compare_run(app_result, label_row))
            run_payloads.append(asdict(app_result))

        run_to_run = (
            run_to_run_agreement(run_results[0], run_results[1])
            if len(run_results) == 2 and all(r.extraction_error is None for r in run_results)
            else None
        )
        listing_records.append(
            {
                "referenznummer": ref,
                "title": entry["title"],
                "employer": entry["employer"],
                "stratum": entry["stratum"],
                "search_location": search_location,
                "label": label_row,
                "runs": run_payloads,
                "run_to_run_agreement": run_to_run,
            }
        )
        categories = ", ".join(
            f"run{r.run}={r.category or r.extraction_error}" for r in run_results
        )
        print(f"[{ref}] label={label_row['category']} {categories}")

    results: dict[str, Any] = {
        "set": args.set,
        "model": config.CHAT_MODEL,
        "reasoning_effort": config.REASONING_EFFORT,
        "run_date": date.today().isoformat(),
        "run_datetime_utc": datetime.now(UTC).isoformat(),
        "n_listings": len(fit_set),
        "category_accuracy_by_run": {
            run: category_accuracy(pairs) for run, pairs in pairs_by_run.items()
        },
        "confusion_matrix_by_run": {
            run: confusion_matrix(pairs) for run, pairs in pairs_by_run.items()
        },
        "dimension_agreement_by_run": {
            run: dimension_agreement(records) for run, records in dim_records_by_run.items()
        },
        "total_dropped_evidence": total_dropped_evidence,
        "disagreements": [asdict(d) for d in all_disagreements],
        "listings": listing_records,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"fit_eval_{args.set}.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults: {out_path}")
    print(
        f"Disagreements: {len(all_disagreements)}; total dropped_evidence: {total_dropped_evidence}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
