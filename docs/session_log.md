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

## 2026-11-06 — WP-03: agent layer (the core journey on the console)

**Done** (branch `feature/agent-layer`, nothing committed yet - see
"Status" below):

- **Step 1 (D-9 skill matching fix):** `rubric.skill_matches_profile`
  changed from plain substring to whole-word matching
  (`(?<!\w)...(?!\w)` lookarounds - plain `\b` fails on `C#`/`C++`).
  Fixes real false positives ("Java" in "JavaScript", "C" in "CI/CD", "R"
  in "Docker"). Re-ran the 5 D-4 listings: **no category changed**
  (addendum in `docs/decisions/D-9-rubric-start-values.md`).
- **Step 2:** `src/job_hunt_agent/state.py` (`JobHuntState`, spec §5.3,
  plus one documented addition - `summaries` cache, needed because
  `distance_km` only exists on `JobSummary`, never `JobDetails`).
  `src/job_hunt_agent/storage.py`: shared SQLite connection
  (`isolation_level=None` - needed so `SqliteStore.setup()`'s bare
  `INSERT` doesn't leave an implicit transaction open and break its own
  later `BEGIN`), `profiles`/`tracker` tables with upsert, `SqliteSaver`
  and `SqliteStore` on the same connection (D-5, D-6).
