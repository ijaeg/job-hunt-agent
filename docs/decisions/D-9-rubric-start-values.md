# D-9: Fit rubric start values

## Question

`rubric.py` (this session, WP-02) implements §7's fit rubric as written, with
three choices the spec left open or only implied: (a) the exact numbers -
weights, the 75 %/45 % category thresholds, the 70 %/40 % skill thresholds;
(b) how an extracted skill name counts as "in the profile" (exact name,
normalised name, or a small synonym list - §7 does not say); (c) whether
`data/samples/profile_alex.yaml` (this session) is the right demo profile.
Do these start values hold, or should any change before they are used for
real listings and the evaluation (§9.3)?

## Context

`rubric.py` was run on the 5 listings spike D-4 already extracted
`JobRequirements` for (gpt-5-mini, run 1 of 2), with the demo profile
below. One finding changes how the Skills dimension should probably be
read, so it is reported first.

### Demo profile used (`data/samples/profile_alex.yaml`)

```yaml
skills: [Python, Java, FastAPI, PostgreSQL, Docker, CI/CD]
seniority: senior
location: Hamburg
radius_km: 25
remote_preference: hybrid
wants_full_time: true
wants_permanent: true
exclude_temp_agency: true
german_level: basic
english_level: native
```

### Finding: gpt-5-mini rarely marks a skill `required: true`

Of the 5 listings' extractions, **4 of 5 have zero skills flagged
`required: true`** (only the EXXETA Java listing has any - all 7 of its
skills are `required: true`). Spec §7 reads "unknown: no required skills
extracted" - applied literally, the Skills dimension (weight 2, the
heaviest) is `unknown` for 4 of 5 real listings, not because the ad has no
skills, but because the model did not mark any as strictly required. This
is a property of the extraction, not of the ads - all 4 "unknown" listings
plainly list skills in their text (confirmed by reading the raw extraction
output, not shown here per CLAUDE.md invariant 4).

Two readings, with the actual numbers for all 5:

| Referenznummer | Required / total skills | Share matched among **required only** | Share matched among **all extracted** |
|---|---|---|---|
| 10001-1003893191-S (ThoughtWorks, Agentic AI Principal) | 0 / 14 | unknown | 2/14 = 14 % |
| 12336-a26f1192j0455715-S (EXXETA, Java/Kafka) | 7 / 7 | 1/7 = 14 % | 1/7 = 14 % |
| 13545-DZTBHCDPFNHF7DSR-S (Dock 22, Marinesysteme) | 0 / 11 | unknown | 3/11 = 27 % |
| 19522-0068291613-S (Löwenstein, AI Engineer) | 0 / 18 | unknown | 0/18 = 0 % |
| 19913-3087851793401200-S (NTT DATA, Forward Deployed Engineer) | 0 / 11 | unknown | 1/11 = 9 % |

Under "all extracted" with the same 70 %/40 % thresholds, every one of
these 5 would be `not_met` (all shares < 40 %), never `unknown` - a
materially different signal that also changes 3 of the 5 overall
categories (see the per-listing table below, "if skills counted" column).

## Per-listing result (gpt-5-mini, run 1, demo profile)

Distance (`entfernung`) was not available for this spot-check - these 5
reference numbers were sourced from `spikes/fixtures/details/`, which does
not carry it (only the matching search response does, and 3 of these 5 are
among the referenznummer-corruption cases from D-1/D-4, so `distance_km` is
`None` here for all 5; `location_remote` below is only the remote-vs-profile
part of that dimension, not an actual radius check). `scripts/build_fixtures.py`
does cross-reference distance correctly for the 37 non-corrupted listings.

| Referenznummer | Employer / role | Category (as shipped) | Category if skills counted (all extracted, not_met) | Exclusion reason | Unknown dimensions | low_evidence |
|---|---|---|---|---|---|---|
| 10001-1003893191-S | ThoughtWorks, Agentic AI Principal | **strong** | partial | - | skills | false |
| 12336-a26f1192j0455715-S | EXXETA, Senior/Lead Java (Kafka, finance) | partial | partial (unchanged) | - | - | **true** (284-char teaser) |
| 13545-DZTBHCDPFNHF7DSR-S | Dock 22, IT-Entwickler Marinesysteme | **excluded** | excluded (unchanged) | temporary agency work | skills, seniority | false |
| 19522-0068291613-S | Löwenstein, AI Engineer | partial | poor | - | skills, seniority | false |
| 19913-3087851793401200-S | NTT DATA, Forward Deployed Engineer (AI) | **strong** | partial | - | skills | false |

### My read on plausibility (so Ingo can judge quickly)

