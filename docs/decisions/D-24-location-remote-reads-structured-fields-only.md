# D-24: `location_remote` never reads the ad text, only the structured API fields

Related: spec §7 "Location / remote", §9.3, FR-06 AC2, D-20, WP-13 addendum 3, WP-14

## Question

Spec §7's source column for the location/remote dimension is "API:
`entfernung`, `homeofficetyp`, `homeofficeprozent`" - structured fields
only. Ingo's own hand-labelling, however, used the ad's free text when
those fields were empty (WP-13 addendum 3's correction rule explicitly
covers "no remote wording" vs. "any remote wording" found in the ad).
Should the rubric also read the ad text for remote-work mentions when the
structured fields carry nothing, to match how the set was actually
labelled - and if so, is that a rubric-rule change that needs its own
sign-off, separate from D-23 (which only covers a stated-but-unquantified
field value, not a missing one)?

## Context

`17338-c2de5ff0cd55000215-S` (Vertec AG, title "Python-Entwickler (w/m/d)
- **Hybrid**") has `remote_type=None`, `remote_percent=None`,
`distance_km=None` in the fixture - no structured remote signal at all,
despite the ad's own title stating "Hybrid". The app computes
`location_remote: partly` (the existing, correct rule for "within
radius, remote not stated at all" - `tests/test_rubric.py`'s
`test_location_partly_within_radius_remote_not_stated` covers exactly
this). Ingo's label is `met`.

Recomputing the weighted share with only this one dimension changed to
`met` flips the category from `poor` to `partial`, matching the label -
the same isolation method used in D-23. Unlike D-23, there is no
structured field value the code is misreading here; the signal exists
only in free text the rubric never looks at, by design (spec §7's source
column, and `docs/labelling_guide.md`'s own rule mirrors it: "a missing
distance counts as within radius" - written for distance, not remote
type, but the rubric applies the same "structured field only" discipline
to `homeofficetyp`/`homeofficeprozent`).

This is a genuine scope question, not a bug: the rubric is doing exactly
what §7 says for this dimension. The mismatch is between §7's literal
source list and how the *label* was actually produced once Ingo started
reading ad text for remote wording (addendum 3) - a labelling-process
change that happened after §7 was written and that §7 itself was never
updated to reflect.

## Options

1. **No change; keep §7 as written (structured fields only).** Simplest,
   keeps the rubric's data dependencies small and auditable. Accept that
   a title/body-only remote mention (no structured field) will keep
   disagreeing with labels produced by addendum 3's rule - document this
   as a known evaluation-methodology mismatch in
   `docs/fit_evaluation.md`, not a code defect.
2. **Extend the dimension to scan the cleaned ad text for a small, fixed
   set of remote-work keywords** (the same list addendum 3's rule
   implicitly used: "Homeoffice", "Home-Office", "mobiles Arbeiten",
   "mobile Arbeit", "remote", "hybrid", "Telearbeit", "ortsunabhängig" -
   taken from WP-13 addendum 3's own wording) when both structured
   fields are `None`, and treat a match as satisfying `remote_stated`/
   `remote_satisfied` the same way D-23's fix does for a stated-but-
   unquantified field. Matches how the set was labelled; adds a new,
   separate code path (keyword search over free text) to a dimension
   spec §7 currently scopes to structured fields only - a genuine rubric
   extension, not a bugfix, so it needs sign-off even though D-23's
   mechanism is similar.

## Recommendation

No strong recommendation either way - this is a scope call about
whether the rubric should take on free-text parsing for one dimension,
not a correctness question. Leaning slightly toward Option 1 for now:
Option 2 adds a second remote-signal source (keywords) on top of D-23's
fix to the structured-field path, and the dev set has exactly one
listing exercising it - thin evidence for a new parsing rule versus
documenting the mismatch and watching the test set.

## Consequences

- **If Option 2:** `src/job_hunt_agent/rubric.py`'s
  `_location_remote_verdict` gains an ad-text parameter and a keyword
  list (naming it precisely needs its own small follow-up, since §7's
  table would then need a new sentence for this dimension's source);
  `rubric.assess`'s signature changes to pass `details.description`
  into this one dimension function; new tests for keyword matches with
  and without word-boundary false positives (the same whole-word
  lesson D-9's addendum already learned for skills). `PRODUCT_SPEC.md`
  would need the change proposed back to Ingo per CLAUDE.md ("do not
  change `PRODUCT_SPEC.md` on your own").
- **If Option 1:** no code change; `docs/fit_evaluation.md` states the
  limitation explicitly (a title/body-only remote mention with no
  structured field will not be picked up); dev listing
  `17338-c2de5ff0cd55000215-S` stays a documented, expected
  disagreement, not a bug to fix before the test-set run.
- Either way: distinct from D-23, which only changes how a
  **present-but-unquantified** structured value is read, not whether
  free text is read at all.

**Decision:**
