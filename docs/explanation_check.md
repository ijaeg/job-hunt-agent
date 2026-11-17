# Explanation-consistency measurement (D-13 Option 2, spec FR-08, WP-15c)

One measurement run, `openai/gpt-5-mini`, `low` reasoning effort, demo mode
(`FixtureSource`), 3 threads x 2 runs = 24 follow-up answers, `eval/results/
explanation_check.json`. One question set, no dev/test split, never used for
tuning (CLAUDE.md invariant 6 only requires that split for sets used to tune
behaviour; this set only measures). No change to the agent, a tool, the
middleware or `prompts/*.md` — this package is the measurement only.

Categories observed across both runs for the 9 assessed listings matched the
pre-run estimate in `eval/explanation_set.yaml`'s `data_check` exactly: all
three temp-agency listings `excluded`, all three "partial" picks `partial`,
all three "poor" picks `poor`, every run. All 6 turn-d cases (the listing not
assessed in its own thread) triggered a fresh `assess_fit` call rather than a
decline — consistent with `prompts/system.md`'s rule and invariant 2. No
`save_to_tracker`/`remember` call occurred anywhere in the run (this question
set never asks for a write).

## Pass rates per rule

| Rule | Run 1 | Run 2 |
|---|---|---|
| C1 quote fidelity | 5/12 (41.7%) | 9/12 (75.0%) |
| C2 match/gap consistency (turns scored, flag-free) | 8/12 (66.7%) | 6/12 (50.0%) |
| C3 category consistency | 12/12 (100%) | 11/12 (91.7%) |
| C4 no new tool call (turns a–c) | 9/9 (100%) | 9/9 (100%) |
| C5 turn d | 3/3 (100%) | 3/3 (100%) |

**These C1/C2/C3 numbers are misleading taken at face value — see below.** Every
single flag these rules raised (19 C1 flags, 63 C2 flags, 1 C3 flag) was read
individually against the real ad text and the stored assessment, as the prompt
requires.

**Headline: 1 confirmed (borderline) match/gap contradiction in the 24
follow-up answers; no fabricated quote in any follow-up.** C1/C2/C3's automatic
rates above mainly reflect the checks' own low precision, not the model's
answers — the known causes are listed under each rule below (word-fragment
substrings like "met" inside "method(s)", no negation/hedging awareness, a
narrow evidence scope that cannot see non-skills quotes at all, mid-quote
ellipsis, and sentence- rather than clause-level scoring). One further merged
quote was observed in an *initial* assessment answer, outside this package's
measured scope (follow-up turns only) — see "Observation outside the measured
scope" below.

## C1 quote fidelity — every one of the 19 flags verified against the real ad text

