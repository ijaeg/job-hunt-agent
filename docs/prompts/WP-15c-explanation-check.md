# WP-15c: Consistency check of follow-up explanations

Date: 2026-11-17
Related: D-13, FR-08 AC1, FR-08 AC2, spec §6.3, §9, invariants 2, 4, 5, 6, D-28

## Prompt (verbatim)

WP-15c: Consistency check of follow-up explanations (D-13, FR-08)

Save this prompt verbatim as docs/prompts/WP-15c-explanation-check.md (header: date,
Related line) as the first step. Branch: feature/explanation-check off main. No
commits, pushes, PRs or merges by you - propose each commit and wait for Ingo's
approval.

Read first: CLAUDE.md, docs/decisions/D-13-explanation-consistency.md (binding),
PRODUCT_SPEC.md FR-08, §6.3, §9, invariants 2, 4, 5, 6, docs/decisions/D-28,
prompts/system.md ("Details and fit assessment", "Explaining the shortlist"),
scripts/_agent_run_helpers.py, eval/run_trajectory_eval.py, src/job_hunt_agent/models.py
(FitAssessment, MatchEvidence).

Goal: D-13 option 2 - a deterministic code check that compares follow-up answers with
the stored FitAssessment, run once on a small question set, reported as a metric.

Fixed in advance (do not re-decide):
- No change to the agent, the tools, the middleware or prompts/*.md in this package.
  One measurement run, reported as it is; any prompt fix would be a separate package.
- No tuning, therefore one question set (no dev/test split); state this in the report.
- Demo mode, real model, fresh DB and user ids per invocation (as after D-28), 2 runs
  per thread. Record answers and the stored assessments; no full ad text (invariant 4).

STEP 1 - Question set and check rules (no model call)
1. eval/explanation_set.yaml (approval block left empty): 3 threads. Each thread starts
   with one user message asking how well 3 named listings (by referenznummer) fit, so
   assess_fit runs on known listings. Choose the 9 listings from eval/fit_set.yaml so
   that across the set the stored categories include at least partial, poor and
   excluded, and every listing has at least one match or gap with evidence_de. Verify
   in demo mode without a model call where possible (CLAUDE.md check 4); the
   categories come from the run itself, not from labels.
   Then 4 follow-up turns per thread, neutral wording (no false premises):
   a. why one named listing got its category,
   b. one dimension across the three (e.g. German level or employment type),
   c. which of the user's skills match one named listing and which are missing,
   d. a question about a listing NOT assessed in this thread (from eval/fit_set.yaml).
2. Check rules (pure functions, unit tests on fixed fake data), written into the file:
   C1 Quote fidelity: every quoted passage in an answer ("...", „...", “...”) of 4 or
      more words is a verbatim substring (case- and whitespace-normalised) of one
      evidence_de or evidence_en of the thread's stored assessments. A passage merged
      from two evidence entries fails.
   C2 Match/gap consistency: for the listing a turn is about, a skill name from
      matches appearing in the same sentence as a gap marker, or a skill name from gaps
      in the same sentence as a match marker, is flagged. Fix both marker lists in the
      file now. Every flag is read by you and reported as confirmed or false alarm,
      with the sentence.
   C3 Category consistency: a category word (strong, partial, poor, excluded) stated
      for a listing equals its stored category.
   C4 No new tool call for turns a-c (FR-08 AC1).
   C5 Turn d: passes if assess_fit is called for that listing or the answer says it
      has not been assessed; fails if the answer states a category or fit reasons for
      it without an assessment in state.
- HALT 1: show Ingo the 9 listings, the 12 questions (one line each), the marker lists
  and the five rules. Wait for approval; Ingo approves the commit (prompt file,
  question set, checker, tests) before Step 2.

STEP 2 - One measurement run and report
1. eval/run_explanation_check.py (reuse scripts/_agent_run_helpers.py). Run the 3
   threads, 2 runs each (24 follow-up answers). Write
   eval/results/explanation_check.json.
2. docs/explanation_check.md: per rule the pass rate (run 1 / run 2), every failure
   with the answer sentence and the stored value it contradicts, every C2 flag with
   your confirmed/false-alarm reading, run-to-run spread, limitations (heuristic C2,
   small set, one model). Add a short section to docs/trajectory_evaluation.md that
   links to it as the FR-08 metric next to the §9.2 metrics.
3. Add the command to CLAUDE.md "Commands"; all CLAUDE.md checks with numbers; session
   log entry.
- HALT 2: report, propose the commit. Change nothing after the run.

Possible decisions (stop and ask Ingo, with options and a recommendation):
1. Approval of listings, questions, marker lists and rules (HALT 1).
Stop rule: anything else that would change the agent, a prompt, a tool contract, the
question set after approval or the check rules after approval -> stop and ask first.
If the package turns out much larger than planned, stop at the next clean point and
report.
