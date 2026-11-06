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
