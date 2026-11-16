"""WP-14b round-2 dev-set re-scoring (spec §9.3, D-26): no model call.

Re-scores the 40 stored WP-14 round-1 runs (``eval/results/fit_eval_dev.json``
8 listings + ``eval/results/fit_eval_test.json`` 12 listings, 2 runs each -
all 20 are now development listings per D-26 step 1) with a new skills metric,
without re-running extraction: each run's ``extracted_skills`` (already past
``drop_non_verbatim_evidence``, FR-05 AC2) is re-matched against the profile
with the existing whole-word matcher (D-9), the other four stored verdicts and
the stored ``exclusion_reasons``/``low_evidence`` are kept, and the category is
recomputed with ``rubric.category_from_rubric`` (the pure function WP-14b
pulled out of ``rubric.assess`` for exactly this purpose).

A sanity check runs first: re-scoring with the *current* (shipped) skills
metric must reproduce every one of the 40 stored skills verdicts and
categories exactly. Only once that passes does this script compute the four
new-metric variants (N = 2 / 3, with/without D-25's cap) D-26 asks for.

Usage (no OPENROUTER_API_KEY needed, no network call):
    uv run python eval/rescore_fit_round2.py

Writes:
    eval/results/fit_eval_round2_dev.json

Related: spec §7, §9.1, §9.3, D-9, D-20, D-21, D-25, D-26, WP-14, WP-14b
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from job_hunt_agent.models import Profile  # noqa: E402
from job_hunt_agent.rubric import category_from_rubric, skill_matches_profile  # noqa: E402

DEV_RESULTS_PATH = PROJECT_ROOT / "eval" / "results" / "fit_eval_dev.json"
TEST_RESULTS_PATH = PROJECT_ROOT / "eval" / "results" / "fit_eval_test.json"
PROFILE_PATH = PROJECT_ROOT / "data" / "samples" / "profile_alex.yaml"
OUT_PATH = PROJECT_ROOT / "eval" / "results" / "fit_eval_round2_dev.json"

FIT_CATEGORIES: tuple[str, ...] = ("strong", "partial", "poor", "excluded")


@dataclass(frozen=True)
class StoredRun:
    """One stored WP-14 round-1 extraction-and-rubric run, as read back from JSON."""

    referenznummer: str
    run: int
    label_category: str
    label_skills_verdict: str
    stored_category: str
    stored_rubric: dict[str, str]
    exclusion_reasons: list[str]
    low_evidence: bool
    extracted_skill_names: list[str]


def load_stored_runs(*paths: Path) -> list[StoredRun]:
    """Flattens every run of every listing across the given result files."""
    runs: list[StoredRun] = []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        for listing in data["listings"]:
            label = listing["label"]
            for run in listing["runs"]:
                runs.append(
                    StoredRun(
                        referenznummer=run["referenznummer"],
                        run=run["run"],
                        label_category=label["category"],
                        label_skills_verdict=label["skills_verdict"],
                        stored_category=run["category"],
                        stored_rubric=run["rubric"],
                        exclusion_reasons=run["exclusion_reasons"],
                        low_evidence=run["low_evidence"],
                        extracted_skill_names=[s["name"] for s in run["extracted_skills"]],
                    )
                )
    return runs


# ---------------------------------------------------------------------------
# Current (shipped) skills metric - sanity check only
# ---------------------------------------------------------------------------

CURRENT_SKILLS_STRONG_THRESHOLD = 0.70
CURRENT_SKILLS_PARTIAL_THRESHOLD = 0.40


def current_skills_verdict(skill_names: list[str], profile_skills: list[str]) -> str:
    """Reproduces ``rubric._skills_verdict`` (share of extracted skills matched)."""
    if not skill_names:
        return "unknown"
    matched = sum(1 for name in skill_names if skill_matches_profile(name, profile_skills))
    share = matched / len(skill_names)
    if share >= CURRENT_SKILLS_STRONG_THRESHOLD:
        return "met"
    if share >= CURRENT_SKILLS_PARTIAL_THRESHOLD:
        return "partly"
    return "not_met"


def sanity_check(runs: list[StoredRun], profile: Profile) -> list[str]:
    """Re-scores all runs with the CURRENT metric; returns a list of mismatch descriptions."""
    mismatches: list[str] = []
    for run in runs:
        skills_verdict = current_skills_verdict(run.extracted_skill_names, profile.skills)
        if skills_verdict != run.stored_rubric["skills"]:
            mismatches.append(
                f"{run.referenznummer} run {run.run}: skills verdict "
                f"recomputed={skills_verdict!r} stored={run.stored_rubric['skills']!r}"
            )
            continue
        rubric = dict(run.stored_rubric)
        category, _ = category_from_rubric(rubric, run.exclusion_reasons, run.low_evidence)
        if category != run.stored_category:
            mismatches.append(
                f"{run.referenznummer} run {run.run}: category "
                f"recomputed={category!r} stored={run.stored_category!r}"
            )
    return mismatches


# ---------------------------------------------------------------------------
# New skills metric (WP-14b/D-26): matched profile skills, not share of all
# ---------------------------------------------------------------------------


def matched_profile_skills(skill_names: list[str], profile_skills: list[str]) -> set[str]:
    """Distinct profile skills found (whole-word, D-9) among the extracted skill names."""
    return {
        profile_skill
        for profile_skill in profile_skills
        if any(skill_matches_profile(name, [profile_skill]) for name in skill_names)
    }


def new_skills_verdict(skill_names: list[str], profile_skills: list[str], n: int) -> str:
    """unknown if nothing extracted (D-21 unchanged); else matched profile-skill count vs. N."""
    if not skill_names:
        return "unknown"
    matched = len(matched_profile_skills(skill_names, profile_skills))
    if matched == 0:
        return "not_met"
    if matched < n:
        return "partly"
    return "met"


# ---------------------------------------------------------------------------
# Metrics over a run set
# ---------------------------------------------------------------------------


def category_accuracy(pairs: list[tuple[str, str]]) -> float:
    if not pairs:
        return 0.0
    correct = sum(1 for label_cat, app_cat in pairs if label_cat == app_cat)
    return correct / len(pairs)


def confusion_matrix(pairs: list[tuple[str, str]]) -> dict[str, dict[str, int]]:
    matrix: dict[str, dict[str, int]] = {
        label_cat: dict.fromkeys(FIT_CATEGORIES, 0) for label_cat in FIT_CATEGORIES
    }
    for label_cat, app_cat in pairs:
        matrix[label_cat][app_cat] += 1
    return matrix


def run_variant(
    runs: list[StoredRun], profile: Profile, *, n: int, apply_cap: bool
) -> dict[str, Any]:
    """Recomputes skills + category for every run under one (N, cap) variant."""
    by_ref_run: dict[tuple[str, int], StoredRun] = {(r.referenznummer, r.run): r for r in runs}
    refs = sorted({r.referenznummer for r in runs})

    category_pairs_by_run: dict[int, list[tuple[str, str]]] = {1: [], 2: []}
    skills_pairs_by_run: dict[int, list[tuple[str, str]]] = {1: [], 2: []}
    category_by_ref_run: dict[tuple[str, int], str] = {}

    for ref in refs:
        for run_index in (1, 2):
            stored = by_ref_run[(ref, run_index)]
            skills_verdict = new_skills_verdict(stored.extracted_skill_names, profile.skills, n)
            rubric = dict(stored.stored_rubric)
            rubric["skills"] = skills_verdict
            category, _ = category_from_rubric(
                rubric,
                stored.exclusion_reasons,
                stored.low_evidence,
                apply_skills_not_met_cap=apply_cap,
            )
            category_pairs_by_run[run_index].append((stored.label_category, category))
            skills_pairs_by_run[run_index].append((stored.label_skills_verdict, skills_verdict))
            category_by_ref_run[(ref, run_index)] = category

    n_different_category = sum(
        1 for ref in refs if category_by_ref_run[(ref, 1)] != category_by_ref_run[(ref, 2)]
    )
    n_correct_by_run = {
        run_index: sum(1 for lbl, app in pairs if lbl == app)
        for run_index, pairs in category_pairs_by_run.items()
    }

    return {
        "n": n,
        "apply_cap": apply_cap,
        "n_listings": len(refs),
        "category_accuracy_by_run": {
            run_index: category_accuracy(pairs)
            for run_index, pairs in category_pairs_by_run.items()
        },
        "n_correct_category_by_run": n_correct_by_run,
        "skills_dimension_agreement_by_run": {
            run_index: category_accuracy(pairs) for run_index, pairs in skills_pairs_by_run.items()
        },
        "n_different_category_between_runs": n_different_category,
        "confusion_matrix_by_run": {
            run_index: confusion_matrix(pairs) for run_index, pairs in category_pairs_by_run.items()
        },
        "meets_rule_5": (
            n_correct_by_run[1] >= 12 and n_correct_by_run[2] >= 12 and n_different_category <= 2
        ),
    }


def main() -> int:
    profile = Profile.model_validate(yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8")))
    runs = load_stored_runs(DEV_RESULTS_PATH, TEST_RESULTS_PATH)
    n_listings = len({r.referenznummer for r in runs})
    print(f"Loaded {len(runs)} stored runs across {n_listings} listings.")

    mismatches = sanity_check(runs, profile)
    print(
        f"\nSanity check (current metric reproduced from stored data): "
        f"{len(runs) - len(mismatches)}/{len(runs)} runs match."
    )
    if mismatches:
        print("MISMATCHES FOUND - stopping before computing the new metric:")
        for m in mismatches:
            print(f"  - {m}")
        return 1
    print("Sanity check passed: 40/40 (skills verdict and category both reproduced exactly).")

    variants = [
        run_variant(runs, profile, n=n, apply_cap=apply_cap)
        for n in (2, 3)
        for apply_cap in (True, False)
    ]

    print(
        "\nVariant results (N / cap / category correct run1 / run2 / "
        "different-category count / meets rule 5):"
    )
    for v in variants:
        acc1 = v["category_accuracy_by_run"][1]
        acc2 = v["category_accuracy_by_run"][2]
        n_corr1 = v["n_correct_category_by_run"][1]
        n_corr2 = v["n_correct_category_by_run"][2]
        print(
            f"  N={v['n']} cap={v['apply_cap']!s:5} "
            f"run1={n_corr1}/{v['n_listings']} ({acc1:.1%}) "
            f"run2={n_corr2}/{v['n_listings']} ({acc2:.1%}) "
            f"diff={v['n_different_category_between_runs']} "
            f"meets_rule_5={v['meets_rule_5']}"
        )

    result = {
        "n_listings": n_listings,
        "n_runs": len(runs),
        "sanity_check": {"mismatches": mismatches, "passed": not mismatches},
        "variants": variants,
    }
    OUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
