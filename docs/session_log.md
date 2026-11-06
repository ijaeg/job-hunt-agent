# Session log

## 2026-11-05 — WP-01: tooling, config, spikes D-4 and D-5

**Done:**

- Tooling and configuration (NFR-01, NFR-06): `pyproject.toml` (real
  description, ruff/mypy/pytest config, placeholder script entry removed),
  `src/job_hunt_agent/config.py` (model, ZDR provider routing, BA API
  settings, spec §8 timeouts, FR-20 limits), `.env.example`,
  `tests/test_config.py`, `.github/workflows/ci.yml`.
- Spike D-4 (model and extraction quality, FR-05, FR-02): compared
  `openai/gpt-5-mini` vs. `anthropic/claude-haiku-4.5` on 5 listings × 2 runs
  for structured extraction, plus 3 tool-calling prompts each - 26 calls
  total. Both kept ZDR routing intact; `gpt-5-mini` faster, cheaper, slightly
  higher verbatim-evidence rate; both 3/3 correct on tool calling. Results:
  `spikes/d4_results.json`, `spikes/NOTES.md` § D-4.
- Spike D-5 (HITL interrupt/resume in Streamlit, FR-10): `spikes/hitl_app.py`
  prototype with `HumanInTheLoopMiddleware` + a custom
  `RejectionLockMiddleware`. Found that `after_model` hooks run in *reverse*
  middleware-list order (undocumented, found by reading
  `langchain/agents/factory.py`) - the rejection lock must be listed *after*
  HITL for its `after_model` to run first. 6 automated `AppTest` checks
  (scripted model, `spikes/test_hitl_app.py`) plus one real-model run, all
  passing. Also answered D-6 (SQLite-backed `langgraph.store.sqlite.SqliteStore`
  is available in already-approved dependencies). Manual checklist:
  `docs/manual_tests/D-5-checklist.md`. Write-up: `spikes/NOTES.md` § D-5.
- Decision files written (Options with numbers from the spike runs):
  `docs/decisions/D-4-model.md`, `docs/decisions/D-5-hitl-streamlit.md`,
  `docs/decisions/D-6-memory-storage.md`. Decided by Ingo on
  2026-11-05 (see status below).

**Checks:** `uv run pytest` 10/10 passed, 100 % coverage on `job_hunt_agent`;
`uv run pytest spikes/test_hitl_app.py` 6/6 passed (not part of the
coverage-tracked suite); `uv run ruff check .` clean; `uv run ruff format
--check .` clean; `uv run mypy src` clean.

**Decision files, status:** D-4, D-5, D-6 written this session and
**decided by Ingo on 2026-11-05** (*Decision:* lines in the files; recorded
in the last commit of WP-01). Nothing open.

**Next:**

- ~~Ingo reads and records decisions in D-4/D-5/D-6.~~ Done 2026-11-05.
- Cleaned fixture set and ad-text cleaning
  (`pii.py`, FR-22), `ba_client.py`, fit rubric (§7) with tests (per the
  project plan, spec §13, Sat–Sun).
- `RejectionLockMiddleware` and the `SqliteStore` wiring move from spike
  prototype to real modules (`middleware/rejection_lock.py`, memory storage)
  once the decisions are confirmed.

## 2026-11-06 — Documentation update (coach)

- Corrected the WP-01 entry above: D-4, D-5 and D-6 were decided on
  2026-11-05; the entry had been written before the decisions were recorded.
- `PRODUCT_SPEC.md` v0.1.3 – v0.1.5 (not by Claude Code): decisions D-4 – D-6
  in §14 and the resulting changes (§5.4 middleware list order, FR-10 AC5/AC6,
  FR-15 AC1, §11), FR-02 AC7 (plain keywords), FR-22 AC5 (clean free text
  only; the phone detector must not match reference numbers – the D-1 spike
  masked `19522-0068291613-S` as `19522-[TELEFON]-S`), R-4 with the D-4
  latency numbers; time budget and §13 "Order of work".

**Open decisions:** none. **Next:** WP-02.

## 2026-11-06 — WP-02: data layer (models, PII cleaning, fixtures, BA client, rubric)

**Done** (branch `feature/data-layer`, nothing committed yet - see "Status"
below):

- `src/job_hunt_agent/models.py` (spec §6): `ToolResult`, `JobSummary`,
  `JobDetails`, `Requirement`, `JobRequirements`, `FitAssessment`,
  `TrackerEntry`, `Memory`, `Profile` (FR-14 AC1; no name/e-mail/phone/
  address field, FR-14 AC3 - checked by a dedicated test). 17 tests,
  100 % coverage.
