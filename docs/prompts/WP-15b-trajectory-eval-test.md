Date: 2026-11-17
Related: spec §3.2 (S1-S6), §9.1, §9.2, invariant 2, invariant 3, invariant 6, D-28,
WP-15a, WP-15a2, WP-15b

WP-15b: Tool-trajectory evaluation - test scenarios and one test run

Save this prompt verbatim as docs/prompts/WP-15b-trajectory-eval-test.md (header: date,
Related line) as the first step. Branch: feature/trajectory-eval-test off main. No
commits, pushes, PRs or merges by you - propose each commit and wait for Ingo's approval.

Read first: CLAUDE.md, PRODUCT_SPEC.md §3.2 (S1-S6), §9.1, §9.2, invariants 2, 3, 6,
docs/decisions/D-28-trajectory-dev-fixes.md, docs/trajectory_evaluation.md,
eval/trajectory_scenarios.yaml, eval/run_trajectory_eval.py.

Fixed in advance (do not re-decide):
- Spec §9.1: the 10 test scenarios are written now, after tuning, and are never used
  for tuning. No change to the agent, the tools, the middleware or prompts/*.md in
  this package.
- Exactly one test run: 10 test scenarios x 2 runs, real model, demo mode, fresh DB
  and user ids per invocation (as after D-28). Reported as it is; no change of any
  kind after the run. An approval-policy violation is listed first; fixing it would
  be a separate package.
- eval/trajectory_scenarios.yaml (dev, approved) stays unchanged.

STEP 1 - Test scenarios, checks, dry validation (no model call)
1. Write eval/trajectory_scenarios_test.yaml (set: test, own approval block left
   empty, own data_check field), same schema and metric rules as the dev file.
   10 scenarios covering the same behaviours as the dev set, but not paraphrases of
   the dev messages and, where the fixture data allows, with other listings and
   employers. Include the spec's own shapes that the dev set did not use: S2 as
   "Why is #N only partial?" after a search with assessment, and S3 as "Save #N and
   remind me in a week" referring to the shortlist (not a reference number).
   Refinement scenarios must lead to the only search that exceeds 50 in demo mode
   (Softwareentwickler / München / 25 km / 28 days, D-10) - verify, do not assume.
   No dates that can expire (relative dates only).
2. Data check per scenario against FixtureSource (CLAUDE.md check 4), recorded in
   data_check. If a scenario cannot be produced by the data, replace it and say so.
3. Add the scenario-specific DB/state check functions for the test ids to
   eval/run_trajectory_eval.py, each registered as write-gating or content check
   (D-28 split). Make --set test read eval/trajectory_scenarios_test.yaml; --set dev
   must behave exactly as before.
4. Dry validation, no model call: load the test file, confirm every order_constraint
   and key_argument rule is recognised by the scorer (no "unrecognised ... treated as
   failed"), every referenznummer exists, every test id has its checks registered.
   Unit tests for the new check functions on fixed fake data (invariant 5).
- HALT 1: show Ingo the 10 test scenarios (one line each: id, user message(s),
  expected tools, approval), the new checks (one line each) and the dry-validation
  result. Wait for approval; Ingo approves the commit (prompt file, test scenario
  file, checks, tests) before Step 2.

STEP 2 - One test run and report
1. Run --set test once (10 scenarios x 2 runs). Write eval/results/trajectory_test.json.
2. docs/trajectory_evaluation.md: add "Test set" with the same tables as the dev
   sections (every metric run 1 / run 2, per-scenario table, every failure with its
   cause, every approval violation individually, run-to-run spread) and a short
   dev-vs-test comparison. Keep all dev sections unchanged.
3. All CLAUDE.md checks with numbers; session log entry.
- HALT 2: report, propose the commit. Change nothing after the run.

Possible decisions (stop and ask Ingo, with options and a recommendation):
1. Approval of the 10 test scenarios and their checks (HALT 1).
Stop rule: anything else that would change the agent, a prompt, a tool contract, the
dev scenarios, the scenario content after approval or the evaluation method -> stop
and ask first. If the package turns out much larger than planned, stop at the next
clean point and report.