- **Step 3:** `tools/search.py`, `tools/details.py`, `tools/assess.py`,
  `tools/tracker.py`, `tools/memory.py` (FR-02, FR-04, FR-05, FR-09,
  FR-15). `context.py` (`AgentContext`: job source, profile, extraction
  model, connection - injected at invoke time). `ba_client.py` gained a
  `JobSource` protocol and a `BAForbiddenError` subclass (403 gets its own
  §8 message). `prompts/extract_requirements.md`. **D-10 written**
  (demo-mode search can never exceed ~6 results, so the ">50, narrow"
  refinement direction cannot be shown in demo mode - confirmed by
  measurement, not just the WP's prediction).
- **Step 4:** `middleware/input_guard.py`, `middleware/limits.py`
  (built-in `ModelCallLimitMiddleware` + an own counter-reset middleware -
  the `search_jobs` limit itself is enforced in the tool, reading/writing
  the §5.3-named `search_calls_this_turn` field), `middleware/
  rejection_lock.py` (ported from spike D-5), `middleware/tool_errors.py`,
  `middleware/pii_guard.py` (built-in email detector + a custom phone
  detector reusing `pii.py`'s own context-gated regexes). `prompts/
  system.md`. `agent.py` (`build_agent`): assembles all of the above in
  the §5.4 order (rejection lock listed after HITL). **Known, documented
  gap:** FR-15 AC2 (loading stored memories into context at thread start)
  is not wired - none of this WP's demo scenarios need it; noted in
  `agent.py`'s own docstring, not hidden.
- **Step 5:** 204 tests total (112 new this session) across
  `tests/test_tools_*.py`, `tests/test_middleware*.py`, `tests/test_agent.py`,
  `tests/test_build_agent.py`, `tests/test_storage.py`; `tests/conftest.py`
  holds the shared `ScriptedModel` + agent-building helper (same pattern
  as `spikes/hitl_app.py`). Covers: tool contracts, clamping, keyword
  sanitising, `seen_refs`, the 8-listing limit, the verbatim-evidence
  check, tracker upsert idempotence, the rejection lock, the search limit
  per message, the input guard, PII redaction on tool results (incl. the
  D-1 reference-number regression, re-checked here), approval required
  for both write tools, and resume-after-restart from the checkpointer.
- **Step 6 (real model, live BA API):** `scripts/run_core_journey.py` ran
  S1/S2/S3/S4/S6 in one thread against the real model and the live API.
  **Found and fixed a real bug this run exposed, invisible to every
  scripted-model test:** `runtime: ToolRuntime[...] | None = None` on
  every tool silently defeated the framework's injected-argument
  detection, so `runtime` stayed in the JSON schema sent to the real
  `ChatOpenAI.bind_tools()` and the very first live call failed outright.
  Fixed by making `runtime` a required, keyword-only parameter with no
  default (the documented pattern) on all five tools. After the fix, the
  full run passed: S1 (30.6 s, well inside the 60 s NFR-03 budget, no D-11
  needed), S2 answered from state with zero new tool calls, S3 saved only
  after approval (verified directly against the SQLite file, not just the
  model's own words), S4's rejected `remember` call never persisted
  (verified the same way), S6 refused the off-topic question without a
  tool call. **S1 did not show refinement this run** (one `search_jobs`
  call; the real total apparently did not cross either threshold) - flagged
  honestly in `spikes/NOTES.md`, not glossed over; a follow-up run with a
  deliberately broad query is needed before relying on S1 as the
  refinement demo for the review. A script bug (cumulative instead of
  per-turn tool-call/token recording) was found, fixed in the script, and
  the one real run's artifacts were corrected post-hoc by diffing (exact,
  not a re-run) rather than spending more real calls.

**Checks:** `uv run pytest` 204/204 passed, 98 % coverage; `uv run ruff
check .` / `ruff format --check .` clean; `uv run mypy src/job_hunt_agent/`
and `mypy scripts/run_core_journey.py` clean (`app.py`/`pages/` still don't
exist, so the full CLAUDE.md `mypy src app.py pages` command still can't
run as written).

**Decision files, status:**

- **D-10 (demo search semantics): decided by Ingo on 2026-11-06, Option 4**
  (not one of my three drafted options) - `FixtureSource` replays the 5
  recorded D-1 search responses: for a query that exactly matches one of
  them, report the *real* recorded `maxErgebnisse` and return whichever of
  its referenced listings exist in the committed set; every other query
  still falls back to the normal keyword filter. Implemented:
  `scripts/build_fixtures.py::build_recorded_searches()` now also writes
  `data/samples/fixtures/recorded_searches.json` (query params + total +
  reference numbers only, no ad text); `ba_client.FixtureSource` tries an
  exact match before falling back (`_recorded_match`); 4 new tests in
  `tests/test_ba_client.py`, 4 new in `tests/test_fixtures.py`. Re-ran S1
  in demo mode with "Softwareentwickler" / München (D-1's real recorded
  total: 103): the agent correctly recognised ">50" and, across a two-turn
  conversation, tried two narrower re-searches with different keywords and
  a widened publication window - found 0 results for the narrowed query
  (an honest, separate limitation of the fixture search's simple
  AND-of-terms keyword matching, not a replay defect) but the refinement
  behaviour itself fired exactly as FR-03 AC1/AC3 describe. Full trace:
  `spikes/NOTES.md` § "D-10 Option 4 follow-up".
- **D-11 (latency):** not written - S1 took 30.6 s against the real model,
  inside the 60 s budget. Nothing to decide here this session.

**Checks after D-10:** `uv run pytest` 208/208 passed, 98 % coverage; ruff
and mypy still clean.

**D-10 addendum (decided by Ingo on 2026-11-06), before any commit:**

1. **Corrupted referenznummern in `recorded_searches.json`:** 3 of the
   entries were corrupted (same D-1 phone-regex regression, but inside the
   raw *search* responses this time, not just the details ones -
   `19522-0068291613-S` -> `19522-[TELEFON]-S` and 2 others). Fixed:
   `scripts/build_fixtures.py::recover_referenznummer()` never trusts a
   referenznummer from the scrubbed search file - matches it against
   `listings.json` instead (exact for an uncorrupted one, prefix/suffix
   around `[TELEFON]` for a corrupted one, dropped if ambiguous or never
   detail-fetched). New tests: `test_recorded_search_referenznummern_exist_in_listings_and_are_uncorrupted`
   plus 6 unit tests in the new `tests/test_build_fixtures.py`.
2. **Autonomous narrowing (FR-03 AC1):** `prompts/system.md` now tells the
   model to narrow *on its own* using the profile before asking the user.
   This needed the profile to actually reach the model - new middleware
   `middleware/profile_context.py` (`LoadProfileContextMiddleware`)
   injects it once, on a thread's first model call, wired into `agent.py`
   right after the input guard. `ba_client.FixtureSource` gained
   `_narrows_recorded_query`: a query that keeps a recorded query's
   keywords as a subset (same location, radius/age same or smaller) is
   restricted to *that specific recorded search's* own referenznummern
   (intersected with `listings.json`), not the full 43-listing set -
   honestly 0 if there is no overlap. 5 new tests in `tests/test_ba_client.py`,
   3 new in `tests/test_middleware_profile_context.py`.
3. **Re-ran S1 in demo mode, "Softwareentwickler" / München, real model**
   (`eval/results/d10_addendum_verification.json`, full trace in
   `spikes/NOTES.md` § "D-10 addendum"): the agent narrowed autonomously
   across 2 attempts using the profile's skills and seniority, within the
   3-call limit, without asking first - then stopped and correctly
   diagnosed that the Hamburg-based profile wasn't helping a München
   query. Both narrowed searches returned 0; **the trace does not reach
   "details -> assess_fit"** for this specific query. Confirmed honest,
   not a bug: München's recorded search has zero overlap between its own
   25 referenznummern and the 40 detail-fetched listings in
   `listings.json` (the D-1 spike's fetch budget was spent on the other 4
   searches first). The mechanism itself works exactly as specified;
   "AI Engineer"/Hamburg (24 of its listings are in the committed set) is
   the better candidate if a guaranteed non-zero narrow-to-assess demo is
   wanted for the review.

**Checks after the addendum:** `uv run pytest` 227/227 passed, 98 %
coverage; ruff and mypy still clean.

**D-10 follow-up 2 (decided by Ingo on 2026-11-06): close the München data
gap**, rather than switching the demo to a different query.

1. **Fetched real München listing data.** `spikes/fetch_muenchen_details.py`
   (new) fetched v4 details for all 25 referenznummern of the recorded
   "Softwareentwickler"/München search from the live BA API directly - one
   run, polite pacing, deliberately *not* reusing the D-1 spike's own
   `scrub()` (the function that caused the referenznummer corruption bug
   in the first place) - raw responses saved unscrubbed, cleaned properly
   later via `pii.py`. 22 of 25 saved; 3 already 404 (expired since the
   D-1 search, one day earlier). `scripts/build_fixtures.py` picked them
   up automatically (65 listings total now); `recorded_searches.json`'s
   München entry references all 22 (was 0).
2. **Found and fixed a lossy referenznummer bug, pre-dating this
   session.** `build_listing_from_details` derived `referenznummer` from
   the details file's *name*, a one-way slug where `_` and `/` both
   collapse to `-` - silently wrong for any reference number containing
   either character (4 of the original 40 listings, 8 of the 22 new
   ones). Fixed to read the field directly from the details JSON (correct
   for everything except the 3 phone-regex-corrupted entries, which still
   use the file name as before). Also improved the other 4 recorded
   searches' own reference coverage (e.g. AI Engineer/Hamburg 24 -> 25).
3. **Found and fixed a real PII leak, pre-dating this session.**
   `spikes/pii_check.py` flagged 2 of the 22 new München listings with a
   real name surviving cleaning (`Herr Salmen`, `Frau Stefanie Ruf`) -
   `pii.py`'s `INLINE_NAME_PATTERN` only matched `bei Frau/Herrn <Name>`
   (D-3 pattern 1), and neither sentence used "bei". Fixed by dropping
   that requirement; re-ran `pii_check.py` - 0 flagged across all 62
   listings now. New test: `tests/test_pii.py::test_inline_name_not_preceded_by_bei_is_still_masked`.
4. **`FixtureSource`'s narrowing path now also checks each candidate's
   description**, not just title/employer, scoped to narrowing only (the
   model's narrowed keywords are more likely to only appear in the ad
   body). New test: `tests/test_ba_client.py::test_fixture_source_narrowing_matches_a_term_only_present_in_the_description`.
5. **Re-ran S1 in demo mode, "Softwareentwickler" / München, real model**
   (`eval/results/d10_followup2_verification.json`, full trace in
   `spikes/NOTES.md` § "D-10 follow-up 2"): search (103) -> narrowed
   search (honest 0, no München listing mentions Python) -> agent fell
   back to its own first search's results on its own -> `get_job_details`
   x6 -> `assess_fit` (6 listings) -> shortlist with fit categories
   `poor, poor, partial, poor, poor, partial`. **The full ">50, narrow,
   details, assess_fit" chain now runs end-to-end for this exact demo
   query** - the gap the previous addendum could only work around is
   closed. Elapsed 54.3 s (within the 60 s NFR-03 budget, no D-11
   needed). The agent's own conclusion was an honest negative: München's
   real market for plain "Softwareentwickler" is mostly .NET/C# and
   system-level contract roles, not a match for the Python/FastAPI/
   PostgreSQL profile used for the demo.
6. Decision recorded as Addendum 2 in `docs/decisions/D-10-demo-search-semantics.md`.

**Checks after follow-up 2:** `uv run pytest` 229/229 passed, 98 %
coverage; ruff and `ruff format --check` clean; `mypy src` clean (`app.py`/
`pages` do not exist yet - no UI work package yet).

**D-10 follow-up 3 (FR-22, found in the coach review): fix a `pii.py`
over-removal bug**, before any commit.

1. **Root cause.** `CONTACT_MARKER_PATTERN` matched "Kontakt"/
   "Ansprechpartner" *anywhere* in a line via `search`, not just a
   heading - a requirement bullet like "Enger Kontakt mit den technischen
   Produktverantwortlichen..." opened a "contact block" that ran to the
   end of the ad. Measured on the 40 raw D-1 listings: 5 lost 50-91 % of
   their text, one lost 19 %.
2. **Fix.** New `CONTACT_HEADING_PATTERN`: only matches a heading-like
   line - anchored at the line start, after an optional markdown
   decoration (`#`, `*`/`**`/`***`, `_`/`__`/`___`) and an optional
   "Ihr(e)"/"Dein(:e)" possessive, length-capped at 90 characters. The
   dropped block is bounded (`CONTACT_BLOCK_MAX_LINES = 6`), ends at the
   first blank line, the next markdown heading, or a continuation line
   too long to be a contact-block entry (`CONTACT_BLOCK_LINE_MAX_LENGTH`) -
   one leading blank right after the heading is skipped rather than
   ending the block immediately (matches common "## Kontakt\n\n<block>"
   spacing). 6 new tests in `tests/test_pii.py`, including
   "Enger Kontakt mit ..." and "im direkten Kontakt mit Kunden" staying.
3. **`spikes/pii_check.py` extended** to report each listing's
   removed-text share and flag anything above 10 %, separating a
   legitimate bounded contact-block drop (counterfactual: share without
   dropping any contact block) from genuine unexplained over-removal.
4. **Found and fixed 2 more real PII leaks and 1 new over-removal
   regression** while re-running the extended check - all introduced or
   exposed by shapes the five D-3 patterns didn't cover:
   - `**Ansprechpartner: <Name>, Tel: [TELEFON], Mobil: [TELEFON]**`
     (markdown-bold, not caught because `**` wasn't an allowed leading
     decoration before).
   - `**ANSPRECHPARTNER FÜR FACHLICHE FRAGEN**` followed, after one blank
     line, by two bare `<Name>, <role>, Tel. <nr>` lines - not caught by
     any D-3 pattern; needed both the `**` decoration fix and the
     "skip one leading blank" change.
   - Regression: `"Dein Kontakt für diese Stelle ist: <Name>"` directly
     followed (no blank line) by a differently-styled subsection and 6
     full-sentence requirement bullets - swallowed by the line-count
     budget alone (17 % removed). Fixed by the continuation-line length
     cap. New test:
     `tests/test_pii.py::test_contact_block_does_not_swallow_the_next_unseparated_section`.
5. **Final numbers** (62 listings): 0 listings above 10 % removed
   (neither explained-by-block nor unexplained); `pii_check.py` still
   flags 7 lines by its plain keyword search, all manually verified as
   benign ("Enger Kontakt mit...", "...als führender Ansprechpartner...",
   etc. - ordinary vocabulary, no name attached). **0 real names leaked.**
6. **Re-ran S1 in demo mode** after rebuilding the fixtures: same full
   chain as before (search 103 -> narrowed 0 -> a third, age-widened
   search, also 0 -> `get_job_details` x6 -> `assess_fit` -> shortlist),
   56.2 s. **Fit categories for the 6 assessed listings did not change**
   (`poor, poor, partial, poor, poor, partial`, identical to follow-up 2)
   even though 2 of the 6 listings' description text changed
   substantively (the name leak fix, the requirement-bullet restoration) -
   neither change overlapped with the profile's skills, so the
   code-computed category was unaffected either way. Full trace:
   `eval/results/d10_followup3_verification.json`, write-up in
   `spikes/NOTES.md` § "D-10 follow-up 3".

**Checks after follow-up 3:** `uv run pytest` 233/233 passed, 98 %
coverage; ruff, `ruff format --check` and `mypy src` clean.

**Next:** show the commit proposal(s) for this work package (one concern
per commit, per CLAUDE.md) and wait for approval before any commit, push
or PR. After that, the remaining Must items per spec §13 (tracker view,
demo mode wiring into `app.py`, developer settings, FR-15 AC2's
memory-loading gap, safety tests, evaluation) and then the Streamlit UI
itself.
