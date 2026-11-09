# D-12: S1 latency against the NFR-03 budget of 60 s

Related: NFR-03, FR-05 AC1, FR-16 AC2, R-4, D-4, D-10

## Question

Scenario S1 in demo mode must complete within 60 s (NFR-03). Is the budget
met, and if not, which lever should change?

## Context

Three runs of the demo variant of S1 ("Find Softwareentwickler jobs in
München.", the recorded 103-result search, D-10) with `openai/gpt-5-mini`,
reasoning effort `low`, 4 concurrent extractions:

| Run | Elapsed | Source |
|---|---|---|
| D-10 follow-up 3 | 56.2 s | `eval/results/d10_followup3_verification.json` |
| WP-04 smoke, first run | 56.4 s | superseded (tool calls were counted twice; elapsed time itself unaffected) |
| WP-04 smoke, corrected | 65.8 s | `eval/results/ui_smoke_wp04.json` |

The runs differ in tool sequence (run-to-run model variance), and three runs
are too few to say whether the budget is met reliably. Spike D-4 measured
15.8 s per extraction on average, so `assess_fit` dominates (risk R-4).

## Options

1. **Measure first, then decide.** Run S1 in demo mode 5 times on the final
   code, record per run: elapsed time, tool sequence, `assess_fit`
   extraction time, number of listings assessed. Report median and maximum.
   Decide on a lever only with these numbers.
2. **Change a lever now** (lower reasoning effort for the extraction only,
   fewer listings per `assess_fit` call, smaller extraction schema) without
   further measurement.
3. **Accept the overage** and document it as a known limitation.

## Recommendation

Option 1. One run over budget out of three is not enough to justify a change
to the extraction, which would also affect the fit evaluation (§9.3).

## Consequences

- WP-05 adds the 5-run measurement (`scripts/ui_smoke_wp04.py` or a
  successor) and writes the results to `eval/results/`.
- If the median or the maximum is above 60 s, this file gets a second round
  of options with the measured numbers, and Ingo decides on a lever.
- No change to `config.py`, `tools/assess.py` or the prompts in this step.

**Decision:** Option 1 (2026-11-09, Ingo). Measure 5 runs in WP-05, then decide on a lever with the numbers.

## Results (WP-05, 2026-11-09)

**First measurement** (5 runs, demo mode, real model, fresh thread each,
`scripts/ui_smoke_wp04.py --runs 5`): all 5 runs median 52.75 s, max 59.63 s
- inside the 60 s budget, but only 3 of 5 ran the full pipeline to
`assess_fit` (6 listings each); the other 2 stopped after `search_jobs`
alone (0 listings assessed, ~8 s) because the model asked for location
clarification instead of searching ("Find ... jobs in München" vs. the
profile's `location: Hamburg`) - the same behaviour seen in the WP-05
S1/S2 check (FR-01 AC4 was already written to allow this: "the request may
override [the profile] for this search", but `prompts/system.md` did not
say so explicitly). On the 3 completed runs only: median 55.48 s, max
59.63 s (0.37 s under budget) - a thinner sample and thinner margin than a
clean "budget met" reading suggested; flagged in Addendum 1 to this work
package rather than acted on unilaterally.

**Fix (Addendum 1 #1):** added an explicit rule to `prompts/system.md`'s
"Search and refinement" section - a location named in the request
overrides the profile's stored location for this search; do not ask.

**Re-measured after the fix** (same script, same config, 5 fresh threads,
`eval/results/latency_s1_wp05.json`, full per-run detail in
`spikes/NOTES.md` "WP-05 S1 latency measurement, re-measured"):

- **Completion rate: 5/5 (100%)** - every run reached `assess_fit`, none
  stopped to ask about the location.
- **Refinement rate: 5/5 (100%)** - every run made more than one
  `search_jobs` call (FR-03 AC3), confirmed working as before.
- **Elapsed seconds: median 44.77 s, mean 47.16 s, min 36.19 s, max
  58.44 s** - all 5 runs now measure the thing NFR-03 is actually about,
  median and maximum both inside the 60 s budget with a real (if still not
  large) margin on the worst run (1.56 s).

Neither reading crosses the median/maximum-above-60s trigger, so no
"Round 2 options" section was added and nothing in `config.py`/
`tools/assess.py`/the extraction prompt was tuned, per this file's
Recommendation. **Budget met: yes**, on a clean 5/5-completion sample this
time.