- **10001 ThoughtWorks (strong) - too generous.** This is a Principal-level
  AI-consulting-leadership role, two seniority levels above a senior IC and
  commercially/consulting-flavoured, not an engineering IC role matching
  Alex's profile - the rubric only reads it as "strong" because Skills
  dropped out entirely (unknown) and `seniority` only scored `partly` (one
  level apart under a 4-level scale that caps "lead" one step above
  "senior", when the real gap reads more like two). I would not ship
  "strong" for this one; it supports fixing the Skills-unknown issue above
  over leaving it as is.
- **12336 EXXETA (partial) - plausible either way.** Senior/Lead Java,
  finance-domain Kafka role; Alex has Java but the ad's specific stack
  (Kafka, event-driven, BaFin/MiFID II compliance) is mostly a gap. Partial
  with 1/7 explicit required-skill matches reads right; `low_evidence` is
  correctly set from the 284-character teaser text (FR-04 AC5), a separate,
  working mechanism from the skills-unknown issue above.
- **13545 Dock 22 (excluded) - correct and working as intended.** Hard
  exclusion fires on `istArbeitnehmerUeberlassung: true` regardless of the
  skills question; this is the mechanism FR-06 AC1 is for, and it is not
  affected by the finding above.
- **19522 Löwenstein (partial) - plausible, borderline.** AI engineering
  role, senior-adjacent from the text but not explicitly leveled (so
  `seniority: unknown`), German-first title; `partial` without an
  exclusion looks reasonable for a profile with only `basic` German
  against a role that leans more German-first than most of the other 4.
- **19913 NTT DATA (strong) - too generous, same root cause as 10001.**
  Fully remote (`remote_percent: 100`), matching location/remote and
  seniority cleanly, but again scores "strong" mostly because Skills
  dropped out; the role (GenAI/LLMOps infrastructure specialist) is a
  plausible but not obvious fit for Alex's Python/Java/FastAPI profile,
  and "strong" overstates that without any skill evidence actually
  counted.

**Net read:** both "strong" results and one of the two "partial" results
with no exclusion are driven in part by the Skills-unknown effect; fixing
it (Option 2 below) moves 10001 and 19913 to "partial" and 19522 to
"poor", which matches my own plausibility judgment above better than the
as-shipped numbers.

## Options

1. **Keep §7 as shipped**, literally: `unknown` only when no skill is
   flagged `required: true`, regardless of how many skills with no flag
   were extracted. Simplest, no code change, but - per the finding above -
   produces 2 of 5 "strong" categories that I would not call strong on a
   read of the actual ad text, driven by the heaviest-weighted dimension
   silently dropping out.
2. **Count all extracted skills, not only `required: true` ones**, for the
   Skills dimension's share calculation (keep `required` as a smaller
   signal elsewhere, e.g. weighting a required skill match double a
   non-required one, or simply ignore the flag for this one dimension).
   Matches my plausibility read better (3 of 5 categories drop one notch,
   all in the direction I'd expect from reading the ads). Requires a small
   `rubric.py` change (`_skills_verdict`) plus updated tests; no spec
   change needed if the wording is read as "required skills" meaning "the
   skills the ad requires" rather than "the skills the model happened to
   flag `required`".
3. **Ask the extraction prompt to set `required: true` more consistently**
   instead of changing the rubric (fix the cause, not the symptom). Keeps
   §7 exactly as written; cost is a prompt-engineering pass plus a repeat
   of the D-4-style spike to confirm the fix actually changes the
   extraction rate, before this question can be closed - more work than
   Option 2, and the prompt lives in a later work package, not this one.

## Separate: skill-name matching (exact vs. normalised vs. synonym list)

`skill_matches_profile` (shipped) matches if a profile skill token is a
case-insensitive substring of the extracted skill name or vice versa
("normalised/substring"). Comparison on the one listing with
`required: true` skills (12336, EXXETA):

| Matching strategy | Required skills matched | Share | Would-be verdict |
|---|---|---|---|
| Exact name equality | "Java" only (exact string `"Java"`) | 1/7 = 14 % | not_met (same as shipped - substring happens to find only the same one here) |
| Normalised/substring (**shipped**) | "Java" only | 1/7 = 14 % | not_met |
| Small synonym list (not built) | would additionally need e.g. "Kafka"→"Apache Kafka" style entries; none of this listing's 6 unmatched skills (event-driven architecture, microservices, Apache Kafka, legacy modernization, BaFin/MiFID II compliance, team leadership) map to any profile synonym Alex's skill list would plausibly carry | 1/7 = 14 % | not_met |

On this one example exact and substring happen to agree because the only
match is a bare single-word skill name; the two *do* differ on the other 4
listings' informal "would it count" check (see the D-9 preparation
numbers above: e.g. "Programmiersprachen: Java, Python, C#..." only
matches under substring, not exact). A synonym list would help a
differently-shaped case (abbreviations like "ML"/"k8s") not present in
this 5-listing sample, so there is no evidence here either way for or
against building one yet.

