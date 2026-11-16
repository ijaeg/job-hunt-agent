"""Selects the 20-listing fit evaluation set (spec §9.1, §9.3, WP-13, D-20).

Picks from the committed fixture set's **real** listings only (excludes the
3 crafted ``FIKTIV-*`` demo listings, D-8) - no app run, no model call, no
rubric computation. Stratifies on features visible in the raw listing data
alone, so each stratum lines up with one of the fit categories the Alex
profile (``data/samples/profile_alex.yaml``) could plausibly reach:

- ``temp_agency``: ``is_temp_agency is True`` -> a hard exclusion (FR-06
  AC1) regardless of anything else, so these candidates for ``excluded``.
- ``skill_match``: not temp agency, and "Python" or "Java" occurs as a
  whole word in the title or description - a weak proxy for the
  heaviest-weighted rubric dimension (§7 "Skills", weight 2), so these are
  candidates for ``strong``/``partial``.
- ``no_skill_match``: neither - candidates for ``poor``/``partial`` (most
  still describe software-adjacent roles, e.g. C#/.NET or DevOps, that may
  still score on other skills; a few are genuinely unrelated to software
  development, e.g. "Manager Digital Risk - Consulting").

**Allocation (Ingo, 2026-11-16, revising the first proportional draft):**
fixed per stratum, not proportional to pool size - ``temp_agency`` 3 (1
dev / 2 test), ``skill_match`` 9 (3 dev / 6 test), ``no_skill_match`` 8 (4
dev / 4 test). Proportional allocation would have given ``temp_agency`` 7
of the 20, but that dimension is excluded by code from one structured
field alone (``is_temp_agency``), so a large share of it would inflate
agreement without testing the LLM extraction the other dimensions depend
on.

**Employer cap:** at most 2 of the 20 listings share an employer, checked
across the whole set, not per stratum. Within each stratum, listings are
shuffled with a single ``random.Random(SEED)`` continued across strata and
taken in that shuffled order, dev first then test; a listing that would
put its employer over the cap is skipped and the next one in that
stratum's shuffled order is tried instead (redraw within the stratum, per
Ingo's instruction) - so the whole selection is reproducible from this
file alone.

Usage (from the project root):
    uv run python scripts/select_fit_set.py

Writes:
    eval/fit_set.yaml

Related: spec §7, §9.1, §9.3, invariant 6, D-9, D-20, WP-13
"""

from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LISTINGS_PATH = PROJECT_ROOT / "data" / "samples" / "fixtures" / "listings.json"
RECORDED_SEARCHES_PATH = PROJECT_ROOT / "data" / "samples" / "fixtures" / "recorded_searches.json"
OUT_PATH = PROJECT_ROOT / "eval" / "fit_set.yaml"

#: Fixed seed for the stratified random selection (WP-13). Changing it
#: changes the selection - do not change it without a new decision record.
SEED = 1300

#: Fixed per-stratum allocation and its dev share (Ingo, 2026-11-16) - see
#: the module docstring for why this isn't proportional to pool size. The
#: test share of each stratum is simply the rest of its total allocation.
TOTAL_ALLOCATION: dict[str, int] = {"temp_agency": 3, "skill_match": 9, "no_skill_match": 8}
DEV_ALLOCATION: dict[str, int] = {"temp_agency": 1, "skill_match": 3, "no_skill_match": 4}

#: Expected totals (spec §9.1), checked against the allocations above.
TOTAL = 20
DEV_TOTAL = 8
TEST_TOTAL = 12

#: At most this many selected listings may share one employer, across the
#: whole set (Ingo, 2026-11-16) - keeps one prolific poster (e.g. NTT DATA,
#: 9 of the 62 real listings) from dominating the fit-category spread.
EMPLOYER_CAP = 2

#: Crafted demo listings are excluded from the pool (D-8, D-20 context).
CRAFTED_PREFIX = "FIKTIV"


def _whole_word(token: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(token)}(?!\w)", re.IGNORECASE)


_PYTHON_RE = _whole_word("Python")
_JAVA_RE = _whole_word("Java")


def stratum(listing: dict[str, Any]) -> str:
    """Assigns one of the three data-visible strata to a real listing."""
    if listing["is_temp_agency"] is True:
        return "temp_agency"
    text = f"{listing['title']} {listing['description']}"
    if _PYTHON_RE.search(text) or _JAVA_RE.search(text):
        return "skill_match"
    return "no_skill_match"


