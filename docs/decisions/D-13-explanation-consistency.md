# D-13: Consistency of follow-up explanations with the stored assessment

Related: FR-08 AC1, FR-08 AC2, spec §9, D-11, WP-05 Addendum 1 #4, WP-05 Addendum 2

## Question

The free-text answer to a follow-up question (S2, "Why is #3 only
partial?") can contradict the stored `FitAssessment`. How should this be
fixed: with more prompt rules now, or with a code check?

## Context

Real-model runs in WP-05 (`eval/results/wp05_s1_s2.json`, write-up in
`spikes/NOTES.md` § "WP-05 Addendum 1 #4" and § "WP-05 Addendum 2"):

1. First run: the answer called Java a gap and shortened the profile's
   skill list, although Java was in `matches` and in the profile.
2. After a prompt rule ("`matches` and `gaps` are authoritative; quote the
   profile's skills in full"): the Java error was gone, but a `gaps` item
   was presented as a match, with a quote merged from two separate
   evidence entries.

The rubric and the stored assessment were correct both times. The error is
in how the model restates them in prose. Each prompt rule so far has
covered one direction of the error, not the error class.

## Options

1. **Another prompt round now:** extend the rule symmetrically ("never
   present a `gaps` item as a match") and forbid merged quotes. Cheap, but
   unmeasured; the next variant of the error may appear again.
2. **Code check in the evaluation work package:** a deterministic checker
   compares each follow-up answer with the stored assessment - every quoted
   German passage must be a verbatim `evidence_de` of the listing, and no
   item from `matches` may be presented as a gap or vice versa. Run on the
   scenario set (§9.2) and reported as a metric; prompt changes are then
   judged by that number.
3. **Accept as a known limitation** and only document it in the README.

## Recommendation

Option 2. It turns the problem into a measured result, which is what the
review asks for, and it tests prompt changes instead of guessing at them.

## Consequences

- Until the evaluation work package, the error stays a known, documented
  issue; no further prompt change for it in between.
- The evaluation work package adds the checker and an FR-08 metric next to
  the tool-trajectory metrics (§9.2); the result goes to `eval/results/`.
- A prompt fix, if still needed, is made in that package and measured with
  the checker before and after.

**Decision:** Option 2 (2026-11-09, Ingo). Build the code check in the evaluation work package; no further prompt round until then.
