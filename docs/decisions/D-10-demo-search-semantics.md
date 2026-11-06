# D-10: Demo-mode search semantics vs. the ">50 results, narrow" refinement

## Question

Demo scenario S1 (spec §3.2) and FR-03 AC1/AC3 describe refinement in both
directions: "with `total > 50` the agent narrows... with `total < 3` it
broadens". The committed fixture set (D-8) has 43 listings total. Can
`FixtureSource.search()` ever report `total > 50` so demo mode can show the
narrowing direction, or does demo mode only exercise the broadening
direction - and if so, is that acceptable, or does something need to
change?

## Context

`FixtureSource.search()` (built this session, WP-03) filters the 43
committed listings by keyword/location/employment-type match and reports
`total = len(matching)`. Measured against the real fixture data:

| Query | `total` |
|---|---|
| "Python" / Hamburg | 2 |
| "Nonexistent Role Xyz" / Hamburg | 0 |
| "Entwickler" / Hamburg, radius 200 km | 6 |

The widest query I could construct (a single common German job-title
keyword, radius widened to 200 km) still returns single digits, because
the ceiling is the fixture set's total size (43) minus whatever the
keyword/location/temp-agency filter removes - `total` can **structurally
never exceed 43**, let alone 50. This is exactly the limitation the WP-03
prompt predicted before I measured it.

The *broadening* direction ("too few, widen") is already demonstrable
today with no further change: a narrow or empty-match query naturally
returns 0-2 results, which is exactly the `< 3` condition FR-03 AC1 asks
the agent to react to.

## Options

