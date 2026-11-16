# Fit evaluation

Related: spec §7, §9.1, §9.3, FR-05 AC2, FR-06, NFR-09, invariant 6, D-9, D-20, WP-14

Compares the code-computed fit category/verdicts (`job_hunt_agent.rubric.assess`,
run via the real extraction call) against Ingo's hand label
(`eval/fit_labels.csv`, D-20) on the labelled fit set (`eval/fit_set.yaml`, 8
development listings, 12 test listings). Run by `eval/run_fit_eval.py`, which
reuses `tools.assess`'s extraction helpers and `rubric.assess` directly (no
copy), against the committed fixture set (demo mode, invariant 6, so results
are reproducible). Each listing is extracted **twice**, independently.

Stage 1 (this document's "Development set" section) ran the 8 development
listings only and stopped for decisions, per spec §9.1/invariant 6: the test
set is never used for tuning. Ingo's decisions on D-21–D-25 are recorded
(2026-11-16); Stage 2 implemented the decided changes, re-ran the
development set once more to confirm the fixes (numbers below, next to the
Stage 1 numbers), then ran the 12-listing test set **once**, with no further
changes after that run.

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
  is run, in case the coincidence doesn't hold there too. **Update
  (test-set run):** the coincidence did not hold - `12336-a26f539j0436667-S`
  (`contract_duration: "KEINE_ANGABE"`, `full_time: true`) computes
  `employment_type: met`, Ingo's label is `not_met` - see "Test set"
  below and the `code_deviation` cause in its disagreement table. No code
  change was made (test-set findings are not used for tuning, spec §9.1).
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

## Decisions

Ingo's decisions on all five, recorded 2026-11-16 (read each file's
**Decision** line for the exact wording):

