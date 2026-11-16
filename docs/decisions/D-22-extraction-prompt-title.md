# D-22: Extraction prompt never sees the listing title

Related: spec §6.2, §7 "Seniority", FR-05 AC1, WP-14

## Question

`tools/assess.py`'s extraction call (`_extract_one`) passes only
`details.description` (the ad body) to the model, never the listing
title. Should the title be added to the extraction prompt?

## Context

In the dev-set run, `19913-3074751792188001-S` (NTT DATA, title "Senior
AI Engineer (w/m/x)") got `seniority: not_mentioned` from the model in
both runs, against Ingo's label `met`. Reading the ad body confirms why:
the word "senior" occurs in the body only as part of "Seniorität" (a
different word) and inside a URL slug
(".../senior-ai-engineer-w-strich-m-strich-x") - never as a standalone
seniority statement. The only place the ad actually states the level is
the **title**, which `_extract_one` never sends to the model.

Two other dev listings whose titles also start with "Senior" -
`12336-a26f1128j0452080-S` (TÜV SÜD) and `13635-d780e451_JB5286154-S`
(DYMATRIX) - got the correct `seniority: met` in both cases, but only
because *their* ad bodies happen to restate "Senior" in the opening
sentence ("**Senior Softwareentwickler** für...", "...suchen wir Dich als
**Senior AI Data Engineer**..."). The extraction is not reading the
title in any of the three cases; it only looks correct for two of them
because the body happens to repeat it.

This is a narrow, single-dimension finding (no other dev disagreement
traces to this cause) but it is a real, structural gap: a title-only
seniority (or other) statement is invisible to `assess_fit` by
construction, not because the model failed to notice it.

## Options

1. **No change.** The title is visible elsewhere (the shortlist card,
   FR-07 AC1) even if the extraction misses it; a human reviewing the
   card still sees "Senior" in the title. Leaves this one failure mode
   unaddressed for the rubric's own seniority verdict.
2. **Pass the title alongside the ad body** in the extraction prompt
   (`prompts/extract_requirements.md` gets a `{title}` placeholder;
   `_extract_one`'s caller passes `details.title`). Minimal change -
   one more prompt placeholder, one more argument - and directly fixes
   the demonstrated failure mode. Verbatim-evidence quotes
   (`evidence_de`) must still come from the ad **body** only (FR-05 AC2
   checks `evidence_de` against `ad_text`, which would need to stay the
   description, not description+title, so a title-sourced seniority
   claim can legitimately carry no quoted evidence - already allowed,
   `seniority_evidence` is `str | None`).

## Recommendation

Option 2. Low-risk, narrowly scoped, and the dev-set evidence shows the
exact mechanism (title-only seniority, confirmed by checking the raw ad
text for all three "Senior ..." dev titles) rather than a guess.

## Consequences

- `src/job_hunt_agent/tools/assess.py`: `_extract_one` gains a `title`
  parameter (or reads it from a `JobDetails`/`JobSummary` passed in);
  the one call site in `assess_fit` passes `details.title`.
- `prompts/extract_requirements.md`: add a `title: {title}` line above
  the ad text, with a note that only the ad text block counts for
  verbatim evidence.
- `eval/run_fit_eval.py`'s `run_listing` passes the title the same way,
  so the eval script and the tool stay on the same code path.
- Tests: `tests/test_tools_assess.py` gets a case asserting the title is
  included in the formatted prompt.
- Dev listing this would likely change: `19913-3074751792188001-S`
  (seniority `not_mentioned` -> `senior`, dimension `unknown` -> `met`) -
  must be re-measured, not assumed; a title-level seniority claim could
  in principle also affect other listings not yet in the dev sample.
- No change to weights, thresholds or the rubric's own logic.

**Decision:** Option 2 (2026-11-16, Ingo). The title is passed to the extraction prompt; verbatim evidence still comes from the ad text only.
