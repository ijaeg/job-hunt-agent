# D-23: `location_remote` falls to `not_met` when a remote type is stated without a percentage

Related: spec §7 "Location / remote", FR-06 AC2, D-9, WP-13 addendum 3, WP-14

## Question

`rubric._location_remote_verdict` has no path to `met`/`partly` when
`remote_type` is set (e.g. `"NACH_VEREINBARUNG"` - "by arrangement") but
`remote_percent` is `None`, for a `hybrid`- or `remote`-preference
profile: it falls through to its final `return "not_met"`. Is this
correct, or should a stated-but-unquantified remote type count for
something?

## Context

The code check (spec §7, independent of any label, WP-14 Stage 1 step 1):
tracing `_location_remote_verdict` for Alex's profile (`hybrid`,
`radius_km=25`) with `remote_type="NACH_VEREINBARUNG"`,
`remote_percent=None`, within radius:

```text
full_remote = False                      (remote_percent is None)
within_radius = True
remote_stated = True                     (remote_type is not None)
remote_satisfied = False                 (hybrid: needs full_remote or percent > 0)
-> not full_remote; not (within_radius and remote_satisfied);
   not (within_radius and not remote_stated) [remote_stated is True];
   not (not within_radius)
-> falls through to "not_met"
```

This directly contradicts Ingo's own hand-labelling rule, recorded after
reviewing the labelled set
(`docs/prompts/WP-13-fit-eval-prep.md`, addendum 3, 2026-11-16): *"within
radius or no distance + any remote wording (incl. 'nach Vereinbarung')
-> met"*.

The dev-set run confirms this is not just theoretical:
`13509-000021113EF002-S` (BWI GmbH) has `remote_type="NACH_VEREINBARUNG"`,
`remote_percent=None`, `distance_km=None` (-> within radius by the
existing "missing distance never excludes" rule). Ingo's label is `met`
("mobiles Arbeiten nach Vereinbarung" note); the app computes `not_met`
in both runs. Fixing just this one dimension on this one listing (holding
every other verdict fixed) would flip the computed category from `poor`
to `partial`, matching the label - confirmed by recomputing the §7
weighted share by hand with `location_remote: met` instead of `not_met`.

This is a one-dimension, single-cause disagreement (the other three
dimension mismatches on `13509` are tagged `extraction_error`/
`label_ambiguity` separately in `docs/fit_evaluation.md`), so the
evidence isolates this specific code path cleanly.

## Options

1. **No change.** Spec §7's table literally lists only `met`/`partly`/
   `not met` outcomes without naming this specific combination; the
   current code is *a* defensible reading (no percentage means the
   remote share can't be confirmed). Leaves a clear, demonstrated
   contradiction with Ingo's own established labelling rule unresolved.
2. **Treat any stated `remote_type` (regardless of `remote_percent`) as
   satisfying the remote preference when within radius**, i.e. add
   `remote_type is not None` to the `remote_satisfied` condition for
   `hybrid`/`remote` preferences. Matches Ingo's rule and the
   `13509` evidence exactly (`met`).
3. **Treat it as `partly` instead of `met`** - a stated-but-unquantified
   remote type is weaker evidence than a known percentage, so give it
   the same credit as "remote not stated" currently gets, not full
   credit. Does not match the specific wording of Ingo's addendum-3 rule
   ("...-> met"), which this decision file exists to confirm or correct.

## Recommendation

Option 2, following Ingo's own addendum-3 rule as written. If Ingo's
intent was closer to Option 3 when he wrote that rule, this file is the
place to say so.

## Consequences

- `src/job_hunt_agent/rubric.py`: `_location_remote_verdict`'s
  `remote_satisfied` branch for `hybrid` becomes `full_remote or
  remote_type is not None or (remote_percent is not None and
  remote_percent > 0)` (and similarly for `remote` preference, if
  Option 2 is meant to apply there too - to confirm).
- `tests/test_rubric.py`: new case,
  `test_location_met_with_stated_remote_type_but_no_percent`, plus a
  check that a *fully* unstated remote type (`remote_type=None`) still
  gets `partly`, not `met` (the existing
  `test_location_partly_within_radius_remote_not_stated` must keep
  passing).
- Dev listing this would change: `13509-000021113EF002-S` (`not_met` ->
  `met`, category `poor` -> `partial`, matching the label in both runs).
- No change to weights or the overall category thresholds.

**Decision:** Option 2, for the "hybrid" preference only (2026-11-16, Ingo). A stated remote type without a percentage (e.g. NACH_VEREINBARUNG) satisfies a hybrid preference within the radius; it does not satisfy a "remote" preference, because it does not guarantee fully remote work.