- [D-21](decisions/D-21-skill-extraction-granularity.md) - **Option 2
  only** (deviates from the file's own Option-3 recommendation): constrain
  `Requirement.name` to atomic skill names via a field description and a
  worked example in the extraction prompt; the all-evidence-dropped case
  stays scored `unknown`, not `not_met` - "a missing evidence must never
  count against a listing" (FR-06 AC3 principle). If it recurs, report it
  rather than change the scoring.
- [D-22](decisions/D-22-extraction-prompt-title.md) - **Option 2**: pass
  the listing title to the extraction prompt; verbatim evidence still
  comes from the ad text only.
- [D-23](decisions/D-23-remote-type-without-percent.md) - **Option 2, for
  the "hybrid" preference only**: a stated remote type without a
  percentage satisfies a hybrid preference within radius; it does **not**
  satisfy a "remote" preference (no guaranteed full remote work).
- [D-24](decisions/D-24-location-remote-reads-structured-fields-only.md) -
  **Option 1**: no code change; `location_remote` keeps reading the
  structured fields only (spec §7 as written). The limitation is
  documented below.
- [D-25](decisions/D-25-category-threshold-skills-not-met.md) - **Option
  3**: `skills: not_met` caps the category at `poor`; hard exclusions
  still win over everything (FR-06 AC4).

Implemented in `src/job_hunt_agent/models.py` (D-21's field description),
`prompts/extract_requirements.md` (D-21's worked example, D-22's title
placeholder), `src/job_hunt_agent/tools/assess.py` (D-22's title
parameter) and `src/job_hunt_agent/rubric.py` (D-23's hybrid-only
`remote_satisfied` branch, D-25's skills cap), each with new tests
(`tests/test_rubric.py`, `tests/test_tools_assess.py`).

## Development set

**Two runs, 2026-11-16: before (Stage 1, pre-decisions) and after (Stage 2,
D-21/D-22/D-23/D-25 implemented).** `openai/gpt-5-mini`, reasoning effort
`low` (`config.CHAT_MODEL`/`config.REASONING_EFFORT` defaults). 8 listings,
2 runs each both times. Full output: `eval/results/fit_eval_dev_stage1.json`
(before) and `eval/results/fit_eval_dev.json` (after, current).

### Numbers, before -> after

| Metric | Run 1 (before -> after) | Run 2 (before -> after) |
|---|---|---|
| Category accuracy (vs. label) | 25.0 % -> 50.0 % | 37.5 % -> 50.0 % |
| Skills dimension agreement | 37.5 % -> 50.0 % | 50.0 % -> 50.0 % |
| Location/remote dimension agreement | 75.0 % -> 87.5 % | 75.0 % -> 87.5 % |
| Seniority dimension agreement | 50.0 % -> 62.5 % | 50.0 % -> 62.5 % |
| Language dimension agreement | 75.0 % -> 75.0 % | 75.0 % -> 75.0 % |
| Employment type dimension agreement | 100 % -> 100 % | 100 % -> 100 % |

`dropped_evidence`: **58 -> 40** across the 16 runs (D-21's granularity fix
reduced it by 31 %, but did not eliminate it - see below).

**Confusion matrix, after** (rows = Ingo's label, columns = app category;
identical both runs):

| label \ app | strong | partial | poor | excluded |
|---|---|---|---|---|
| strong | 0 | 0 | 0 | 0 |
| partial | 0 | 0 (run 1) / 1 (run 2) | 4 (run 1) / 3 (run 2) | 0 |
| poor | 0 | 0 (run 1) / 1 (run 2) | 3 (run 1) / 2 (run 2) | 0 |
| excluded | 0 | 0 | 0 | 1 |

**Run-to-run agreement, after:** category and every dimension identical
between the two runs for 7 of 8 listings; `12336-a26f1192j0456061-S` (D-21's
granularity fix still extracts a different-sized skill list run to run,
flipping `skills`/`category` once) is the only mismatch.

**The D-21/D-22/D-23 fixes confirmed working as intended:**
`13509-000021113EF002-S`'s `location_remote` is now `met` in both runs
(was `not_met`, D-23's hybrid fix); `12336-a26f1128j0452080-S` and
`13635-d780e451_JB5286154-S`'s categories are now `poor` in both runs,
matching the label (D-25's skills cap); extracted skill names are now
short and atomic (e.g. "C++", "Qt", "Cisco Switchen" instead of full
requirement sentences, D-21).

**The all-evidence-dropped case recurred, as anticipated by D-21 - reported,
not fixed:** `12288-4971252625-S` run 2 extracted 21 skills, all 21 dropped
for non-verbatim evidence (`dropped_evidence: 20` on this run alone),
leaving `skills: unknown` and `category: partial`; the label is `poor`. Run
1 of the same listing extracted none of this problem (0 skills dropped,
`skills: not_met`, `category: poor`, matching the label) - the instability
is in the model's run-to-run extraction yield, not the scoring rule, which
D-21's decision explicitly kept as `unknown` rather than `not_met`.

### Every disagreement, with cause (after)

28 disagreements (down from 36 before). Classified the same way as Stage 1
(reading the ad text and extraction output against §7) and recorded via
`attach_cause`/`summarize_causes` into `eval/results/fit_eval_dev.json`.

| Cause | Before | After |
|---|---|---|
| `rubric_rule_or_threshold` | 4 | 14 |
| `label_ambiguity` | 8 | 6 |
| `extraction_error` | 16 | 6 |
| `data_issue` | 4 | 2 |
| `code_deviation` | 4 | 0 |

`code_deviation` and most of `extraction_error`/`data_issue` dropped out as
D-21/D-22/D-23 took effect. `rubric_rule_or_threshold` **grew**, not
because anything got worse, but because D-25's cap now fires every time
the skills share lands under 40 % - and that 40 % threshold is still
strict enough, even with atomic skill names, that a long but genuinely
relevant skill list (e.g. `19913-3074751792188001-S`'s NTT DATA AI-platform
ad, which correctly extracts "Python", "FastAPI", "Docker" among ~34
skills) still scores `not_met` by raw share. This generalises much further
on the test set below - see "Limitations".

## Test set

**Run once, 2026-11-16** (spec §9.1/invariant 6: never used for tuning, no
code change after this run). `openai/gpt-5-mini`, reasoning effort `low`.
12 listings, 2 runs each. Full output: `eval/results/fit_eval_test.json`.

### Numbers

| Metric | Run 1 | Run 2 |
|---|---|---|
| **Category accuracy (vs. label)** | **33.3 % (4/12)** | **33.3 % (4/12)** |
| Skills dimension agreement | 25.0 % | 25.0 % |
| Location/remote dimension agreement | 66.7 % | 66.7 % |
| Seniority dimension agreement | 58.3 % | 50.0 % |
| Language dimension agreement | 83.3 % | 83.3 % |
| Employment type dimension agreement | 83.3 % | 83.3 % |

**4x4 confusion matrix** (rows = Ingo's label, columns = app category;
identical both runs):

| label \ app | strong | partial | poor | excluded |
|---|---|---|---|---|
| **strong** | 0 | 0 | 0 | 0 |
| **partial** | 0 | 0 | 7 | 0 |
| **poor** | 0 | 0 | 2 | 0 |
| **excluded** | 0 | 0 | 1 | 2 |

`dropped_evidence`: **9** across the 24 runs (12 listings x 2) - far lower
than the dev set's 40, confirming D-21's granularity fix holds up on a
larger, unseen sample.

**Run-to-run agreement:** category **12/12 (100 %)**; per-dimension **59/60
(98.3 %)** - only `10001-1003893191-S`'s seniority verdict differs between
the two runs (`met` vs. `partly`). Reproducibility is markedly better than
the dev set's Stage-1 run (87.5 %/95.8 %), consistent with D-21's
atomic-skill fix also stabilising extraction generally.

### Every disagreement, with cause

61 disagreements across 12 listings x 2 runs x 6 fields (72 comparisons) -
a 84.7 % disagreement rate, dominated by one mechanism:

| Cause | Count |
|---|---|
| `rubric_rule_or_threshold` | 32 |
| `label_ambiguity` | 12 |
| `data_issue` | 10 |
| `extraction_error` | 5 |
| `code_deviation` | 2 |

- **`rubric_rule_or_threshold` (32, the dominant cause):** `skills:
  not_met` fires on **all 12** test listings, in both runs - agreeing
  with the label on only 3 of them (where the label's own skills verdict
  is also `not_met`); on the other 9 the label is `partly` or, for
  `12336-a26f539j0436667-S`, `met`. D-25's cap (correct on the two dev-set
  listings it was built from, where skills genuinely had zero overlap)
  fires on almost every `partial`-labelled test listing too, because the 40 %
  share-of-all-extracted-skills threshold (D-9's start value, unchanged
  since) is strict against Alex's 6-skill profile whenever an ad names
  more than a handful of technologies - which most real ads do (10-60
  skills extracted per listing on this test set). This is the single
  biggest driver of the 33.3 % category accuracy and is **not** an
  extraction-quality problem (`dropped_evidence` is low, and the
  skill names extracted are correct, atomic, and often genuinely include
  2-3 of Alex's 6 profile skills) - it is the threshold itself not
  generalising from the 2-listing dev-set evidence D-25 was decided on.
  No code change was made (test-set findings are not used for tuning).
- **`label_ambiguity` (12):** mostly seniority verdicts following the same
  "implicit context vs. explicit wording" pattern as the dev set, plus
  `15548-1650634-1-S`'s category/seniority (the labelling-time override to
  `excluded` despite a code-visible `location`/`distance` contradiction,
  already documented in WP-13 addendum 3 - expected, not a new finding).
- **`data_issue` (10):** mostly `location_remote` - D-24's documented
  limitation (ad text states "hybrid"/"Homeoffice" but the structured
  fields are empty) recurred on 4 of 12 test listings
  (`12336-a26f539j0436667-S`, `15548-1650634-1-S`, `12117-YF-48852-YF-S`,
  `13635-9c49789f_JB5290290-S`) - more often than the single dev-set
  example suggested, see "Limitations". Plus one genuine BA-data
  contradiction: `10001-1003964383-S`'s title says "befristet bis
  31.01.2028" (fixed-term) but its `contract_duration` field says
  `"UNBEFRISTET"` (permanent) - the structured field itself is wrong, not
  misread.
- **`extraction_error` (5):** language-level nuances (2 listings) and one
  run-to-run seniority miss (`10001-1003893191-S`, run 2) - all minor,
  single-dimension, non-reproducible misses.
- **`code_deviation` (2):** `12336-a26f539j0436667-S`'s `employment_type`
  - `contract_duration: "KEINE_ANGABE"` (not stated) with a known
  `full_time`, the exact gap flagged in the Stage-1 code check above:
  `JobDetails` cannot distinguish "not stated" from "confirmed permanent",
  so the code computes `met` where Ingo's label is `not_met`.

## Limitations

- **One labeller, who also designed the rubric.** Ingo both wrote spec §7
  and produced every hand label; no second, independent labeller's
  judgment was available to check agreement against.
- **Small sample.** 8 development and 12 test listings; the
  `rubric_rule_or_threshold` finding above (D-25's cap not generalising)
  is well-evidenced on this sample but the *right* fix - a different
  threshold, a different skills metric, or something else - cannot be
  picked from 12 listings without risking the same "tuning without a
  number to tune against" problem D-9/D-25 already flagged once.
- **No listing is labelled `strong`.** Across all 20 labelled listings
  (8 dev + 12 test), Ingo's hand label is never `strong` - the `strong`
  category is completely untested by this evaluation, in either
  direction (false positives or false negatives).
- **Location/remote free-text gap (D-24), confirmed more common than the
  single dev-set example suggested.** 4 of 12 test listings disagree on
  `location_remote` because the ad text states remote/hybrid work in
  free text (title or body) while the structured `homeofficetyp`/
  `homeofficeprozent` fields are empty; D-24's decision (Option 1, no code
  change) stands, but this limitation is now measured, not theoretical:
  roughly a third of test listings carry this gap.
- **BA structured-data contradictions.** Two distinct data issues found
  on the test set: a `location`/`distance` contradiction for a
  multi-location posting (`15548-1650634-1-S`, documented in WP-13
  addendum 3) and a `contract_duration` field that contradicts the ad's
  own title (`10001-1003964383-S`, found here). Neither is something the
  rubric can correct without either re-deriving the field from ad text
  (a scope question like D-24's) or treating the BA API's own structured
  fields as potentially wrong, which spec §7 does not currently
  anticipate.
- **The skills-share threshold does not generalise past the 2 dev-set
  listings D-25 was built from.** This is the headline finding of the
  test-set run: `skills: not_met` fires on all 12 test listings, matching
  the label on only 3 of them (D-25's cause table above), making
  `rubric_rule_or_threshold` the dominant disagreement cause and the
  main reason category accuracy
  (33.3 %) is lower on the test set than the post-fix dev set (50.0 %).
  Flagged as an idea for a future iteration, not implemented here (no
  rubric change after the test-set run): the 40 %/70 % skills thresholds
  were set against 5 D-4 spike listings (D-9) and never re-examined
  against a profile with few (6), narrow skills matched against ads that
  routinely name dozens of technologies; a metric less sensitive to the
  *count* of unrelated skills an ad happens to list (e.g. a cap on how
  many extracted skills count toward the denominator, or scoring whether
  *any* profile skill is matched rather than a share) might track Ingo's
  own holistic judgment better than "share of all extracted skills."

## Proposed spec §7 wording

Two changes, for the coach to apply to `PRODUCT_SPEC.md` (CLAUDE.md: Claude
Code does not edit the spec directly). Both are implemented in code
already (D-23, D-25); this section only proposes how §7 should describe
what the code now does.

**1. Scoring paragraph** (after "Any hard exclusion (FR-06) → `excluded`."
and before "If more than two dimensions are `unknown`..."), add one
sentence:

> A `not_met` skills verdict caps the category at `poor`, regardless of
> the weighted share of the other dimensions (D-25).

**2. Location / remote row**, as a new sentence directly under the table
(same place the "Skills:" and "Scoring:" explanatory paragraphs already
sit):

> **Location/remote:** for a `hybrid` remote preference, a listing whose
> remote type is stated but whose remote share is not (e.g. the BA API's
> `homeofficetyp = NACH_VEREINBARUNG`, "by arrangement") counts as remote
> preference satisfied; a `remote` preference still requires a confirmed
> 100 % remote share, since a stated-but-unquantified type does not
> guarantee fully remote work (D-23).
