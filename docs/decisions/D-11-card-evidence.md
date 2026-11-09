# D-11: where does the German quote for FR-07 AC1's top-3 matches come from?

## Question

FR-07 AC1 requires each shortlist card to show its top 3 matching requirements
"with evidence (German quote + English translation)". Where should the UI get
the German quote from?

## Context

Confirmed by reading `tools/assess.py`, `rubric.py` and `state.py`:

- `rubric.assess()` builds `FitAssessment.matches` as
  `f"{r.name} — {r.evidence_en}"` (`rubric.py:327-331`) from the per-listing
  `JobRequirements` extraction — `evidence_de` is read nowhere in this
  function.
- `JobRequirements` (the extraction output, which *does* carry
  `evidence_de`, spec §6.2) is built and consumed entirely inside
  `assess_fit`'s local scope (`tools/assess.py::assess_fit`, the `extracted`
  dict) and is never written to `JobHuntState`. Only the derived
  `FitAssessment` is stored, in `state["assessments"]`.
- So after one `assess_fit` call returns, the German quote for any match is
  gone from everything the UI (or a later turn) can read. `FitAssessment`
  (spec §6.3) is a tool contract — changing its shape needs a decision
  (CLAUDE.md).

## Options

1. **Change `FitAssessment.matches`/`gaps` from `list[str]` to a structured
   list** (e.g. `list[MatchEvidence]` with `name`, `evidence_de`,
   `evidence_en`), built by `rubric.assess()` directly from
   `requirements.skills`. Cleanest fit with spec §6.3's intent (fit evidence
   is part of the fit result) and gives any future consumer (FR-08
   follow-up answers, an export) structured access to both quotes.
   **Cost:** touches `models.py` (`FitAssessment`), `rubric.py`, and every
   test that currently asserts the `"name — evidence_en"` string shape
   (`tests/test_rubric.py`, parts of `tests/test_tools_assess.py`) — a
   tool-contract change in the sense CLAUDE.md means it.
2. **Add a `requirements: dict[str, JobRequirements]` field to
   `JobHuntState`** (same pattern already used for `summaries` —
   `state.py` already documents one field added beyond spec §5.3's list for
   exactly this kind of "a consumer other than the rubric needs raw data"
   case), populated by `assess_fit` alongside `assessments`. The UI looks up
   `evidence_de` there, matching `FitAssessment.matches`' entries by skill
   name. **Cost:** one field added to `state.py` and one line in
   `tools/assess.py` (store `extracted` into state); `FitAssessment` and
   `rubric.py` stay byte-for-byte unchanged, so no existing test changes.
3. **Re-fetch and re-extract on demand in the UI.** Rejected outright: would
   mean either a second LLM call per card render (cost, latency, and a
   second source of truth for the same extraction) or re-running the
   rubric's own matching logic in `ui_view.py` — exactly the kind of
   model/code duplication CLAUDE.md's architecture forbids.

## Recommendation

Option 2. It gets FR-07 AC1's German quote onto the cards without touching
`FitAssessment`'s shape, `rubric.py`, or any of their existing tests —
lowest risk for this work package, and it reuses a pattern (`state.py`'s
`summaries` field) already approved once before. Option 1 is the more
architecturally "correct" home for this data long-term (fit evidence as
part of the fit result, spec §6.3) but is a larger, separable change; worth
revisiting once the UI's actual usage patterns for match evidence are
clearer.

Until this is decided, `ui_view.py` builds cards with the English evidence
only; the German quote is a `# TODO(D-11)`-marked gap, not silently dropped.

## Consequences

- If Option 2: `state.py` (`JobHuntState.requirements` field + docstring),
  `tools/assess.py` (`assess_fit` stores `extracted` into state), `ui_view.py`
  (look up `evidence_de` by skill name for the top-3 matches). No change to
  `models.py`, `rubric.py`, or their tests.
- If Option 1: `models.py` (`FitAssessment.matches`/`gaps` shape),
  `rubric.py` (`assess()`), `tests/test_rubric.py`,
  `tests/test_tools_assess.py`, and `ui_view.py`.
- Either way: `prompts/extract_requirements.md`/FR-05 AC2's verbatim-evidence
  check is unaffected — `evidence_de` already exists on `Requirement`, this
  decision is only about which object the card-building code reads it from.

**Decision:** Option 1 (2026-11-09, Ingo). Implemented in WP-05.
