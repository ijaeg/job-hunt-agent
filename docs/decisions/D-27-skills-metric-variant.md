# D-27: which skills-metric variant, and does D-25's cap stay

Related: spec §7, §9.1, §9.3, D-9, D-20, D-21, D-25, D-26, WP-14, WP-14b

## Question

D-26 asks for a new skills metric - "matched = number of distinct profile
skills found among the extracted skills; `not_met` if `matched == 0`,
`partly` if `1 <= matched < N`, `met` if `matched >= N`" - measured on the
20 development listings only, by re-scoring the stored WP-14 round-1
extractions (no new model calls). Two open parameters: the threshold `N`
(2 or 3) and whether D-25's "`skills: not_met` caps the category at `poor`"
rule stays. Which variant, if any, clears D-26's rule 5 stop criterion
(>= 12/20 correct category in both runs, <= 2 listings differing between
runs) well enough to continue to blind labelling and the test run?

## Context

`eval/rescore_fit_round2.py` re-scored all 40 stored runs (8 dev + 12 test
listings from WP-14 round 1, now all "development" per D-26 step 1; 2 runs
each). A sanity check first confirmed the re-scoring harness reproduces
every one of the 40 stored skills verdicts and categories exactly under the
**current** (shipped) metric - 40/40, no code or data issue in the harness
itself. Only then were the four new-metric variants computed.

### Results (`eval/results/fit_eval_round2_dev.json`)

| Variant | Category correct, run 1 | Category correct, run 2 | Skills dim. agreement (run1/run2) | Categories differing between runs | Meets rule 5? |
|---|---|---|---|---|---|
| N=2, with cap | 10/20 (50.0%) | 10/20 (50.0%) | 60.0% / 55.0% | 0 | No (< 12/20) |
| N=2, no cap | 8/20 (40.0%) | 8/20 (40.0%) | 60.0% / 55.0% | 0 | No (< 12/20) |
| N=3, with cap | 14/20 (70.0%) | 15/20 (75.0%) | 75.0% / 70.0% | 1 | **Yes** |
| N=3, no cap | 12/20 (60.0%) | 13/20 (65.0%) | 75.0% / 70.0% | 1 | Yes (run 1 exactly at the 12/20 floor) |

Removing D-25's cap never helps and sometimes hurts: for both N values, the
"no cap" column is strictly worse than "with cap" on category accuracy
(10->8 at N=2, 14->12 and 15->13 at N=3), because the cap's job - catching
a clear 0-skill mismatch that the weighted average alone would read too
generously - is unaffected by which skills metric feeds it. Dropping the
cap only removes a mechanism that was already working.

**N=2 is too lenient.** Matching only 2 of Alex's 6 profile skills now
scores `skills: met` (full weight-2 credit). Across the 20 listings this
produces `skills: met` or `partly` almost everywhere a label says `partial`
and the ad happens to name any 1-2 overlapping technologies, which is most
real ads. Round 1's current metric scored 33.3% on its 12-listing test set
and, applied to all 20 now-development listings, 40% (8/20) - N=2 with cap
reaches 50% (10/20), an improvement over round 1, but still short of rule
5's 12/20 floor; N=2 without cap (8/20, 40%) does not even clear round 1's
own 20-listing number.

**N=3, with cap, is the strongest variant** (14/20, 15/20) but is not
without a new, specific failure mode: it produces `category: strong` on 3
listings in run 1 and 2 in run 2, all three labelled `partial` by Ingo -
but only one of them is actually driven by the new skills metric:

| Referenznummer | Skills verdict (N=3) | Matched profile skills | Label | App (N=3, cap) |
|---|---|---|---|---|
| 19913-3074751792188001-S | met (3 >= N) | Docker, FastAPI, Python | partial | strong (both runs) |
| 19913-3056331792188001-S | partly (1 < N) | Python | partial | strong (both runs) |
| 10001-1003893191-S | partly (2 < N) | CI/CD, Python | partial | strong (run 1 only) |

Only **19913-3074751792188001-S** reaches `strong` through the new metric:
matching 3 of Alex's 6 skills (Python, FastAPI, Docker) scores
`skills: met` (`matched >= N=3`) under the new metric's own logic, pushing
the weighted share over `STRONG_THRESHOLD` - a genuinely strong skills
overlap by this metric's definition, but Ingo's hand label still reads the
listing as `partial` overall. This is a new disagreement shape the old
metric's "share of all extracted skills" never produced (it could not
reach `met` on a 34-skill ad with only 3 matches).