- `src/job_hunt_agent/pii.py` (FR-22): `clean_ad_text` masks e-mail
  addresses and context-gated phone numbers, drops the five D-3 name
  patterns (inline "bei Frau X", signature line, name before a phone
  number, "Ihr Ansprechpartner: Herr X", name + address block). 18 tests
  with synthetic examples only (CLAUDE.md invariant 4), incl. the two D-1
  reference-number regression cases staying unchanged. `spikes/pii_check.py`
  ran it over all 40 raw D-1 listings: **0 remaining contact names**
  (`spikes/NOTES.md` § "D-8 preparation"; per-listing detail in the
  gitignored `spikes/fixtures/pii_check.json`).
- `scripts/build_fixtures.py` (FR-19, D-3): builds
  `data/samples/fixtures/listings.json` from the 40 raw listings (cleaned
  with `pii.py`, referenznummer taken from the file name - not the
  details JSON - to avoid the D-1 corruption) plus 3 crafted listings
  (prompt injection for S5, a short external-URL teaser, one
  temporary-agency listing). 43 listings, 0 PII, 0 corrupted reference
  numbers (spot-checked; `tests/test_fixtures.py` written but not yet
  wired to run in CI - see decision D-8).
- `src/job_hunt_agent/ba_client.py` (FR-02, FR-04, FR-19 AC1, spec §8):
  `BAClient` (v6 search, v4 details, spec §8's one retry after 2 s on
  timeout/429/5xx, no caching of failures, success-only per-session cache
  for details), `sanitize_keywords` (FR-02 AC7), `FixtureSource` with the
  same two-method interface for demo mode. 30 tests with
  `httpx.MockTransport`, response shapes from `spikes/NOTES.md` § D-1;
  never calls the real API. 96 % coverage.
- `src/job_hunt_agent/rubric.py` (FR-06, spec §7): `hard_exclusions` and
  `assess`, weights/thresholds as named constants. 40 tests covering every
  §7 verdict bucket and FR-06 AC1-AC4 (incl. "missing value never
  excludes"). Applied to the 5 D-4-extracted listings (gpt-5-mini, run 1)
  with the demo profile - see decision D-9 for the per-listing results and
  a finding worth flagging: gpt-5-mini flagged `required: true` on 0 of 5
  listings' skills except one, which makes the heaviest-weighted (Skills)
  dimension `unknown` on 4 of 5 real listings under a literal §7 reading.
- `data/samples/profile_alex.yaml`: fictional demo profile (persona §3.1).
- `docs/prompts/WP-02-data-layer.md`: the work-package prompt, saved
  verbatim per CLAUDE.md's hand-over rule.

**Checks:** `uv run pytest` 124/124 passed, 98 % coverage on
`job_hunt_agent` (the two files with <100 % have only defensive/edge
branches uncovered - `ba_client.py` 96 %, `rubric.py` 99 %); `uv run ruff
check .` and `uv run ruff format --check .` clean; `uv run mypy src` clean
(`app.py`/`pages/` do not exist yet, so the full `mypy src app.py pages`
command from CLAUDE.md cannot run until a later work package).

**Decision files, status:** both **decided by Ingo on 2026-11-06**
(*Decision:* lines in the files):

- **D-8 (fixture content):** Option 1 - commit the cleaned real 43-listing
  fixture set as built. Applied: removed the working-tree-only
  `data/samples/fixtures/` line from `.gitignore`; `listings.json` and
  `tests/test_fixtures.py` (its `skipif` guard dropped - the file always
  exists now) are ready to commit together.
- **D-9 (rubric start values):** my recommendation, in full - Skills
  dimension now counts every extracted skill, not only ones flagged
  `required: true` (`_skills_verdict` in `rubric.py` changed, docstring
  references D-9); weights/thresholds, substring skill matching and the
  demo profile stay as shipped. `tests/test_rubric.py` updated: the old
  "no required skills -> unknown" test is replaced by "empty skills list
  -> unknown" plus a new test for the counts-non-required-skills case.

**Checks after applying both decisions:** `uv run pytest` 125/125 passed
(fixture tests now run for real, no longer skip), 98 % coverage; ruff and
mypy still clean.

**Next:** show the commit proposal(s) for this work package (one concern
per commit, per CLAUDE.md) and wait for Ingo's approval before any commit,
push or PR.
