# D-26: second fit-evaluation round with a new skills metric and a fresh test set

Related: spec §7, §9.1, §9.3, invariant 6, D-9, D-20, D-25, WP-14, docs/fit_evaluation.md

## Question

WP-14's single test run (12 listings, 2 runs each) gave 33.3 % category
accuracy. The dominant cause is the skills metric, not extraction: the
share of *all* technologies an ad names that the profile covers is almost
always below 40 % for Alex's 6-skill profile, because real ads name 10-60
technologies. `skills: not_met` fired on all 12 test listings, and D-25's
cap then turned every `partial`-labelled listing into `poor` (7 of 7).
Leave this as a documented result, or run a second, clean round?

## Options

- **A. Leave as is.** Report 33.3 %, the cause analysis and the idea for a
  better metric as a limitation. No further work.
- **B. Second round with a stop after the development set.** The 20
  labelled listings become the development set. A fresh test set is fixed
  *before* any code change. The new skills metric is built and measured on
  the 20 development listings only. Ingo labels the new test listings only
  if the development result clears a criterion fixed in advance; then one
  test run, reported whatever its outcome. Otherwise back to Option A.

## Rules fixed in advance (so the round stays clean)

1. **Test set first.** A new test set of 10 listings is drawn from the
   fixture listings not yet in `eval/fit_set.yaml`, by a written rule with
   a fixed seed, approved by Ingo and committed **before** any change to
   `rubric.py`. No app run, no model call, no rubric computation while
   drawing it.
2. **Blind labelling.** Ingo labels the new listings with
   `scripts/label_fit.py` without ever seeing the app's category or
   verdicts (D-20).
3. **Tuning on the development set only.** The new metric and its
   thresholds are chosen using the 20 development listings only.
4. **One test run, no change afterwards.** The result is reported as it
   is. WP-14's 33.3 % stays in `docs/fit_evaluation.md` as the first-round
   result; it is not overwritten.
5. **Stop criterion after the development set, fixed now:** the second
   round continues to labelling and the test run only if, on the 20
   development listings, category accuracy is **at least 60 % in both
   runs** (baseline with the current code: 8 of 20 = 40 %, WP-14 dev and
   test combined) **and** category run-to-run agreement does not fall
   below 90 %. Otherwise the code returns to the WP-14 state and
   Option A applies.

## Consequences

- New file for the second-round test set (rule, seed, approval), next to
  `eval/fit_set.yaml`; new label rows from Ingo for those 10 listings.
- `src/job_hunt_agent/rubric.py`: new skills metric based on how many
  profile skills the ad names, instead of the share of all extracted
  skills; D-25's cap re-checked against the new metric (an Ingo decision
  in the round's prompt).
- `docs/fit_evaluation.md`: new "Second round" section; first-round
  numbers kept.
- Spec §7 wording and §14 entries updated by the coach after the round.
- Extra effort for Ingo: about 1 hour of labelling, only if the stop
  criterion is met.

**Decision:** Option B (2026-11-16, Ingo), with the stop after the
development set. Rule 5's numbers (>= 12 of 20 correct categories in both
runs, <= 2 listings with a different category between the runs) proposed
by the coach, confirmed by Ingo (2026-11-16). Ingo: the extra effort
should also bring extra value - if the development set does not show a
clear improvement, the round stops there.

**Method for the development measurement** (2026-11-16, Ingo, following
the coach's recommendation): the new skills metric is re-scored on the
stored WP-14 extraction results of the 20 development listings (both
runs each, `eval/results/fit_eval_dev.json` and `fit_eval_test.json`),
without new model calls - so the only change between old and new numbers
is the metric itself. The fresh test set is run with real model calls,
as in WP-14.