`check_quote_fidelity` compares a quoted passage only against `evidence_de`/
`evidence_en` of the stored `FitAssessment.matches`/`gaps` — the only evidence
text spec §6.3 actually keeps. I additionally checked every flagged quote
directly against the fixture's real `title`/`description` text (a substring
check only, nothing printed or committed — CLAUDE.md invariant 4). Every one
turned out to be genuine verbatim ad text (or, in the exclusion case, the
code's own exclusion string) that the narrow evidence pool simply doesn't
cover. None were fabricated or stitched together from unrelated ad passages.

| # | Thread/run/turn | Quote | Why it failed C1 | Verified against real text? |
|---|---|---|---|---|
| 1 | t1 r1 b | "Sicherer Umgang mit gängigen Data-Science-Tools (…PyTorch) ..." | mid-quote `...` breaks exact-substring match | ✅ verbatim prefix of BWI's stored evidence |
| 2 | t1 r1 b | "Unsere Kunden berätst Du methodisch und technisch ..." | non-skills (German-level) evidence isn't stored at all | ✅ verbatim in DYMATRIX's ad text (not BWI's — model was citing the right listing, I initially checked the wrong one) |
| 3 | t1 r1 c | "...PyTorch) …" (first half) | mid-quote `…` | ✅ verbatim prefix of BWI's stored evidence |
| 4 | t1 r1 c | "… sowie verbreiteten DevOps-Tools…(…S3)" (second half) | mid-quote `…` | ✅ verbatim suffix of the same BWI evidence string |
| 5 | t2 r1 a | "Erweitertes Know-how im Prompt Engineering ... (…)" | mid-quote `...` | ✅ verbatim prefix+suffix of Löwenstein's stored evidence |
| 6 | t2 r1 a | "Konzeption und eigenständige Umsetzung von KI-Lösungen" | not in any stored evidence_de/en at all | ✅ verbatim substring of Löwenstein's real ad description — genuinely real text the extraction never captured as skill evidence |
| 7 | t2 r1 a | "Generierung KI-gestützter Workflows, ... Agenten / Copiloten" | mid-quote `...` | ✅ verbatim prefix+suffix of Löwenstein's stored evidence |
| 8 | t2 r1 a | "Homeoffice gemäß aktueller Betriebsvereinbarung möglich" | non-skills (remote) evidence isn't stored | ✅ verbatim in Löwenstein's ad text |
| 9 | t2 r1 a | "Sehr gute Deutsch- und Englischkenntnisse in Wort und Schrift" | non-skills (German-level) evidence isn't stored | ✅ verbatim in Löwenstein's ad text |
| 10 | t2 r1 b | "befristet bis Mitte 2028" | non-skills (employment-type) fact, from the title, not extraction | ✅ verbatim in Hamburger Energienetze's title |
| 11 | t2 r1 c | "JUnit, Spring Test, Kotlin Test, Testcontainers" | each of the 4 skills' *own* stored evidence_de is just its own name; the combined comma list isn't in the evidence pool | ✅ verbatim contiguous substring of the real ad text — genuinely one real sentence, not 4 entries stitched together |
| 12 | t2 r1 d | "verhandlungssicher in Deutsch und gut in Englisch" | non-skills (German-level) evidence isn't stored | ✅ verbatim in SIGNAL IDUNA's ad text |
| 13 | t2 r2 a | "Erweitertes Know-how im Prompt Engineering ... (…)" | mid-quote `...` | ✅ verbatim (same evidence string, run 2's own extraction) |
| 14 | t2 r2 a | "Abgeschlossener technischer Bildungsweg…Deep Learning..." | mid-quote `...` | ✅ verbatim prefix of Löwenstein's stored evidence |
| 15 | t2 r2 a | "Gewährleistung der datenschutzkonformen Nutzung ... Medical Device, MDR, ISO" | mid-quote `...` | ✅ verbatim prefix+suffix of Löwenstein's stored evidence |
| 16 | t2 r2 b | "Excludes temporary agency work" | paraphrase of the exclusion fact, not ad text or the exact code string | ⚠️ not a quote of anything specific — a labelled paraphrase, not ad evidence; low risk (states a true fact, in its own words, inside quote marks it shouldn't have used) |
| 17 | t3 r1 a | "Sie haben bereits Erfahrung im Bereich Visualisierung und Usability Design..." | mid-quote `...` | ✅ verbatim prefix of Hays-898750's stored evidence |
| 18 | t3 r2 a | "temporary agency work (Arbeitnehmerüberlassung)" | `exclusion_reasons` text isn't in C1's evidence pool at all | ✅ exact match of `rubric.hard_exclusions`'s own string |
| 19 | t3 r2 a | "agency work — excluded per profile" | same scope gap, and also a paraphrase | ⚠️ same as #16 — paraphrase in quote marks, not a literal quote of anything |

**Root causes, all pre-existing in the approved check design, none fixed (per
the "change nothing after the run" rule):**
- **Narrow evidence scope (14 of 19):** `FitAssessment` only carries forward
  evidence for the `skills` dimension (spec §6.3); `JobRequirements.
  seniority_evidence`/`german_level_evidence` exist in the LLM extraction but
  `rubric.assess` never copies them into the stored assessment, and
  `exclusion_reasons` was never in scope either. A fully accurate quote about
  German level, remote type, employment type, or an exclusion reason has no
  ground truth to be checked against and will always flag, regardless of
  accuracy.
- **Mid-quote ellipsis (9 of 19, overlapping with the above):** the model
  routinely shortens a single long evidence string with `...`/`…`; my
  normalisation didn't strip it, so an otherwise-exact quote fails.
- **Multi-entry evidence collapsed to a bare name (1 of 19, #11):** when
  several skills share one ad sentence, `rubric.assess` stores each skill's
  own name as its `evidence_de` rather than the shared sentence, so a model
  answer that accurately quotes the real shared sentence has nothing to match
  against.
- **Paraphrase in quote marks (2 of 19, #16/#19):** the model put its own
  summary of a fact in quote marks instead of either quoting the ad or not
  using quote marks at all — stylistically sloppy, but not evidence
  fabrication (D-13's actual concern), since it isn't presented as an ad
  quote.

## C2 match/gap consistency — 63 flags read: 1 confirmed (borderline), 62 false alarms

Every flag was read with its sentence, cross-checked against the full
`matches`/`gaps` lists of the relevant listing(s), and in several cases
against the real ad text directly (same method as C1).

**Confirmed (borderline) — thread 3, run 2, turn d** (`10001-1003863378-S`,
Landesamt für Digitalisierung): *"...The ad explicitly matches Java (one of
your skills) but focuses on desktop/server software, IT-security and
geodata-related relational DB work plus SOAP/REST/JSON/XML interfaces — areas
where your profile has partial overlap **(Java, SQL)** but misses domain
specifics and some technologies."* The parenthetical groups **SQL** together
with Java as something the profile has "partial overlap" with. SQL is in this
listing's stored `gaps`, not `matches` — the profile has PostgreSQL, not a
generic "SQL" skill the rubric's whole-word matching would count as the same
thing. The claim is defensible in substance (PostgreSQL is a SQL database, so
there is a real, if indirect, kernel of relevant experience) but it
contradicts the authoritative `matches`/`gaps` split `prompts/system.md`
tells the model to treat as given ("The assessment's matches and gaps are
already computed by code - treat them as authoritative") — exactly D-13's
error class, even though the practical risk to the user is low. The same
sentence's other flags (IT-Security/SOAP/JSON/XML via "your profile"/"match",
and Java via "miss") are false alarms (bucket 3 below) — only the SQL pairing
inside the explicit "(Java, SQL)" grouping is a real contradiction.

The other 62 flags found no listing's `gaps` item presented as a match or
`matches` item presented as a gap beyond the one case above. They fall into
four heuristic-artifact buckets:

1. **"met" as a word-fragment, not a marker (≈24 flags):** the word
   "met(hod)(s)" / German "Methoden"/"methodisch" contains the match marker
   "met" as a literal substring (`"agile **met**hods"`, `"**met**hodisch"`).
   Every flag in threads using the words "methods"/"methodisch"/"Methoden" in
   an answer is this, not a real signal.
2. **Negated or hedged phrasing (≈27 flags):** "does **not match**", "no
   **matches** to your core skills", "**if** you have cloud experience…", "the
   main reason is the skills mis**match**" (where "mismatch" itself contains
   "match"). The checker has no negation or conditional-hedging awareness —
   exactly the behaviour `check_rules` already names as a known limitation,
   confirmed concretely here, including a brand-new instance from the coach
   review's own new markers: "you have"/"your profile" fire just as readily
   inside "**if** you have X" (a hypothetical about what *would* help) as
   inside a real assertion.
3. **One marker anywhere in a long, compound sentence (≈10 flags):** e.g.
   "you match core items (Python and CI/CD), but the posting calls for
   [gaps]… those are significant **gaps**" — the model correctly scopes the
   match/gap language to the right items *within* the sentence, but C2 is
   sentence-level, not clause-level, so it flags every skill name anywhere in
   that sentence (including, in the confirmed case above, the one it should
   not have scoped that way).
4. **A skill name as a substring of a related compound term (1 flag):** "the
   ad asks for Google Cloud, Vertex AI, …, **Python**-based microservices…"
   under a "Gaps" heading — this is the ad's own stored gap evidence_de
   verbatim ("Python-basierte Microservices", a specific architecture skill
   distinct from plain Python), not a claim that plain Python is a gap; the
   extraction legitimately named the compound skill "Microservices" with that
   German sentence as evidence.

**Reading:** this run surfaced one real, if borderline, D-13-style
contradiction (1 of 63 flags), plus a false-positive rate high enough (62 of
63) that the raw "flag-free" percentage in the table above should not be read
as a quality signal on its own — only the individually-read flags are
informative.

## C3 category consistency — the 1 flag read

Thread 1, run 2, turn a: *"...the assessment found a **strong** mismatch on
the skills dimension (skills: not_met)."* — "strong" is used as an ordinary
English adverb ("a pronounced mismatch"), not a `FitCategory` claim; the
answer's actual stated category elsewhere is "poor", matching the stored
value. **False alarm** — a known risk of using plain-English words ("strong",
"poor") as category markers; this is the first run where it actually fired.

## C4 / C5 — no findings

Both 100% in both runs; no new tool call on any of the 18 a/b/c turns, and all
6 turn-d cases called `assess_fit` for the unassessed listing rather than
guessing (invariant 2).

## Observation outside the measured scope — a merged quote in an initial answer

This package's checks only run on follow-up turns (a–d), per the approved
question-set design — the opening "assess these three listings" message in
each thread is unchecked. Reading the transcripts anyway while verifying the
above surfaced one more D-13-class defect there, worth recording even though
it falls outside what was measured:

Thread 1, run 2, the initial turn, listing `13509-000021113EF002-S` (BWI
GmbH): *"Gaps / prominent requirements: ... ML tooling (MLflow, TensorFlow,
PyTorch), Kubernetes, ... — Evidence examples: ... "**ML-Flow, TensorFlow,
PyTorch, Kubernetes**""*. The stored evidence for this listing is one
sentence: *"Sicherer Umgang mit gängigen Data-Science-Tools (z.B. Python,
ML-Flow, TensorFlow, PyTorch) sowie verbreiteten DevOps-Tools und Standards
(Kubernetes, Git, PostgreSQL, S3)"* — two separate bracketed lists joined by
"sowie verbreiteten DevOps-Tools und Standards" in between. The quoted span
"ML-Flow, TensorFlow, PyTorch, Kubernetes" skips that middle clause entirely,
splicing the tail of the first bracket directly onto the front of the second;
confirmed directly against the real ad text that this exact string is **not**
a contiguous substring anywhere in it. This is D-13's original "merged quote"
failure mode (two real evidence spans stitched into one fabricated-looking
quotation), now observed once, in an initial answer rather than a follow-up.
Not counted in any C1/C2/C3 rate above, and no code change follows from it in
this package (same "no change after the run" rule) — recorded here so the
next prompt-side look at D-13 has it on file.

## Run-to-run spread

C4/C5: identical both runs (100%/100%, no spread — these are structural, not
extraction-dependent). C1/C2/C3: spread between runs (C1 41.7%→75.0%, C2
66.7%→50.0%, C3 100%→91.7%) mostly reflects run-to-run differences in the
fresh extraction (different phrasing, different ellipsis use, one colloquial
"strong"), not a change in real correctness — with one exception: the single
confirmed (borderline) C2 finding occurred only in run 2 (thread 3's turn d);
run 1's flags were all false alarms on manual read, run 2's were all false
alarms except that one.

## Limitations

- **Heuristic C2**, by design (`eval/explanation_set.yaml`'s own `check_rules`
  text) — sentence-level keyword co-occurrence, no negation or scope
  awareness; confirmed concretely in this run (see above).
- **One question set, no tuning split** — these numbers describe this one
  run; no dev/test separation applies since nothing here is tuned against it
  (CLAUDE.md invariant 6).
- **Small set** — 3 threads, 24 follow-up answers, one model
  (`openai/gpt-5-mini`, low effort). Not powered to estimate a rate precisely.
- **C1's evidence scope is narrower than "the ad text"** — it is exactly
  spec §6.3's stored `FitAssessment` evidence (skills only), which is correct
  per the approved rule's wording, but means C1 cannot vouch for or refute
  German-level/remote/employment-type/exclusion quotes at all; every quote
  about those topics will register as a "failure" regardless of accuracy.
  Should a future run show a *real* fabrication in one of those areas, C1
  cannot currently distinguish it from this run's 7 structurally-unverifiable
  cases — widening its evidence pool (propagating `seniority_evidence`/
  `german_level_evidence` into `FitAssessment`, and including
  `exclusion_reasons`) would close this gap, but that is a product/spec change
  outside this package's "no agent/tool/prompt change" boundary.
- **C5 only catches the "states a category word" shape** of an invariant-2
  violation on turn d, not a vaguer answer that implies fit without naming a
  category — unchanged from the HALT 1 design note; not exercised either way
  in this run (all 6 cases called `assess_fit`).

Related: D-13, FR-08 AC1, FR-08 AC2, spec §6.3, §9, invariant 2, invariant 4,
invariant 6, D-28, WP-15c