def data_coverage_report(real: list[dict[str, Any]], ref_to_queries: dict[str, list[str]]) -> str:
    """The Part A "Checks #4" report: per-feature counts in the real fixture pool."""
    strata = Counter(stratum(listing) for listing in real)
    temp_agency_unknown = sum(1 for listing in real if listing["is_temp_agency"] is None)
    distance_known = sum(1 for listing in real if listing["distance_km"] is not None)
    low_evidence = sum(1 for listing in real if listing["low_evidence"])
    in_any_search = sum(1 for listing in real if listing["referenznummer"] in ref_to_queries)
    full_remote = sum(1 for listing in real if (listing.get("remote_percent") or 0) >= 100)
    lines = [
        f"real listings in pool: {len(real)} (of {len(real)} + 3 crafted)",
        f"  temp_agency (True):     {strata['temp_agency']}",
        f"  skill_match (Py/Java):  {strata['skill_match']}",
        f"  no_skill_match:         {strata['no_skill_match']}",
        f"  is_temp_agency unknown (None): {temp_agency_unknown}",
        f"  distance_km known: {distance_known}, unknown: {len(real) - distance_known}",
        f"  low_evidence: {low_evidence}",
        f"  remote_percent >= 100 (full remote): {full_remote}",
        f"  appears in >=1 of the 5 recorded searches: {in_any_search}",
    ]
    return "\n".join(lines)


def main() -> int:
    listings: list[dict[str, Any]] = json.loads(LISTINGS_PATH.read_text(encoding="utf-8"))
    real = [
        listing for listing in listings if not listing["referenznummer"].startswith(CRAFTED_PREFIX)
    ]

    recorded = json.loads(RECORDED_SEARCHES_PATH.read_text(encoding="utf-8"))
    ref_to_queries: dict[str, list[str]] = {}
    for query in recorded:
        for ref in query["referenznummern"]:
            ref_to_queries.setdefault(ref, []).append(f"{query['keywords']}/{query['location']}")

    report = data_coverage_report(real, ref_to_queries)
    print(report)

    by_stratum: dict[str, list[dict[str, Any]]] = {
        "temp_agency": [],
        "skill_match": [],
        "no_skill_match": [],
    }
    for listing in real:
        by_stratum[stratum(listing)].append(listing)

    stratum_sizes = {name: len(items) for name, items in by_stratum.items()}
    total_alloc = TOTAL_ALLOCATION
    dev_alloc = DEV_ALLOCATION
    test_alloc = {name: total_alloc[name] - dev_alloc[name] for name in total_alloc}
    assert sum(total_alloc.values()) == TOTAL
    assert sum(dev_alloc.values()) == DEV_TOTAL
    assert sum(test_alloc.values()) == TEST_TOTAL

    rng = random.Random(SEED)
    employer_count: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []
    for name in ("temp_agency", "skill_match", "no_skill_match"):
        shuffled = by_stratum[name][:]
        rng.shuffle(shuffled)
        accepted: list[dict[str, Any]] = []
        for listing in shuffled:
            employer = listing["employer"]
            if employer_count[employer] >= EMPLOYER_CAP:
                continue
            accepted.append(listing)
            employer_count[employer] += 1
            if len(accepted) == total_alloc[name]:
                break
        if len(accepted) < total_alloc[name]:
            raise RuntimeError(
                f"stratum {name!r}: only {len(accepted)} of {total_alloc[name]} "
                f"listings fit under the employer cap of {EMPLOYER_CAP}"
            )
        for index, listing in enumerate(accepted):
            set_name = "dev" if index < dev_alloc[name] else "test"
            rows.append(
                {
                    "referenznummer": listing["referenznummer"],
                    "title": listing["title"],
                    "employer": listing["employer"],
                    "stratum": name,
                    "set": set_name,
                }
            )

    doc = {
        "seed": SEED,
        "rule": (
            "Stratify the 62 real fixture listings (FIKTIV-* crafted demo listings "
            "excluded) into temp_agency (is_temp_agency is True), skill_match "
            "(Python or Java as a whole word in title+description, and not "
            "temp_agency), no_skill_match (neither). Allocate a fixed 3/9/8 of the "
            "20 to temp_agency/skill_match/no_skill_match (1/3/4 dev, 2/6/4 test) - "
            "not proportional to pool size, so the code-only temp_agency exclusion "
            "does not dominate the set (Ingo, 2026-11-16). Within each stratum, "
            f"shuffle with a single random.Random({SEED}) continued across strata "
            "and take dev first, then test, from that shuffled order, skipping (and "
            "so redrawing further down that stratum's order) any listing that would "
            f"put its employer over a cap of {EMPLOYER_CAP} across the whole set "
            "(Ingo, 2026-11-16). No app run, no model call, no rubric computation."
        ),
        "approval": {
            "date": "2026-11-16",
            "by": "Ingo",
            "note": (
                "First draft used proportional allocation (7/6/7) and no employer "
                "cap - NTT DATA Deutschland SE alone would have contributed 4 of "
                "20. Approved with the fixed 3/9/8 allocation and the employer cap "
                "above; seed and shuffle-then-take procedure unchanged."
            ),
        },
        "counts_in_pool": dict(stratum_sizes),
        "allocation": {"total": total_alloc, "dev": dev_alloc, "test": test_alloc},
        "employer_cap": EMPLOYER_CAP,
        "listings": rows,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as handle:
        yaml.dump(doc, handle, allow_unicode=True, sort_keys=False, width=100)
    print(f"\nWrote {len(rows)} listings to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