The other two reach `strong` **without** the skills metric's help -
`19913-3056331792188001-S` and `10001-1003893191-S` both score
`skills: partly` (1 and 2 matched skills, below N=3), not `met`, so D-25's
cap does not fire (it only catches `not_met`) and the other four
dimensions, all `met`/`partly`, carry the weighted share over
`STRONG_THRESHOLD` on their own - the same "high score on everything but
skills" shape D-25 was built to catch at the opposite end (`not_met`), now
showing up at the `partly` end instead, independent of which skills metric
is in use. `10001-1003893191-S`'s run-to-run difference (the single "1" in
the table above) reproduces a known instability already documented for
this exact listing in `docs/fit_evaluation.md` (its seniority verdict
flips `met`/`partly` between runs, WP-14 round 1) - not a new problem from
this metric.

## Options

1. **N=3, with cap.** Clears rule 5 with the most margin (14/20, 15/20,
   diff 1). Known cost: 2-3 false `strong` categorizations on listings
   Ingo would call `partial`. Only one of them is actually driven by the
   new metric (3 of 6 profile skills matched, scored `met`); the other two
   score `skills: partly` and reach `strong` because the other four
   dimensions alone carry the weighted share over threshold - a pre-existing
   shape at the `partly` end that D-25's cap (built for `not_met`) does not
   catch, not something this metric change introduced.
2. **N=3, no cap.** Clears rule 5 only barely (run 1 sits exactly at the
   12/20 floor) and is strictly worse than Option 1 on every number measured
   (2 fewer correct in run 1, 2 fewer in run 2, same skills agreement, same
   run-to-run diff) - the cap was never the problem. No reason to prefer
   this over Option 1.
3. **Abort** (D-26 rule 5's fallback). Revert `rubric.py` to the WP-14
   commit state, keep only `eval/results/fit_eval_round2_dev.json` and this
   file as the record, report, and stop - no test-set run, no further
   labelling effort from Ingo.

## Recommendation

Option 1 (N=3, with cap). It is the only variant with real margin over
D-26's rule 5 floor, keeps the cap that is demonstrably still doing useful
work independent of which skills metric feeds it, and its one new failure
mode (3 false `strong` results, i.e. 15% of the 20 dev listings in run 1)
is a smaller, more specific problem than the metric this round set out to
replace (round 1: `skills: not_met` fired on **all 12** test listings).
The STRONG_THRESHOLD/PARTIAL_THRESHOLD category thresholds (D-9, unchanged
by this round) are the more precise lever for the false-`strong` finding
if it recurs on the fresh test set, not a reason to abandon N=3 now - but
that is a judgment call for Ingo, not something to decide from 20 listings
without a number to tune against.

## Consequences

- If Option 1 or 2 is chosen: `src/job_hunt_agent/rubric.py`'s
  `_skills_verdict` is rewritten to the new metric (Step 3, with
  `tests/test_rubric.py` cases for matched 0/1/N-1/N, duplicate profile
  skills counted once, no skills -> unknown, cap behaviour per this
  decision); `scripts/label_fit.py` extended for the 10 new test listings;
  HALT 3 (Ingo labels) follows.
- If Option 3 (abort): `rubric.py` stays as shipped by WP-14 (D-9/D-21/D-22/
  D-23/D-25); `docs/fit_evaluation.md` gets a short "second round" note
  that the dev-set measurement did not clear D-26's bar and the round
  stopped there; the 10 new test listings in `eval/fit_set_round2.yaml`
  are not labelled or used.
- Either way: the false-`strong` finding above (if Option 1/2 chosen) is
  reported in `docs/fit_evaluation.md`'s "Second round" section regardless
  of what the fresh test-set run shows, per D-26's "reported whatever its
  outcome" rule.

**Decision:** Option 1 (2026-11-16, Ingo): N = 3 (3 or more distinct profile
skills matched -> `met`, 1-2 -> `partly`, 0 -> `not_met`), D-25's cap stays.
Coach review: all four variants independently re-computed from the stored
runs with identical results; rule 5 met (14/20, 15/20, 1 listing differing).
Continue with Step 3 (implementation, blind labelling of the 10 new listings).
