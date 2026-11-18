Date: 2026-11-18
Related: spec §3.2, §9.5, FR-03 AC1/AC3, NFR-03, D-10, D-12, D-18

---

WP-16b: Demo reliability check, fresh LangSmith traces, screenshots in the README

Save this prompt verbatim as docs/prompts/WP-16b-traces-screenshots-demo.md (header:
date, Related line) as the first step. Branch: feature/traces-screenshots off main. No
commits, pushes, PRs or merges by you - propose each commit and wait for Ingo's approval.

Read first: CLAUDE.md, README.md (placeholders "added in WP-16b", "Usage: demo script"),
PRODUCT_SPEC.md §3.2, §9.5, D-10, D-12, D-18, docs/langsmith.md,
scripts/run_langsmith_traces.py, scripts/ui_smoke_wp04.py, docs/trajectory_evaluation.md.

Fixed in advance (do not re-decide):
- No change to the agent, the tools, the middleware or prompts/*.md. The evaluated
  version is the submitted version. The wording check below chooses how S1 is demoed;
  it does not tune the agent. Its result is reported as it is.
- Demo mode, real model (config defaults), user "alex" (D-18), fresh thread per run.
- Do not change the visibility of any LangSmith run (no share_run) without Ingo's
  decision.

STEP 1 - S1 wording check (demo mode)
1. Run each of these three S1 wordings 5 times on fresh threads:
   W1 "Find Softwareentwickler jobs in München."  (D-12's wording)
   W2 "Find Softwareentwickler jobs in München, posted in the last 4 weeks."
   W3 "Find Softwareentwickler jobs in München from the last 4 weeks, no temp agencies."
   Per run record: number of search_jobs calls, whether the agent narrowed after the
   103-result search, number of listings assessed, whether a shortlist was shown,
   elapsed time. Reuse scripts/ui_smoke_wp04.py's or the trajectory runner's logic.
   Write eval/results/s1_wording_wp16b.json. Report per wording: complete runs
   (refined AND at least one listing assessed) out of 5, median and max elapsed time.

STEP 2 - Fresh traces
1. Extend scripts/run_langsmith_traces.py (or add a successor; keep the WP-10 result
   file untouched) to record, in demo mode with tracing on, one thread S1 -> S2 -> S3
   (approve) -> S4 (reject), using the S1 wording with the most complete runs in Step 1
   (on a tie: the shorter wording), plus S5 and S6 on their own threads, with the
   README's S2-S6 wording. If S1 does not refine in the recorded run, record it once
   more and report both. Write eval/results/langsmith_wp16b.json (project, run ids,
   thread ids, whether S1 refined).
- HALT 1: report Step 1's table and Step 2's run ids. Ingo decides (1) the S1 wording
  for the demo and the README, (2) whether the six traces get public share links or
  are shown as screenshots in the README. Then Ingo does a demo rehearsal and takes the
  screenshots himself; wait until he provides the image files.

STEP 3 - README update (after Ingo has provided the images)
1. Put the images into docs/images/ with descriptive names; replace every "added in
   WP-16b" placeholder in README.md with the image (or the share link, if decided).
   Check each image shows no API key, no e-mail and no real person's data.
2. Update the README's S1 row to the chosen wording and add one sentence with Step 1's
   result for that wording (e.g. "complete in N of 5 runs"). Update docs/langsmith.md
   to point to the new run ids.
3. Check every README link and image path resolves; all CLAUDE.md checks; session log.
- HALT 2: report, propose the commit.

Possible decisions (stop and ask Ingo):
1. S1 wording for the demo; public share links or screenshots for the traces (HALT 1).
Stop rule: anything that would change the agent, a prompt, a tool contract or an
evaluation result file -> stop and ask first.

---

## Addendum 1 (2026-11-18, HALT 1 decisions, recorded by the coach)

Step 1 result (`eval/results/s1_wording_wp16b.json`): all three wordings completed
5 of 5 runs; maximum elapsed time W1 64.4 s, W2 61.5 s, W3 54.6 s - only W3 stayed
within NFR-03's 60 s in every run.

Decisions (Ingo, following the coach):

1. **S1 wording for the demo and the README: W3** ("Find Softwareentwickler jobs in
   München from the last 4 weeks, no temp agencies."). The thread S1 -> S2 -> S3
   (approve) -> S4 (reject) is recorded once more with W3, so trace, README and live
   demo match; S5 and S6 keep their WP-16b recordings. The README's known limitation
   "3 of 6 runs" stays; the README adds this check's result next to it.
2. **Traces: public share links for all eight traces, plus one screenshot of the S1
   trace tree** as a permanent fallback (base retention is 14 days, so the links expire
   around 2026-12-02; they can be renewed by re-running the recording script).
   Ingo approves `share_run` for these eight runs.

## Addendum 2 (2026-11-18, coach review of the screenshots, recorded by the coach)

Decisions (Ingo, following the coach):

1. The "Agent steps" arguments show the umlaut in "München" as a JSON unicode escape
   (backslash, u00fc) instead of the letter itself (`steps_view.py` dumps the arguments
   as ASCII-escaped JSON). Fix it in the display
   only (`ensure_ascii=False`), with a test, and re-take `agent-steps.png`. No change to
   the agent, the tools or any evaluation result.
2. The README gets one line under the demo table with the public links of all eight
   traces and a link to `docs/langsmith.md` (added by the coach).
3. The shortlist screenshot keeps answer item 3 ("Matches: Java" and "Gaps: focuses on
   Java, ...") as it is: a visible example of the free-text explanation limitation
   (D-13), documented in the README.