## Recommendation

- Start values (weights, 75 %/45 %, 70 %/40 %): **keep as shipped**
  pending Ingo's own read; nothing in this 5-listing sample argues for a
  specific different number, only for *how the Skills dimension's
  denominator is chosen* (see above).
- Skills dimension: **Option 2** - count all extracted skills, not only
  `required: true` ones. The `required` flag's own low hit-rate (1 of 5
  listings) makes the literal §7 reading behave like "usually unknown",
  which silently removes the single heaviest-weighted dimension on 4 of 5
  real listings and produces the two "strong" results I would not call
  strong above.
- Skill matching: **keep substring/normalised** (shipped); no evidence
  yet for a synonym list, and exact matching is demonstrably too strict on
  real extractions (D-9 preparation data).
- Demo profile: no change suggested; it reads as a reasonable
  operationalisation of persona §3.1 and nothing in the 5-listing run
  exposed a gap in it (the German-level and seniority fields were the ones
  exercised, and both behaved as expected: AC "language" fired `partly`
  exactly where the ad implied more German than `basic`, and `met` or
  `unknown` elsewhere).

## Consequences

- **If Option 2 is confirmed:** change `_skills_verdict` in `rubric.py` to
  drop the `r.required` filter (use `requirements.skills` directly), update
  its docstring and the "unknown: no required skills extracted" label text
  in `assess`, and update/replace the skills-dimension tests in
  `tests/test_rubric.py` (`test_skills_unknown_when_no_required_skills_extracted`
  would need a new scenario - e.g. truly empty `skills: []` - since a
  non-empty but all-optional list would no longer be `unknown` under this
  option). No spec wording change needed if "required skills" in §7 is
  read as "the ad's skill requirements" (what WP-02 instructions call
  "required skills in profile", not literally the `required: true` flag).
  If Ingo prefers the letter of §7 kept and the fix applied to the
  extraction prompt instead (Option 3), this is deferred to the work
  package that builds `assess_fit` and its prompt.
- **If Option 1 (no change) is confirmed instead:** no code or test change;
  the two "strong" results and the "unknown" skills dimension on 4 of 5
  real listings stand as shown above, to be revisited once more labelled
  data exists in §9.3's fit evaluation.
- Either way: no change to weights, thresholds or the demo profile.

**Decision:** Option 2 for the Skills dimension - count all extracted
skills, not only `required: true` ones. Start values (weights, 75 %/45 %,
70 %/40 %), substring/normalised skill matching, and the demo profile all
stay as shipped. - Ingo, 2026-11-06

## Addendum (WP-03, 2026-11-06): whole-word matching, no category changes

The substring matching this file originally shipped with was too loose:
"Java" matched inside "JavaScript", "C" matched inside "CI/CD", "R" matched
inside "Docke**r**". `skill_matches_profile` now requires a whole-word match
(case-insensitive, via `(?<!\w)...(?!\w)` lookarounds - plain `\b` fails on
tokens like "C#"/"C++" since a non-word character on both sides of the
token leaves no word/non-word transition for `\b` to anchor on).

Re-ran the same 5 D-4 listings (gpt-5-mini run 1, demo profile) with the
new whole-word matcher:

| Referenznummer | Category (substring, as decided above) | Category (whole-word) | Changed? |
|---|---|---|---|
| 10001-1003893191-S | partial | partial | no |
| 12336-a26f1192j0455715-S | partial | partial | no |
| 13545-DZTBHCDPFNHF7DSR-S | excluded | excluded | no |
| 19522-0068291613-S | poor | poor | no |
| 19913-3087851793401200-S | partial | partial | no |

**No category changed** on this sample. The matched-skill counts did shift
down for two listings (12336: 1/7 unchanged; 13545: 3/11 -> 2/11, one
substring false-positive removed; 19522: 0/18 unchanged; 19913: 1/11
unchanged; 10001: 2/14 unchanged) - all stayed within the same `not_met`
bucket (share < 40 %) either way, so the fix corrects a real false-positive
source (confirmed by the dedicated matching tests: "Java"/"JavaScript",
"C"/"CI/CD", "R"/"Docker") without moving any of these 5 listings' output.
No further action needed here; worth re-checking once the labelled fit set
(§9.3) exists, since a larger or differently-shaped sample could expose a
case where it does flip a category.

