Date: 2026-11-16
Related: spec §7, §9.1, §9.3, D-9, D-20, D-21, D-25, D-26, WP-14, WP-14b

# WP-14b: Fit evaluation, second round - new skills metric, fresh test set

Save this prompt as docs/prompts/WP-14b-fit-eval-second-round.md before you start.
Stay on branch feature/fit-evaluation (not pushed yet). No commits, pushes, PRs or
merges by you - propose commit messages, Ingo commits.

Read first: CLAUDE.md, docs/decisions/D-26-fit-eval-second-round.md (the rules and
the method of this round - binding), docs/fit_evaluation.md, eval/fit_set.yaml,
eval/run_fit_eval.py, src/job_hunt_agent/rubric.py, docs/labelling_guide.md,
docs/decisions/D-9, D-20, D-21, D-25, PRODUCT_SPEC.md §7 and §9.

Goal: replace the skills metric "share of all extracted skills the profile covers"
with a metric based on how many of the profile's skills the ad names, and evaluate
it cleanly: fresh test set first, measurement on the development set only (by
re-scoring stored WP-14 extractions), a stop after the development set, one test run.

STEP 0 - State
- Report `git status`. Uncommitted docs/decisions/D-26-fit-eval-second-round.md is
  expected; it goes into the Step 1 commit. Anything else unexpected -> STOP.

STEP 1 - Fix the new test set (no code change yet)
- The 20 listings in eval/fit_set.yaml are now all development listings. Do not
  change eval/fit_set.yaml.
- Draw 10 new test listings from the real fixture listings (FIKTIV-* excluded) that
  are NOT in eval/fit_set.yaml. Rule: same strata definitions as fit_set.yaml;
  1 temp_agency / 6 skill_match / 3 no_skill_match; random.Random(1400) continued
  across strata, shuffle per stratum, take in order; employer cap 2 across all 30
  listings (old 20 + new 10), skipping listings that would exceed it.
  First report the pool size per stratum after the cap; if a stratum cannot fill
  its quota, STOP.
- No app run, no model call, no rubric computation in this step.
- Write rule, seed, pool counts and listing IDs to eval/fit_set_round2.yaml
  (approval block left empty).
- HALT 1: show Ingo the 10 IDs with title and employer only. Nothing about fit.
  Wait for approval; Ingo commits D-26 and the new file before Step 2.

STEP 2 - New skills metric, re-scored on the stored development results
- Refactor rubric.assess: move the category computation (weighted share,
  thresholds, unknown-dimensions cap, D-25 cap, exclusions win) into a pure
  function that takes the five verdicts, the exclusion reasons and low_evidence.
  assess calls it. No behaviour change; all existing tests must stay green.
- Re-score script (no model call): read the 40 stored runs of the 20 development
  listings from eval/results/fit_eval_dev.json and eval/results/fit_eval_test.json
  (WP-14 round 1). Recompute the skills verdict from the stored extracted_skills
  with the existing whole-word matching; keep the other four stored verdicts and
  the stored exclusion_reasons; recompute the category with the new pure function.
- Sanity check first: re-scoring with the CURRENT metric must reproduce every
  stored skills verdict and category exactly (40 of 40). Any mismatch -> STOP and
  report; no new metric before this passes.
- New metric: matched = number of distinct profile skills found among the stored
  extracted skills. skills = unknown if no skill was extracted (D-21 unchanged);
  not_met if matched == 0; partly if 1 <= matched < N; met if matched >= N.
  Weight 2 unchanged.
- Compute four variants: N = 2 and N = 3, each with and without D-25's cap.
  Report per variant: category accuracy run 1 / run 2 (out of 20), skills
  dimension agreement, number of listings whose category differs between the two
  runs, confusion matrix. Compare with D-26 rule 5: >= 12 of 20 correct in BOTH
  runs and <= 2 listings with a different category between the runs.
  Write the results to eval/results/fit_eval_round2_dev.json.
- Do not change the production skills metric yet; no new rubric tests yet.
- Do not open, label or score the new test listings in this step.
- HALT 2: numbers per variant, which variants meet rule 5, your recommendation.
  Ingo decides: continue with one variant, or abort. On abort: revert rubric.py
  to the WP-14 commit state except for nothing - i.e. discard all Step 2 code
  changes, keep only the round-2 dev results file and a short report, and stop.

STEP 3 - Implement the chosen variant and prepare blind labelling
- Implement the chosen variant in rubric.py with tests in tests/test_rubric.py
  (matched 0 / 1 / N-1 / N, duplicates of one profile skill counted once,
  no skills -> unknown, cap behaviour as decided). Full test suite green.
- Make scripts/label_fit.py able to label the listings of eval/fit_set_round2.yaml
  (append rows to eval/fit_labels.csv, same columns). Never show the app's
  category or verdicts.
- HALT 3: Ingo labels the 10 listings and commits the labels.

STEP 4 - One test run
- Make eval/run_fit_eval.py able to run the listings of eval/fit_set_round2.yaml
  with real model calls (2 runs each, as in WP-14). Output:
  eval/results/fit_eval_round2_test.json. Do not overwrite round-1 result files.
- Run once. No code or threshold change after this run, whatever the result.
- docs/fit_evaluation.md: add a section "Second round (D-26)" with the sanity
  check, the four dev variants, the chosen variant, test numbers, confusion
  matrix, every disagreement with cause (same cause classes as round 1),
  limitations. Keep all round-1 numbers and text unchanged.
- Propose the spec §7 wording for the new metric (the coach applies it).
- HALT 4: report and commit proposal.

Possible decisions (stop and ask Ingo, with options and a recommendation):
1. Approval of the test-set rule and the 10 listings (HALT 1).
2. Variant: threshold N (2 or 3) and whether D-25's cap stays (HALT 2).
3. Continue or abort per D-26 rule 5 (HALT 2).
Stop rule: anything not listed here that would change the rubric, the label data,
the set composition or the evaluation method -> stop and ask first. Do not decide
it yourself.
