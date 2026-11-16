# D-21: Skill-extraction granularity (`Requirement.name`)

Related: spec §6.2, §7 "Skills", FR-05 AC1, FR-05 AC2, D-9, WP-14

## Question

`Requirement.name` and `prompts/extract_requirements.md` give the model no
guidance on how big a "skill" should be. Should the schema/prompt be
changed to require short, atomic skill/technology names, and should the
all-evidence-dropped case be scored differently from "no skills in the
ad"?

## Context

WP-14's dev-set run (`eval/results/fit_eval_dev.json`, 8 listings, 2 runs
each, `openai/gpt-5-mini`, reasoning effort `low`) found the skills
dimension is by far the worst-agreeing one: 37.5–50 % (run 1/run 2) vs.
75–100 % for the other four dimensions. 16 of the 36 dev disagreements
are tagged `extraction_error`, and 9 of those are skills-dimension
disagreements. `total_dropped_evidence` across the 16 runs is **58** -
3.6 per run on average.

Reading the actual extractions explains why: the model frequently returns
full requirement **sentences** as `name`, not atomic skills, e.g. (DEKRA,
`11119-4964515256-S`, run 1):

> "Planung, Entwicklung und Konfiguration von Simulationsnetzwerken und
> deren Komponenten (HW und SW)"

> "Implementierung und Auswertung von Unit- und Subsystemtests,
> Durchführung von Tests und Anpassungen der Erhöhung der
> Systemstabilität"

as two of 18 "skills" for one listing, alongside soft-skill bullets like
"Teamfähigkeit, Selbstständigkeit und hohe Kommunikationsfähigkeit" and
"Gute Englischkenntnisse". None of these can ever whole-word-match a
profile skill token (D-9); they inflate the denominator of the skills
share, and - being long, free-form text - they are also fragile against
the verbatim-evidence check (FR-05 AC2): a second run of the *same*
listing (`11119`, run 2) returned only 2 of the same requirements, the
other 20 dropped for non-verbatim evidence (paraphrasing/reformatting
between runs), swinging `dropped_evidence` from 0 to 20 while the final
`skills: not_met` verdict happened to stay the same by luck.

The worst case (`12288-4971252625-S`, run 1): the model extracted 21
"skills", **all 21** were dropped for non-verbatim evidence, leaving
`requirements.skills == []`. `_skills_verdict` treats an empty list the
same as "the ad has no skills" and returns `unknown` - the heaviest
dimension (weight 2) silently drops out of the score, which is exactly
the D-9 failure mode but via a different mechanism (evidence-matching
failure instead of a missing `required` flag). Category for that run
came out `partial`; label and the listing's own run 2 (2 skills
extracted, 15 dropped, verdict correctly `not_met`) both say `poor`.

By contrast, listings where the ad repeats a short, named skill list
(`19913-3074751792188001-S`, NTT DATA: "Python", "PyTorch", "Docker",
"Kubernetes", ...) still score `skills: not_met` against label `partly`
in both runs, but with 0 `dropped_evidence` and no run-to-run skills
mismatch - the granularity problem, not the matching rule itself, is the
dominant driver here.

## Options

1. **No change.** Keep `Requirement.name` and the prompt as they are.
   Simplest; leaves the worst-performing dimension and the highest
   `dropped_evidence` count unaddressed, and risks the same "all evidence
   dropped -> unknown" failure recurring on the test set.
2. **Add field guidance**: `Requirement.name` gets a `Field(description=...)`
   ("a short, specific skill or technology name such as 'Python' or
   'Kubernetes', not a full sentence or requirement description") and
   `prompts/extract_requirements.md` gets one worked example (a short
   skill list vs. a rejected full-sentence example) based on one of the
   dev listings above. No schema shape change (spec §6.2's `Requirement`
   fields are unchanged), only the guidance the model receives when
   `with_structured_output` builds its tool schema and when it reads the
   prompt. Needs a dev-set re-run to confirm the fix actually changes the
   extraction (same D-9 pattern: confirm with a repeat run, don't assume).
3. **Option 2, plus**: when every extracted skill is dropped for
   non-verbatim evidence (`requirements.skills` becomes empty **after**
   `drop_non_verbatim_evidence`, not before), score the dimension
   `not_met` instead of `unknown` if `dropped_evidence > 0` on entry (i.e.
   distinguish "the ad stated no skills" from "the ad stated skills but
   none survived the evidence check"). Requires `rubric._skills_verdict`
   (or its caller) to see the pre-drop count, a small rubric-logic change
   on top of Option 2's prompt/schema change.

## Recommendation

Option 3. The granularity fix (Option 2) should remove most of the
sentence-as-skill cases on its own, but the `12288` case shows the
all-dropped failure mode can still happen (e.g. on a short or
teaser-length ad) and silently removes the heaviest-weighted dimension
from the score exactly like the bug D-9 already fixed once; closing both
at once avoids re-discovering the same failure shape a third time on the
test set.

## Consequences

- `src/job_hunt_agent/models.py`: `Requirement.name` gets a
  `Field(description=...)`.
- `prompts/extract_requirements.md`: one short/long worked example.
- `src/job_hunt_agent/tools/assess.py`: `_extract_one` or
  `drop_non_verbatim_evidence` needs to report whether any skill was
  dropped (not just the count, which it already returns) so
  `rubric.assess`/`_skills_verdict` can tell "empty because nothing was
  extracted" apart from "empty because everything was dropped"; the
  `_skills_verdict` signature changes to take that flag.
- Tests: `tests/test_tools_assess.py`, `tests/test_rubric.py` get a case
  for all-evidence-dropped -> `not_met`, not `unknown`.
- Dev listings this would likely change: `12288-4971252625-S` (skills
  `unknown` -> `not_met`, category `partial` -> `poor`, matching the
  label); the granularity fix alone should improve (not guaranteed to
  fully fix) the skills verdict on `17338`, `19913`, `13509`,
  `12336-a26f1192j0456061-S` - must be re-measured, not assumed.
- No change to weights or thresholds (D-9's start values stand).

**Decision:**
