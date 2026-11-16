# Fit evaluation

Related: spec §7, §9.1, §9.3, FR-05 AC2, FR-06, NFR-09, invariant 6, D-9, D-20, WP-14

Compares the code-computed fit category/verdicts (`job_hunt_agent.rubric.assess`,
run via the real extraction call) against Ingo's hand label
(`eval/fit_labels.csv`, D-20) on the labelled fit set (`eval/fit_set.yaml`, 8
development listings, 12 test listings). Run by `eval/run_fit_eval.py`, which
reuses `tools.assess`'s extraction helpers and `rubric.assess` directly (no
copy), against the committed fixture set (demo mode, invariant 6, so results
are reproducible). Each listing is extracted **twice**, independently.

Stage 1 (this document's "Development set" section) runs the 8 development
listings only and stops for decisions, per spec §9.1/invariant 6: the test
set is never used for tuning. Stage 2 ("Test set" section) is added after
Ingo's decisions on D-21–D-25 are implemented.

## Code check against spec §7 (independent of any label)

Before running anything, a direct read of `rubric.py` against spec §7's
table and source columns:

- **`befristungInMonaten`/`contract_duration` ("BEFRISTET") for employment
  type:** `rubric._employment_type_verdict` reads `details.contract_months`,
  which `ba_client.py`/`scripts/build_fixtures.py` populate straight from
  the API's `befristungInMonaten` (confirmed: every fixture listing with
  `contract_duration == "BEFRISTET"` has a non-null `contract_months`, and
  every `"UNBEFRISTET"`/`"KEINE_ANGABE"` listing has `contract_months ==
  None` - checked across all 65 fixture listings, 0 mismatches). So the
  code *does* read `befristungInMonaten` correctly for what it is. The gap
  is structural, not a misread: `befristungInMonaten` is `None` both when a
  contract is confirmed permanent (`"UNBEFRISTET"`) and when the API simply
  states nothing about duration at all (`"KEINE_ANGABE"`) - and
  `JobDetails` has no `contract_duration` field at all (unlike
  `JobSummary`, which does carry it, FR-02 AC2's compact subset). So
  `_employment_type_verdict`'s `is_permanent = details.contract_months is
  None` silently folds "confirmed permanent" and "not stated" into the same
  branch, even though spec §7's own table has a dedicated "not stated"
  verdict for this dimension. **On the dev set this caused zero actual
  disagreements** (`employment_type` dimension agreement was 1.0, see
  below) - `KEINE_ANGABE` happened to coincide with a `met` verdict every
  time a profile-matching `full_time` value was also present. No decision
  file is opened for this: no change is proposed for now, but it is worth
  re-checking once the test set (which has more `KEINE_ANGABE` listings)
  is run, in case the coincidence doesn't hold there too.
- **A stated remote type without a percentage ("NACH_VEREINBARUNG") for
  location/remote:** traced by hand for Alex's `hybrid`-preference profile,
  within radius: `_location_remote_verdict` computes `full_remote = False`
  (no percentage), `remote_stated = True` (the type *is* set), so the
  "remote not stated -> partly" branch never fires (it requires `not
  remote_stated`), and `remote_satisfied` is `False` for `hybrid`/`remote`
  preferences (it only credits `full_remote` or `remote_percent > 0`, both
  false here) - the function falls through to its final `return
  "not_met"`. Spec §7 is silent on this exact combination; it directly
  contradicts the hand-labelling correction rule Ingo recorded while
  reviewing the labelled set (WP-13 addendum 3: "...+ any remote wording
  (incl. 'nach Vereinbarung') -> met"). **This caused a real dev-set
  disagreement** (`13509-000021113EF002-S`, see below) - see D-23.

## Development set

**Run:** `uv run python eval/run_fit_eval.py --set dev`, 2026-11-16.
`openai/gpt-5-mini`, reasoning effort `low` (`config.CHAT_MODEL`/
`config.REASONING_EFFORT` defaults). 8 listings, 2 runs each. Full output:
`eval/results/fit_eval_dev.json`.

### Numbers

| Metric | Run 1 | Run 2 |
|---|---|---|
| Category accuracy (vs. label) | 25.0 % (2/8) | 37.5 % (3/8) |
| Skills dimension agreement | 37.5 % | 50.0 % |
| Location/remote dimension agreement | 75.0 % | 75.0 % |
| Seniority dimension agreement | 50.0 % | 50.0 % |
| Language dimension agreement | 75.0 % | 75.0 % |
| Employment type dimension agreement | 100 % | 100 % |

**Confusion matrix** (rows = Ingo's label, columns = app category; identical
both runs except where noted):

| label \ app | strong | partial | poor | excluded |
|---|---|---|---|---|
| strong | 0 | 0 | 0 | 0 |
| partial | 0 | 1 | 3 | 0 |
| poor | 0 | 3 (run 1) / 2 (run 2) | 0 (run 1) / 1 (run 2) | 0 |
| excluded | 0 | 0 | 0 | 1 |

No dev listing is labelled `strong` (consistent with spec §9.3's eventual
limitation that the labelled set has no `strong` example at all - see
"Limitations" once the test set is added).

**`dropped_evidence`: 58** across the 16 runs (8 listings x 2), 3.6 per run
on average - see D-21.

**Run-to-run agreement:** category 7/8 (87.5 %); per-dimension 46/48
(95.8 %) across all 8 listings x 6 fields. The two mismatches are both on
`12288-4971252625-S` (category and skills; D-21's "all evidence dropped"
failure mode, see below) - every other listing's two runs agree on every
field.

### Every disagreement, with cause

36 disagreements total (category + 5 dimensions, 2 runs, 8 listings).
Classified by reading the ad text and the extraction output against §7,
then re-saved into `eval/results/fit_eval_dev.json` (`cause` field per
disagreement, `cause_summary` for the totals) via `attach_cause`/
`summarize_causes` (`eval/run_fit_eval.py`, unit-tested with fixed fake data
in `tests/test_run_fit_eval.py`, NFR-05).

| Cause | Count |
|---|---|
| `extraction_error` | 16 |
| `label_ambiguity` | 8 |
| `data_issue` | 4 |
| `code_deviation` | 4 |
| `rubric_rule_or_threshold` | 4 |

- **`extraction_error` (16):** dominated by the skill-granularity problem
  (D-21) - the model frequently extracts full requirement sentences as
  `Requirement.name` instead of atomic skill names (e.g. "Planung,
  Entwicklung und Konfiguration von Simulationsnetzwerken und deren
  Komponenten (HW und SW)" as one "skill" on `11119-4964515256-S`), which
  can never whole-word-match a profile skill and is fragile against the
  verbatim-evidence check. One case (`19913-3074751792188001-S`'s
  seniority) is a different, title-only mechanism - see D-22.
- **`label_ambiguity` (8):** mostly seniority/language verdicts where
  Ingo's label implies a judgment from context (experience requirements,
  degree requirements) that the ad never states as an explicit level/
  language word - exactly the "unknown vs. not met" distinction
  `docs/labelling_guide.md` calls out as needing care, now showing up as a
  real, recorded gap between "nothing extractable" and "a human's
  contextual read."
- **`data_issue` (4):** `17338-c2de5ff0cd55000215-S`'s category and
  location/remote - the ad's own title says "Hybrid" but both structured
  remote fields are `None` in the fixture; §7 does not tell the rubric to
  read ad text for this dimension (see D-24).
- **`code_deviation` (4):** `13509-000021113EF002-S`'s category and
  location/remote - `remote_type="NACH_VEREINBARUNG"` is stated but the
  code has no path to `met`/`partly` for a stated-without-percentage
  value, contradicting Ingo's own addendum-3 labelling rule (D-23).
- **`rubric_rule_or_threshold` (4):** `12336-a26f1128j0452080-S` and
  `13635-d780e451_JB5286154-S`'s category, both runs each - every
  dimension verdict matches the label exactly, but `skills: not_met`
  (weight 2) is still outvoted by three `met`/`partly` dimensions in the
  weighted-average share (lands at exactly 50 %, above the 45 % `partial`
  threshold); Ingo calls both `poor` (D-25).

## Decisions arising from the development set

Five decision files, each with dev-set-only evidence, options, a
recommendation and which dev listings would change:

- [D-21](decisions/D-21-skill-extraction-granularity.md) - constrain
  `Requirement.name` to atomic skill names; also fix the "all evidence
  dropped -> unknown" failure mode.
- [D-22](decisions/D-22-extraction-prompt-title.md) - pass the listing
  title to the extraction prompt (seniority is sometimes title-only).
- [D-23](decisions/D-23-remote-type-without-percent.md) - `location_remote`
  should credit a stated-but-unquantified remote type.
- [D-24](decisions/D-24-location-remote-reads-structured-fields-only.md) -
  whether `location_remote` should also read ad text when the structured
  fields are empty (open question, no recommendation either way).
- [D-25](decisions/D-25-category-threshold-skills-not-met.md) - whether
  `skills: not_met` should cap the category at `poor`.

**Stop rule reached: Stage 1 complete.** The test set (12 listings) is not
run until Ingo's answers on D-21–D-25 are recorded and implemented (spec
§9.1, invariant 6).
