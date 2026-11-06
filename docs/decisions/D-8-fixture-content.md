# D-8: Content of the committed fixture set

## Question

May the **cleaned** fixture set (`data/samples/fixtures/listings.json`,
built by `scripts/build_fixtures.py` from the 40 real D-1 listings plus 3
crafted ones) be committed to this public repository as real, cleaned ad
text - or must the committed set be synthetic/paraphrased, or kept local
only? The real listings are third-party employer content reposted by the
Bundesagentur für Arbeit (BA); the BA API's terms of use on redistribution
are unclear (D-7, still open).

## Context

- `pii.py` (this session, WP-02) removes e-mail addresses, phone numbers and
  contact names from the 40 real listings with 0 remaining contact names
  (`spikes/pii_check.py`, `spikes/NOTES.md` § "D-8 preparation") - so the
  *personal-data* risk (D-3) is handled regardless of this decision.
- What is **not** handled by `pii.py` is the separate question of whether
  the *employer's ad text itself* (job description, company name, benefits
  copy) may be redistributed in a public GitHub repository at all. D-7
  (spec §14) already flags the BA API's terms of use here as unverified;
  this decision does not resolve D-7, it only decides what to do **while**
  D-7 stays open.
- `scripts/build_fixtures.py` currently produces 43 listings (40 real +
  cleaned, 3 crafted: the S5 prompt-injection listing, a short teaser with
  `external_url`, one temporary-agency listing) in
  `data/samples/fixtures/listings.json`. The file is generated and sitting
  in the working tree, gitignored for now (`.gitignore`, not committed by
  this change), and `tests/test_fixtures.py` (also uncommitted, held
  alongside) passes against it: 0 e-mails, 0 unmasked phone numbers, 0
  unredacted "Frau"/"Herr" mentions, 0 corrupted reference numbers, unique
  IDs, and all 3 crafted listings present.
- Demo mode (FR-19) and the evaluation (§9.1) both need *some* fixture set
  that ships with the repo so a reviewer can `uv sync && uv run streamlit
  run app.py` with no API key and no manual data-collection step (NFR-01).

## Options

1. **Commit the cleaned real listings as built.** Simplest; the fixture set
   is exactly what the real API returns (minus contact data), so demo mode
   and the evaluation see realistic ad-text length, structure and
   difficulty (e.g. the real teaser-vs-full-text spread from D-2). Risk:
   if BA's terms of use turn out to forbid redistribution (D-7), this
   would need to be reverted and rebuilt later - rewriting history or
   force-pushing is something CLAUDE.md requires asking about separately,
   so a revert would likely need a follow-up commit, not a silent fix.
2. **Replace the 40 real listings with synthetic/paraphrased ones**,
   written by hand or generated to resemble the real distribution (lengths,
   fields populated, the temp-agency/teaser/missing-field edge cases from
   D-1), keeping only the 3 already-crafted listings as-is. No
   redistribution question at all. Cost: separate authoring effort now,
   before FR-19/§9 can be finished; the evaluation (§9.3, fit labels) would
   be labelling synthetic text instead of real ad language, which is a
   small extra step removed from how a real BA ad reads.
3. **Keep the real cleaned listings local only** (current state: gitignored,
   built on demand by `scripts/build_fixtures.py`, which stays committed
   and documented), and ship only the 3 crafted listings in the committed
   set for now. A fresh clone still runs (NFR-01) with a minimal demo set;
   anyone who has (or re-runs) the D-1 spike locally gets the full 43.
   Weakest demo experience for a reviewer who has not run the spike, and
   the evaluation set (§9.1, ~40 listings) would need a different source
   until D-7 or this decision changes.

## Recommendation

Option 3 as the default until D-7 is answered, with a low bar to switch to
Option 1 once it is: BA's terms of use are a legal question outside my
competence to judge, D-7 is explicitly still open, and "ignore it and ship
anyway" is the one path that cannot be undone cheaply if the answer turns
out to be "no". Option 3 costs the least now (the script and tests already
work; only the commit scope changes) and keeps NFR-01 satisfied with a
smaller demo set. If D-7 resolves favourably, switching to Option 1 is a
one-line `.gitignore` change plus committing the already-built,
already-tested file - no rework.

## Consequences

- **If Option 3 (recommended):** `.gitignore`'s `data/samples/fixtures/`
  line stays; only 3 crafted listings ship in a *separate*, explicitly
  committed file (e.g. `data/samples/fixtures/demo_listings.json`, built
  by a small hand-written fixture, not by `scripts/build_fixtures.py`
  against spike data). `scripts/build_fixtures.py` and
  `spikes/pii_check.py` stay committed as-is (no ad text, no personal data
  in either). FR-19 AC4 and §9.1's "about 40 listings" note would need a
  spec correction to describe the smaller committed set and the local-build
  path for the full one - flagged here, not applied without Ingo's
  confirmation (CLAUDE.md "Do not change `PRODUCT_SPEC.md` on your own").
  `tests/test_fixtures.py` adjusted to check whichever file is actually
  committed.
- **If Option 1:** remove the `data/samples/fixtures/` line from
  `.gitignore`, commit `data/samples/fixtures/listings.json` and
  `tests/test_fixtures.py` together (one commit, this file as its basis of
  approval). No spec change needed - FR-19 AC4 and §9.1 already describe
  this shape.
- **If Option 2:** `scripts/build_fixtures.py`'s 40-listing path is
  replaced or supplemented by hand-authored/synthetic listings; the "40
  real listings" framing in §9.1 and D-3 would need a spec correction to
  "40 synthetic listings modelled on the D-1 spike's field distribution".
  Larger follow-up task, not started in this session.
- None of the three options change `pii.py`, `models.py` or the BA client
  (step 4 of this work package) - this decision is scoped to what gets
  committed, not how it is cleaned.

**Decision:** Option 1 - commit the cleaned real listings as built
(`data/samples/fixtures/listings.json`, 43 entries) together with
`tests/test_fixtures.py`. - Ingo, 2026-11-06
