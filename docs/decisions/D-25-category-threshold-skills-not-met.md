# D-25: the 45 % "partial" threshold scores a clear skill mismatch as `partial`, not `poor`

Related: spec §7 "Scoring", D-9, WP-14

## Question

Two dev listings get all five rubric dimension verdicts right (identical
to Ingo's per-dimension label) but still disagree on the **overall
category** - the app says `partial`, Ingo says `poor` - both times
because `skills: not_met` (weight 2, the heaviest dimension) is outvoted
by three dimensions that happen to be `met`/`partly`. Should `not_met`
on the skills dimension cap the category, the way "too many unknown
dimensions" already caps it at `partial` (spec §7, last sentence)?

## Context

This is the cleanest kind of disagreement in the dev set: dimension
verdicts match exactly, so the cause is isolated to the category-level
math, with zero extraction noise involved.

`12336-a26f1128j0452080-S` (TÜV SÜD, .NET/Blazor role) and
`13635-d780e451_JB5286154-S` (DYMATRIX, AI/marketing data engineering
role) both land on:

| dimension | verdict | weight | points |
|---|---|---|---|
| skills | not_met | 2 | 0 |
| location_remote | partly | 1 | 1 |
| seniority | met | 1 | 2 |
| language | unknown (excluded) | 1 | - |
| employment_type | met | 1 | 2 |

`share = (0 + 1 + 2 + 2) / ((2+1+1+1) * 2) = 5 / 10 = 0.50`, which is
`>= PARTIAL_THRESHOLD (0.45)` -> `partial`. Both listings are labelled
`poor` by Ingo, with exactly this reasoning available from the ad text:
Alex's profile skills (Python, Java, FastAPI, PostgreSQL, Docker,
CI/CD) have essentially no overlap with .NET MAUI/Blazor/C# (TÜV SÜD) or
with AI-driven marketing/data-platform engineering (DYMATRIX) - a 0 %
skill match is, in Ingo's judgment, disqualifying on its own regardless
of seniority/contract fit, not merely half-weight evidence to be
averaged away by three other passing dimensions.

The pattern is exactly reproducible (both runs, both listings, identical
numbers both times) - this is the rubric's weighted-average formula
interacting with its own 2x weight on skills, not a one-off.

## Options

1. **No change.** Keep the 45 %/75 % thresholds and the plain weighted
   average as shipped (D-9's start values). Simplest; leaves this
   reproducible 2-listing pattern as a standing disagreement.
2. **Raise `PARTIAL_THRESHOLD`** above 0.50 (e.g. to 0.55 or 0.60) so
   this specific share no longer clears it. Simple, one-constant change,
   but a blunt instrument: it also moves every other listing sitting in
   the 45-54 % band, not just this skills-not_met pattern, and the dev
   set has too few listings in that band to say what else would move.
3. **Add a hard cap, symmetric to the existing "too many unknowns caps
   at partial" rule**: `skills: not_met` caps the category at `poor`
   regardless of score (mirrors spec §7's last sentence's own pattern -
   a specific dimension outcome overriding the weighted average, not a
   threshold number). Targets exactly the demonstrated failure mode
   without touching the thresholds that the other 6 dev listings'
   correct categories depend on.
4. **Increase the skills weight further** (e.g. 2 -> 3) instead of
   capping. Keeps the "it's still just a weighted average" model, but a
   quick hand-check shows weight 3 still gives `share = (0+1+2+2)/((3+1+1+1)*2)
   = 5/12 = 0.417`, which drops *below* even the 0.45 partial threshold
   (-> `poor`, fixing these two) - plausible, but changes every other
   listing's score too and needs the same re-check Option 2 needs.

## Recommendation

Option 3. It is the most targeted fix for the evidence actually in hand
(two listings, identical mechanism, zero skill overlap) and does not
risk moving any of the other six dev listings whose categories already
match the label. Options 2 and 4 are not ruled out, but neither has
dev-set evidence for *which* new threshold/weight value is right -
picking one now would be tuning without a number to tune against, which
spec §9.3/CLAUDE.md's "tuned on development listings only, with
documented values" asks to avoid.

## Consequences

- `src/job_hunt_agent/rubric.py`: `assess` gains a cap rule - if
  `rubric["skills"] == "not_met"`, `category` is capped at `poor`
  (downgrading `partial`/`strong` the same way the unknown-dimensions
  cap already downgrades `strong` to `partial`). Needs to compose
  correctly with the existing unknown-dimensions cap and with hard
  exclusions (exclusions still win over everything, per FR-06 AC4).
- `tests/test_rubric.py`: new case asserting a high weighted share with
  `skills: not_met` still comes out `poor`, plus a case confirming
  `skills: partly`/`met` is unaffected by the new rule.
- Dev listings this would change: `12336-a26f1128j0452080-S` and
  `13635-d780e451_JB5286154-S` (`partial` -> `poor`, matching the label
  in both runs each).
- No change to `PARTIAL_THRESHOLD`/`STRONG_THRESHOLD` or any weight;
  `PRODUCT_SPEC.md` §7's last sentence would need one more sentence
  describing the new cap, proposed back to Ingo rather than edited
  directly (CLAUDE.md).

**Decision:**