1. **Accept the limitation; demo mode only shows "broaden".** The ">50,
   narrow" direction is demoed against the *live* API instead (any common
   keyword search over a real German city returns well over 50 - confirmed
   by D-1's own spike numbers, e.g. "Softwareentwickler" nationwide).
   FR-03 AC3 ("the trace of demo scenario S1 shows at least one
   refinement") is satisfied either way - the spec does not require *which*
   direction. Zero code change; only the demo script (S6 of this WP,
   `scripts/run_core_journey.py`) needs to pick a query that happens to
   broaden in demo mode, and run S1's narrowing half, if wanted for the
   review, against the live API separately.
2. **Inflate the reported `total` in demo mode** (e.g. report a multiple of
   the real match count, or a fixed large number, while still only
   returning the real matching listings up to 25). Lets demo mode exercise
   the narrowing branch on command, but the number shown to the model (and,
   transitively, anything printed in a trace or shown to a reviewer) would
   be fabricated - in tension with CLAUDE.md invariant 6 ("evaluation runs
   on the fixture set, so results are reproducible") and with FR-19 AC2's
   demo-mode banner, which exists precisely so nothing in demo mode is
   mistaken for real. I would not ship fabricated counts even behind that
   banner.
3. **Grow the committed fixture set with enough additional crafted,
   clearly-fictional listings sharing one common keyword** (e.g. 15-20 more
   "Softwareentwickler" listings) so a real search genuinely clears 50.
   Honest (no fabricated numbers), but a non-trivial amount of new
   synthetic content to author and clean, for a single demo moment; also
   dilutes the fixture set's value as a sample of real BA ad language and
   structure (D-8's rationale for committing the real cleaned listings in
   the first place) with 3-4x as many fictional ones.

## Recommendation (superseded - see Decision)

Option 1. The spec's actual requirement (FR-03 AC3) is "at least one
refinement shown", not "both directions shown in demo mode specifically",
and the broadening direction is already exercised for free by the real
data. Option 2 fabricates a number a reviewer could see, which is the one
thing I'd rather stop and ask about than do quietly. Option 3 is honest
but disproportionate effort for one demo moment, and works against D-8's
reason for wanting real listings at all.

## Option 4 (Ingo's decision, not drafted above)

**`FixtureSource` replays the recorded D-1 search responses.** For a query
that exactly matches one of the 5 fixed searches `spikes/ba_api_spike.py`
ran (keywords, location, radius, published-within-days), report the *real*
recorded `maxErgebnisse` as `total`, and return whichever of its
referenced listings happen to exist in the committed set (filtered by
`exclude_temp_agency` as usual) rather than the normal keyword-filter
count. Every other query still falls back to filtering the 43 committed
listings as before.

Implemented as `scripts/build_fixtures.py::build_recorded_searches()`,
writing a second, small committed file,
`data/samples/fixtures/recorded_searches.json` (query params + the real
`total` + reference numbers only - no ad text, no listing fields; checked
by `tests/test_fixtures.py`). `ba_client.FixtureSource` loads it as an
optional sibling of `listings.json` and tries an exact match before
falling back to the existing filter logic (`tests/test_ba_client.py`,
4 new tests).

Why this beats my own three options: it is neither fabricated (Option 2 -
the 103 for "Softwareentwickler"/München really happened, D-1, 2026-11-05)
nor does it require authoring new fictional content (Option 3) nor does it
give up on demoing the narrow direction in demo mode at all (Option 1) -
it just reuses data the project already collected and already trusted
enough to build the cleaned fixture set from in the first place.

## Re-run: S1 in demo mode with "Softwareentwickler" / München

`scripts/run_core_journey.py`, demo mode (`FixtureSource`), same user
message pattern as the live S1 run but naming the query directly:
"Find Softwareentwickler jobs in München." Result and the rest of the
summary are in `spikes/NOTES.md` § "WP-03 core journey", appended below
the live run's entry.

## Consequences

- `scripts/build_fixtures.py` gained `build_recorded_searches()` and now
  writes two files, not one; `ba_client.FixtureSource` gained the replay
  check (`_recorded_match`); `tests/test_ba_client.py` and
  `tests/test_fixtures.py` gained coverage for both.
- No spec change needed - FR-03 AC1/AC3 and FR-19 AC1 already permit this
  reading; `recorded_searches.json` is just a second fixture file, same
  category as `listings.json` under D-8's already-decided Option 1.
- The other 4 recorded queries (Python/Hamburg: 4, AI Engineer/Hamburg: 42,
  Java/Hamburg: 9, Machine Learning/Berlin: 18) are available the same way
  if a different demo query is wanted later; only München crosses 50.

**Decision:** Option 4 - replay the 5 recorded D-1 search totals via a new
`recorded_searches.json` fixture file; demo mode now genuinely shows the
">50, narrow" refinement direction for "Softwareentwickler" / München
(total 103). - Ingo, 2026-11-06

## Addendum (2026-11-06, decided by Ingo): corrupted referenznummern, and autonomous narrowing

Two follow-up fixes, both decided by Ingo the same day.

### 1. `recorded_searches.json` had 3 corrupted reference numbers

The raw D-1 search responses (`spikes/fixtures/search/*.json`) were scrubbed
by the same context-free phone regex as the details responses (the
original D-1/D-4 regression) - corrupting 3 referenznummern inside the
search results too, not just inside the details files (e.g.
`19522-0068291613-S` -> `19522-[TELEFON]-S`). `build_recorded_searches()`
was reading `referenznummer` straight from those scrubbed search files, so
`recorded_searches.json` shipped with 3 corrupted entries.

Fixed: `scripts/build_fixtures.py::recover_referenznummer()` never reads a
referenznummer from the search files as truth - every one is matched
against the already-correct `listings.json` (built from the details
files' names, never corrupted), either by case-insensitive equality (an
uncorrupted entry) or by prefix/suffix around the `[TELEFON]` artifact (a
corrupted one, unambiguous match required). A reference that was never
detail-fetched (not in `listings.json` at all - true for all 25 of
München's own recorded results) is simply dropped from
`referenznummern`, never kept as an unverifiable guess. New test:
`tests/test_fixtures.py::test_recorded_search_referenznummern_exist_in_listings_and_are_uncorrupted`
(every referenznummer in the committed file exists in `listings.json` and
contains no `[`), plus 6 unit tests for `recover_referenznummer` itself in
`tests/test_build_fixtures.py`.

### 2. Autonomous narrowing (FR-03 AC1), not "ask first"

`prompts/system.md` now tells the model to narrow **on its own**, using
the profile (skills, seniority, radius) and a shorter publication age,
when a search returns more than 50 results - only asking the user if that
still is not enough. This needed the profile to actually be visible to the
model, which it was not before: a new middleware,
`middleware/profile_context.py`
(`LoadProfileContextMiddleware`), injects a one-off message describing the
selected user's profile the first time a thread calls the model. Wired
into `agent.py` right after the input guard.

`ba_client.FixtureSource` gained a second match path,
`_narrows_recorded_query`: a query that keeps a recorded query's keywords
as a subset of its own (same location, radius and publication age the
same or smaller) is treated as narrowing that specific recorded search -
filtered to *that search's own* referenznummern, restricted further to
`listings.json`, never to the full 43-listing committed set. `total` is
the honest count of that intersection, which can legitimately be 0 if none
of a recorded query's own results happen to be in the committed set (true
for München, confirmed below) - no number is ever invented either
direction. A query that drops or changes a recorded query's keywords
instead of extending them falls through to the ordinary, unrestricted
filter over the whole committed set, as before. 5 new tests in
`tests/test_ba_client.py`.

### Re-run result: honest, did not reach assess_fit

Demo mode, real model, same single-message pattern as before: "Find
Softwareentwickler jobs in München." Full trace:

| # | `search_jobs` call | Result |
|---|---|---|
| 1 | `Softwareentwickler` / München, 25 km, 28 days | **total: 103** (exact replay) |
| 2 | `Senior Softwareentwickler Python FastAPI` / München, 25 km, 28 days | narrowed from the recorded query - **total: 0** |
| 3 | `Softwareentwickler Python Java Docker PostgreSQL CI/CD` / München, 25 km, **60 days** | wider publication age than the recorded query, so not "narrowing" - falls through to the full-set filter - **total: 0** |

The agent narrowed **autonomously, without asking first** - exactly the
new instruction - using the profile's seniority and several of its skills
across two attempts, within the 3-calls-per-message limit. Only after
both narrowed searches came back empty did it stop and ask the user,
explicitly diagnosing *why*: "your stored profile is for Hamburg with a
25 km radius... that limited useful refinements when you asked for
München." It never called `get_job_details` or `assess_fit` - **the trace
does not reach "details -> assess_fit"** for this specific query.

This is a correct, honest outcome, not a bug: confirmed directly against
`recorded_searches.json` - the München recorded search's own 25 reference
numbers have **zero overlap** with the 40 detail-fetched listings in
`listings.json` (the 40-detail budget in the original D-1 spike was spent
on the other 4 searches, run before München in `spikes/ba_api_spike.py`'s
list, before München's own results were ever reached). No keyword
narrowing of *that specific recorded search* can honestly return anything
but 0, because we have no real ad data for any of its original results.
The mechanism (autonomous, profile-driven narrowing; honest, non-invented
totals) works exactly as specified; this particular query is simply the
wrong one to demo "narrow -> assess_fit" end-to-end with, because of a
data-coverage gap from the original D-1 spike's fetch order. A different
recorded query with the same issue is unlikely: "AI Engineer"/Hamburg
(total 42, not >50 but close) has 24 of its results in `listings.json`,
and the other 3 searches (Python/Hamburg, Java/Hamburg, ML/Berlin) have
partial overlap too (see their `referenznummern` counts in
`recorded_searches.json`) - München is the one search whose detail
fetching happened to be fully crowded out.

Full machine-readable trace: `eval/results/d10_addendum_verification.json`
(CLAUDE.md: evaluation/spike results go to `eval/results/` or `spikes/` as
JSON plus a short Markdown summary, never only to the terminal).

**Decision:** both fixes confirmed as described - corrupted referenznummer
recovery, and autonomous profile-driven narrowing with honest (possibly
zero) totals when narrowing a recorded query. No further fixture change
needed to "make München work"; if a guaranteed non-zero narrow-to-assess
demo is wanted later, use "AI Engineer"/Hamburg or a fresh spike run that
detail-fetches München's own results. - Ingo, 2026-11-06
