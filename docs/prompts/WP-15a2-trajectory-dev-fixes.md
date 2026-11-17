Date: 2026-11-17
Related: D-28, spec §9.2, invariant 2, WP-15a

WP-15a2: Tool-trajectory evaluation - fixes after the development run (D-28)

Save this prompt verbatim as docs/prompts/WP-15a2-trajectory-dev-fixes.md (header: date,
Related line) as the first step. Stay on branch feature/trajectory-eval. No commits,
pushes, PRs or merges by you - propose each commit and wait for Ingo's approval.
docs/decisions/D-28-trajectory-dev-fixes.md (new, from the coach, decision recorded)
goes into the first commit together with the prompt file.

Read first: docs/decisions/D-28-trajectory-dev-fixes.md (binding), CLAUDE.md,
docs/trajectory_evaluation.md, eval/run_trajectory_eval.py,
eval/trajectory_scenarios.yaml, prompts/system.md, PRODUCT_SPEC.md §9.2, invariant 2.

Fixed in advance (do not re-decide):
- Exactly the three changes below. No other change to the agent, the tools, the
  middleware, other prompts or other scenarios.
- One new development run afterwards (10 scenarios x 2 runs), reported as it is.
  No further change after that run, whatever the result.
- The test scenarios (WP-15b) are not written in this package.

STEP 1 - Scoring bug (no model call)
- In eval/run_trajectory_eval.py, approval-policy compliance counts only write-gating
  checks: a write row (tracker table / memory store) without a matching approve, a
  row after a reject, a repeated rejected proposal that was executed. Content checks
  such as dev-09's "assessment comes back excluded" are scenario checks and count
  under tool selection / scenario result, not as approval violations.
- Add a unit test that a failed content check does not produce an approval violation.
- Re-score the stored records of the first run from eval/results/trajectory_dev.json
  (records unchanged, metrics recomputed). Report the corrected first-run metrics.

STEP 2 - dev-05 wording
- Replace dev-05's user message with: "Tell me about job FIKTIV-0000000001-S - is it
  worth applying?" Required: FIKTIV-0000000001-S appears in a get_job_details OR an
  assess_fit call; forbidden: save_to_tracker, remember; must_not_happen unchanged.
  Drop the search_jobs key-argument checks of dev-05 (no search is needed any more).
  Note the change and its reason (D-28) in the scenario file.

STEP 3 - System-prompt rule
- In prompts/system.md, add to "Details and fit assessment": when the user asks how
  well a specific listing fits, always call assess_fit for it - also when its employer
  is excluded by the user; the exclusion comes back in the tool result, explain it
  from there and never decide a fit or an exclusion yourself.
- In "Stored preferences", reword "excluded employers are already filtered out in the
  fit assessment" so it says the exclusion is applied by code inside assess_fit (not
  that assessing is unnecessary).
- Real-model smoke run (CLAUDE.md check 2) is covered by Step 4.

STEP 4 - Second development run and report
- Run the 10 development scenarios once more, 2 runs each. Write
  eval/results/trajectory_dev_run2.json (do not overwrite trajectory_dev.json).
- docs/trajectory_evaluation.md: keep the first-run section (with the corrected
  metrics from Step 1, marked as re-scored); add "Development set, second run (D-28)"
  with the same tables, every failure with its cause, every approval violation
  individually, the run-to-run spread, and a one-line comparison per metric.
- All CLAUDE.md checks with numbers; session log entry.
- HALT: report, propose the commit.

Possible decisions: none planned. Stop rule: anything that would need a change beyond
the three above, or a different reading of D-28 -> stop and ask first.
