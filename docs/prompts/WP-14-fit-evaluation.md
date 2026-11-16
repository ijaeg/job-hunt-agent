Date: 2026-11-16
Related: spec §7, §9.1, §9.3, FR-05 AC2, FR-06, NFR-09, invariant 6, D-9, D-20

# WP-14: Fit evaluation (spec §9.3)

Related: spec §7, §9.1, §9.3, FR-05 AC2, FR-06, NFR-09, invariant 6, D-9, D-20

## Step 0
Save this prompt verbatim as docs/prompts/WP-14-fit-evaluation.md. We are on branch feature/fit-evaluation.

## Method (do not change)
Two stages, because the test set is never used for tuning (spec §9.1, invariant 6):
- Stage 1 runs the 8 dev listings only, analyses every disagreement, then stops for Ingo's decisions.
- Stage 2 runs the 12 test listings once, after Ingo's decisions are implemented. Nothing is tuned after Stage 2; findings from the test set go into the report as limitations or ideas.

## Stop rules
1. Planned stop after Stage 1 (see below).
2. Any change to a rubric rule, threshold, weight or tool contract needs a decision file and Ingo's answer first (CLAUDE.md).

## Script
eval/run_fit_eval.py (spec §11). For each listing of eval/fit_set.yaml:
- Build exactly the inputs the labelling tool showed (WP-13 addendum 2): the JobSummary with the fixture's distance_km and the search location from scripts/label_fit.py's resolve_search_location, JobDetails from FixtureSource, profile data/samples/profile_alex.yaml.
- Run the same extraction and rubric code path as tools/assess.py (reuse its functions, no copy), real model, settings from config.py.
- Record per listing and run: app category, the five dimension verdicts, exclusion reasons, extracted requirements with evidence, dropped_evidence count, low_evidence, model and settings (NFR-09).
- Each listing runs twice; report both runs and whether they agree.
- Compare with eval/fit_labels.csv: overall category and each dimension.

## Stage 1: dev set (8 listings)
1. Code check against spec §7, independent of any label: does rubric.py read every structured field §7 names, in particular befristungInMonaten / contract_duration ("BEFRISTET") for the employment type, and how does it treat a stated remote type without a percentage ("NACH_VEREINBARUNG") for location/remote? Report what the code does and where it deviates from §7 or where §7 is silent.
2. Run the dev set. For every disagreement (category or dimension), classify the cause: extraction error (model extracted wrong or missed something; quote the ad), rubric rule or threshold (the code applied §7 as written, but the result differs from the label), code deviation from §7, data issue (fixture fields contradict each other or the ad, see the notes in eval/fit_labels.csv), label ambiguity.
3. Write eval/results/fit_eval_dev.json and a short summary in docs/fit_evaluation.md (section "Development set").
4. For every proposed change (code fix, rule clarification, threshold), write one decision file docs/decisions/D-21-....md (number further files D-22, ...): question, evidence from the dev set only, options, recommendation, which test cases would change. Then STOP and report. Do not run the test set.

## Stage 2: test set (12 listings) - only after Ingo's answer is recorded
1. Implement the decided changes with tests; re-run the dev set and record the new dev numbers.
2. Run the test set once (two runs per listing). Report: category accuracy, 4x4 confusion matrix (strong/partial/poor/excluded), agreement per dimension, run-to-run agreement, every disagreement with its cause class, total dropped_evidence.
3. eval/results/fit_eval_test.json; docs/fit_evaluation.md section "Test set" and "Limitations": one labeller who also designed the rubric; small sample; no listing labelled "strong" by Ingo, so the strong class is untested; location-field/distance contradictions in the BA data (multi-location postings).
4. No change to rubric, prompts or code after this run.

## Tests (NFR-05)
Unit tests for the comparison logic (agreement, confusion matrix, cause classification input/output) with fixed fake results; no test reaches OpenRouter (invariant 5).

## Done when
- All checks of CLAUDE.md "Checks before hand-over" pass, with numbers.
- docs/session_log.md has an entry; the report states the test accuracy and the confusion matrix explicitly.

## Commits
Propose small commits and wait for Ingo's approval each time. Suggested split: prompt; script + comparison tests; dev results + decision files (Stage 1); decided changes + tests; test results + docs/fit_evaluation.md + session log.
