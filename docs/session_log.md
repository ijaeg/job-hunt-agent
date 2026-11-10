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

## 2026-11-09 — WP-04: Streamlit UI for the core journey

**Done** (branch `feature/streamlit-core-ui`, nothing committed yet - see
"Status" below):

- **Data checks first (CLAUDE.md "Checks before hand-over" #4):**
  1. Confirmed FR-07 AC1's gap by reading `tools/assess.py`/`rubric.py`/
     `state.py`: `FitAssessment.matches`/`gaps` hold only
     `"name — evidence_en"` strings (`rubric.py:327-336`); the German
     `evidence_de` quote is built and consumed entirely inside
     `assess_fit`'s local scope and never reaches `JobHuntState`.
     **`docs/decisions/D-11-card-evidence.md` written** (3 options) and
     that part stopped per the work package's own instruction - cards
     built with English evidence only, German quote marked
     `# TODO(D-11)` in `ui_view.py`. **Decided by Ingo on 2026-11-09:
     Option 1** (structured `matches`/`gaps` on `FitAssessment`, built by
     `rubric.assess()`), to be implemented in WP-05 - not started here.
  2. Checked every `state["shortlist"]` ref has a cached summary: true
     for every real run inspected (the model only ever calls `assess_fit`
     on refs it got from its own `search_jobs` calls), but nothing in the
     code *enforces* this - `ui_view.build_card` falls back to the
     referenznummer as the title and leaves employer/location/etc. `None`
     if a summary is ever missing (FR-06 AC3 "missing value never
     excludes" spirit), covered by
     `test_build_card_falls_back_gracefully_without_a_summary`.
  3. No existing BA listing URL builder - `tools/tracker.py` explicitly
     left `url=None` ("the public BA jobsuche web URL scheme is
     unverified... a later UI work package's concern"). Built
     `ui_view.listing_url` (`https://www.arbeitsagentur.de/jobsuche/
     jobdetail/{referenznummer}`), documented as unverified against a
     real response (D-1 only exercised the JSON API).
  4. Demo-run query confirmed: **"Softwareentwickler" / München, radius
     25 km, published within 28 days** (`data/samples/fixtures/
     recorded_searches.json`, real recorded total 103) - triggers
     autonomous narrowing (>50) end-to-end, already proven in WP-03's
     D-10 follow-ups and re-confirmed by this work package's own
     real-model smoke run.
- **`src/job_hunt_agent/llm.py`:** `build_real_model()` moved out of
  `scripts/run_core_journey.py` (no duplicate); the script now imports it.
  Renumbered that script's dormant latency-decision placeholder from
  `D-11-latency.md` to `D-12-latency.md` (D-11 is now card-evidence) -
  never triggered so far (S1 stayed under the NFR-03 budget in every
  WP-03 run), but would have collided with D-11 if it ever fired.
- **`src/job_hunt_agent/ui_view.py`:** pure card-building helpers (no
  Streamlit, no LLM/network call, mirrors `rubric.py`/`pii.py`):
  `listing_url`, `low_evidence_note` (FR-07 AC4), `build_card`/
  `build_cards` (FR-07 AC1), `order_cards` (strong -> partial -> poor,
  excluded separate, FR-07 AC2). 8 unit tests, 100 % coverage.
- **`app.py`** (repo root, `uv run streamlit run app.py`): layout and
  wiring only (NFR-04) - one shared SQLite connection via
  `st.cache_resource` keyed by db path (D-5, FR-10 AC5); profile seeded
  from `data/samples/profile_alex.yaml` on first use (FR-14 AC1); thread
  id kept in `st.query_params`, "New search" button starts a new one
  (FR-16 AC3); demo-mode toggle (default on) switches `FixtureSource` vs.
  `BAClient` with a "Demo data – not live listings" banner (FR-19 AC1,
  AC2); chat (left) + shortlist cards (right), history read from
  `agent.get_state(cfg).values["messages"]`, never session state (FR-01
  AC1) - the `profile_context`-named message `LoadProfileContextMiddleware`
  injects is filtered out of the chat view (it is context for the model,
  not something the user said); progress labels via
  `agent.stream(..., stream_mode="updates")` in `st.status` (FR-16 AC2);
  "Save to tracker" button per card sends a chat message naming the
  listing (FR-07 AC3); approval read from `agent.get_state(cfg).interrupts`
  with Approve/Edit/Reject buttons per pending action, Edit revealing a
  form (`save_to_tracker`: status/follow_up_date/note;
  `remember`: kind/value) with its own "Save edited action" button,
  resuming with `Command(resume={"decisions": [...]})` (FR-10 AC2, AC5);
  every `agent.stream`/`agent.invoke` call wrapped so a failure becomes a
  friendly `st.error`, never a stack trace (invariant 7). A small
  `_ScriptedModel` (gated by `JOB_HUNT_FAKE_MODEL=1`, never active
  otherwise) mirrors `spikes/hitl_app.py`'s pattern for tests, referenced
  rather than imported per the work package's instruction.
- **`scripts/ui_smoke_wp04.py`:** headless real-model smoke script (not a
  pytest test), reusing `app.py`'s own `iter_new_tool_calls`/
  `_status_label` so the recorded behaviour matches what the UI actually
  shows.
- **Tests:** `tests/test_ui_view.py` (8), `tests/test_llm.py` (2),
  `tests/test_app.py` (7, `streamlit.testing.v1.AppTest` +
  `JOB_HUNT_FAKE_MODEL=1` + `FixtureSource`, no network/API key) - cards
  render strong/partial/poor/excluded-separate; a save request raises the
  approval with exact arguments; approve writes the tracker row (checked
  directly against SQLite); reject writes nothing; an edit decision's
  edited arguments reach the tracker row; a brand-new `AppTest` on the
  same DB file/thread id (`storage.get_connection.cache_clear()` +
  `app.get_connection.clear()`, mirroring `spikes/test_hitl_app.py`)
  still shows the pending interrupt and the history after a simulated
  restart; a focused unit test reproducing the `stream_mode="updates"`
  duplicate-echo bug below.
- **Bug found in coach review, fixed before any commit:** the first
  real-model smoke run's tool-call/status-label counting was wrong -
  several middleware `before_model` hooks (the built-in `PIIMiddleware`
  in particular) return an update carrying the *whole* `messages` list,
  not just what changed, so the same `AIMessage`/tool-call `id` is
  re-emitted across several `stream_mode="updates"` steps. The first run's
  naive loop counted every occurrence, making the real 3-call sequence
  (`search_jobs, search_jobs, assess_fit`) look like 6 - checked against
  the checkpointer's actual message history, which had only 3 unique tool
  call ids. Fixed with a shared `app.iter_new_tool_calls` helper (dedup by
  `tool_call["id"]`) used by both `app.py::run_turn` and
  `scripts/ui_smoke_wp04.py`; unit-tested directly.
- **Approval UI redesigned in coach review:** FR-10 AC2 asks for three
  buttons (Approve/Edit/Reject), not a selectbox + a separate "Submit"
  button. `render_approval` now renders those three buttons per pending
  action request; Edit reveals the argument form with its own "Save
  edited action" button. Supports a batch of more than one pending
  action request (tracked in `st.session_state["_pending_decisions"]`,
  cleared the moment every request in the current interrupt has a
  decision and the resume is sent) even though the core journey only
  ever proposes one write tool per turn in practice.

**Real-model smoke run** (Checks #2, `scripts/ui_smoke_wp04.py`, demo
query "Find Softwareentwickler jobs in München.", full record
`eval/results/ui_smoke_wp04.json`, write-up `spikes/NOTES.md` § "WP-04 UI
smoke run"): **65.8 s - exceeds the 60 s NFR-03 budget.** Tool sequence
`search_jobs, search_jobs, get_job_details` x6, `assess_fit` (each call
counted once, after the dedup fix); 9 status labels for 9 real tool
calls. Card count: 6 visible (2 partial, 4 poor), 0 excluded. Reported as
instructed, nothing tuned to bring it under budget -
`run_core_journey.py`'s own `D-12-latency.md` auto-write is scoped to its
own S1 scenario, not this script, so no decision file was written here;
flagged to Ingo for a call on whether a decision is warranted (a first,
buggy-count run of the same query had measured 56.4 s with a different
tool sequence - run-to-run model variance, not something the counting fix
caused).

**Checks:** `uv run pytest` 250/250 passed, 98 % coverage (no skipped
tests); `uv run ruff check .` and `uv run ruff format --check .` clean;
`uv run mypy src app.py scripts` clean (`pages/` still doesn't exist - a
later work package). No fixture/evaluation-set changes this work package,
so CLAUDE.md check #3 (data integrity) does not apply.

**Decision files, status:**

- **D-11 (card evidence): decided by Ingo on 2026-11-09, Option 1**
  (structured `matches`/`gaps` on `FitAssessment`, built by
  `rubric.assess()` directly from `requirements.skills`) - to be
  implemented in **WP-05**, not this one; `ui_view.py` still carries the
  `# TODO(D-11)` marker on the English-only `matches` field.
- **D-12 (latency):** reserved (renumbered from the former dormant
  `run_core_journey.py` placeholder), not written as a decision file this
  session - the 65.8 s NFR-03 overage above is reported, not decided on,
  pending Ingo's call.

**Next:** show the commit proposal(s) for this work package (one concern
per commit, per CLAUDE.md) and wait for approval before any commit, push
or PR. After that: WP-05 (D-11 Option 1 implementation) and the remaining
Must items per spec §13 (tracker view, memory page, profile form,
developer settings, FR-15 AC2's memory-loading gap, safety tests,
evaluation).

## WP-05: German evidence on the cards (D-11) and S1 latency measurement (D-12) - 2026-11-09

Prompt: `docs/prompts/WP-05-evidence-and-latency.md`. Branch
`feature/evidence-and-latency`.

**Part A, D-11 Option 1 (decided 2026-11-09, Ingo):** `models.py` gets a new
`MatchEvidence` model (`name`, `evidence_de`, `evidence_en`);
`FitAssessment.matches`/`gaps` change from `list[str]` to
`list[MatchEvidence]` (FR-05 AC4, spec §6.3). `rubric.assess()` builds them
directly from `requirements.skills`, carrying both the German quote and the
English translation instead of the old `"name — evidence_en"` string.
`ui_view.CardData.matches`/`gaps` follow the same type; `app.py::render_card`
now shows the German quote and the English translation for both (FR-07
AC1); the `# TODO(D-11)` marker is gone.

Consumers found and updated: `models.py`, `rubric.py`, `ui_view.py`,
`app.py`, `tests/test_rubric.py`, `tests/test_ui_view.py`, `tests/
test_app.py`. Not affected: `prompts/system.md` (refers to "the evidence
quote" generically, no shape dependency), `prompts/extract_requirements.md`
(extracts `Requirement.evidence_de`/`evidence_en`, which this change reads
from unchanged), `state.py` (never held `matches`/`gaps` directly).
`tests/test_tools_assess.py` needed no change (asserts only `len(...
["assessed"])`, not match content).

**Old checkpoints under `data/*.sqlite`:** confirmed by loading each with
`agent.get_state()` and then `ui_view.build_cards()` + the new `app.py`
rendering code - the LangGraph checkpointer deserializes old `FitAssessment`
objects without validating field types (`matches` stays a bare
`list[str]`), so `get_state()` itself doesn't raise, but `render_card`'s new
`match.name`/`match.evidence_de` access then crashes with
`AttributeError: 'str' object has no attribute 'name'` - a real stack trace
in the UI (would violate invariant 7) for any old thread. Affected:
`data/ui_smoke_wp04.sqlite`, `data/job_hunt_agent.sqlite`,
`data/core_journey_run.sqlite` (all three gitignored, never committed, local
dev data only). No migration code written, per the prompt's instruction;
proposed to Ingo for deletion rather than decided unilaterally.

**Spec §6.3 wording proposed for the coach to apply** (not edited in
`PRODUCT_SPEC.md` directly, per CLAUDE.md):

```text
MatchEvidence
├── name: str
├── evidence_de: str                     (verbatim quote from the ad)
└── evidence_en: str                     (English translation)

FitAssessment
├── referenznummer: str
├── category: "strong" | "partial" | "poor" | "excluded"
├── exclusion_reasons: list[str]
├── matches: list[MatchEvidence]
├── gaps: list[MatchEvidence]
├── unknown: list[str]                   ("not mentioned in the ad")
├── low_evidence: bool
└── rubric: dict[str, str]               (per dimension: met / partly / not_met / unknown)
```

**Real-model check (Checks #2), S1 then S2:** `scripts/s1_s2_check.py`
(new), demo mode, real model. Record: `eval/results/wp05_s1_s2.json`. S1
("Find Softwareentwickler jobs in München.") produced 5 cards (1 partial, 4
poor); S2 ("Why is #3 only partial?") was answered with **no new tool
call** and cited the German evidence quotes for the skills and language
gaps verbatim (FR-08 AC1, AC2) - confirms the structured evidence survives
from `assess_fit` into a follow-up answer. (A first attempt on a fresh
thread didn't search at all - the model treated the profile's `location:
Hamburg` as a hard search boundary for a München query and asked which
location to use instead; re-run on a new thread to get a completed S1 to
test S2 against - the same behaviour recurs in Part B below, so it is
reported there rather than treated as a one-off.)

**Part B, D-12 Option 1 (decided 2026-11-09, Ingo):** `scripts/
ui_smoke_wp04.py` gets a `--runs N` option (`run_s1_once`,
`run_latency_measurement`, sharing `_build_context` with the existing
single-run path - no duplicated logic) that runs S1 on N fresh threads and
records elapsed seconds, deduplicated tool sequence, `assess_fit`
extraction seconds, listings assessed, card count and token usage per run,
plus median/mean/min/max. 5 runs, demo mode, real model, config unchanged:
`eval/results/latency_s1_wp05.json`, written up in `spikes/NOTES.md` § "WP-05
S1 latency measurement" and in `docs/decisions/D-12-latency.md` § "Results
(WP-05)".

**S1 latency result:**
- All 5 runs: median **52.75 s**, mean 36.96 s, min 7.63 s, max **59.63
  s** - inside the 60 s NFR-03 budget.
- But only 3 of 5 ran the full pipeline to `assess_fit` (6 listings each);
  the other 2 stopped after one `search_jobs` call (0 listings assessed,
  7.6 s / 9.3 s) - the same location-mismatch clarification behaviour as
  the S1/S2 check's discarded first attempt.
- **3 completed runs only:** median 55.48 s, mean 55.95 s, min 52.75 s,
  max 59.63 s - still inside budget, but only 0.37 s under the ceiling on
  the worst run, and n=3 rather than the 5 planned.
- Neither reading crosses D-12's "median or max above 60 s" trigger, so no
  "Round 2 options" were added and nothing in `config.py`/`tools/
  assess.py`/the prompts was tuned, per the prompt's instruction.
  **Budget met: yes, on the numbers measured - flagged to Ingo given the
  thin margin and the completion-rate confound above.**

**Checks:** `uv run pytest` 252/252 passed, 98 % coverage (no skipped
tests); `uv run ruff check .` and `uv run ruff format --check .` clean;
`uv run mypy src app.py scripts` clean (31 source files). No
fixture/evaluation-set changes this work package, so CLAUDE.md check #3
(data integrity) does not apply.

**Decision files, status:**

- **D-11 (card evidence):** implemented this session per Ingo's
  2026-11-09 Option 1 decision.
- **D-12 (latency):** measured this session per Ingo's 2026-11-09 Option 1
  decision; results appended to the file, no lever changed (trigger not
  met).

**Open for Ingo:**
1. ~~Delete the stale local `data/*.sqlite` files~~ - done (Addendum 1 #5
   below); corrected: only 2 of the 3 files first listed here still held
   the old shape by the time of deletion (see Addendum 1 #5).
2. Apply the proposed spec §6.3 wording above to `PRODUCT_SPEC.md`.
3. ~~The S1 latency margin was thin (n=3, 0.37 s)~~ - superseded by the
   Addendum 1 re-measurement below (n=5, 1.56 s margin).

## WP-05 Addendum 1 (2026-11-09, after coach review)

Related: FR-01 AC4, FR-03 AC3, FR-08 AC2, NFR-03, D-12. Addendum text
appended to `docs/prompts/WP-05-evidence-and-latency.md`.

**#1 - FR-01 AC4 location override:** added one bullet to
`prompts/system.md`'s "Search and refinement" section - a location named
in the request overrides the profile's stored location for this search;
do not ask first. Real-model check: re-ran `scripts/s1_s2_check.py` on a
fresh thread - the model now searches München directly (3 `search_jobs`
calls, autonomous refinement, then 6 `get_job_details` + `assess_fit`),
no clarifying question. Confirmed again at scale by Addendum 1 #3's
5/5 completion rate below.

**#2 - tool-sequence recording:** `scripts/ui_smoke_wp04.py`'s latency
path previously collapsed the tool sequence to unique names, hiding
repeat `search_jobs` calls. Replaced with `_tool_sequence_of` (full
per-call sequence, deduplicated by `tool_call` id only); added
`search_jobs_calls` and `reached_assess_fit` per run.

**#3 - re-measured S1 latency (5 fresh-thread runs, post-fix):**
`eval/results/latency_s1_wp05.json` replaced; `docs/decisions/
D-12-latency.md` § "Results" and `spikes/NOTES.md` § "WP-05 Addendum 1:
location-override fix and re-measured S1 latency" updated.

- **Completion rate: 5/5 (100%).** No run stopped early this time.
- **Refinement rate: 5/5 (100%).** Every run made >1 `search_jobs` call.
- **Elapsed seconds: median 44.77 s, mean 47.16 s, min 36.19 s, max
  58.44 s** - both median and max inside the 60 s NFR-03 budget, on a
  clean 5/5-completion sample. **Budget met: yes.**

**#4 - FR-08 AC2 investigation (S2 explanation contradicts the computed
match):** the stored `FitAssessment` for `10001-1003863378-S` has Java
correctly in `matches` (two Java-named requirements matched the profile's
`Java` skill); the `skills` dimension's `not_met` verdict is a correct
*aggregate* (2 of 10 extracted requirements matched, 20% < the 40%
partial threshold, D-9), not a unanimous "nothing matched". The S2
explanation nonetheless calls Java part of a "skills mismatch" and both
times omits at least Java and `CI/CD` from its recollection of the
profile's 6 skills, instead of quoting the profile-context message's
`Skills:` line verbatim. **Rubric confirmed correct - not changed.**
Full write-up and a proposed (not yet applied) `prompts/system.md`
addition: `spikes/NOTES.md` § "WP-05 Addendum 1 #4". **Open for Ingo:**
apply the proposed wording, or hold for separate review.

**#5 - stale `data/*.sqlite` files, Ingo-approved deletion:** re-checked
each file's actual `FitAssessment` shape before deleting (not from the
earlier report, which was taken before this session's own smoke re-run
had already overwritten `ui_smoke_wp04.sqlite` with the new shape).
Confirmed old-shape (`matches` still a bare `list[str]`) in exactly two
files - `data/job_hunt_agent.sqlite` and `data/core_journey_run.sqlite`
- both deleted (plus their `-wal`/`-shm` siblings). `data/
ui_smoke_wp04.sqlite`, `data/s1_s2_check.sqlite` and `data/
latency_s1_wp05.sqlite` already held the new shape and were left alone.
All were gitignored, never committed, local dev data only;
`job_hunt_agent.sqlite` is also the Streamlit app's own default DB file
(`config.DB_PATH`), so its profile/tracker tables reset too - expected,
not flagged as a separate concern.

**Checks (after Addendum 1):** `uv run pytest` 252/252 passed, 98 %
coverage; `uv run ruff check .` and `uv run ruff format --check .` clean;
`uv run mypy src app.py scripts` clean (31 source files).

**Addendum 1 commits:** 5 commits made on `feature/evidence-and-latency`
after Ingo's "go ahead" (prompt+D-12; MatchEvidence+rubric+tests;
cards+UI tests; location-override fix; S1/S2 check+latency+NOTES+log).
Item 4's prompt fix left unapplied per the report, pending Ingo's call.

## WP-05 Addendum 2 (2026-11-09)

Related: FR-08 AC2, FR-20 AC1, D-9.

**#1 - Addendum 1 #4's proposed fix applied and re-checked, partial
success:** added the proposed wording to `prompts/system.md`'s
"Explaining the shortlist" section; re-ran `scripts/s1_s2_check.py` on a
fresh thread (`eval/results/wp05_s1_s2.json` replaced). Verified against
the stored `FitAssessment`, not the prose: the originally reported Java
contradiction is gone (Java now correctly listed under "What matched",
matching the stored `matches`; profile skills quoted in full this time).
**But a mirror-image instance of the same error class appeared in the
same answer:** a gap item (a merged, non-verbatim quote of two separate
`gaps` entries about relational databases/SQL) was presented as a match.
The applied wording only guards one direction ("never call a skill
listed in `matches` a mismatch"); it does not cover "never call a `gaps`
skill a match" or quote-fabrication. Full before/after detail:
`spikes/NOTES.md` § "WP-05 Addendum 2". **Not re-fixed this round** -
reported as found; open for Ingo to decide whether to extend the
instruction symmetrically in a future work package.

**#2 - FR-20 AC1 check, no bug found:** latency run 2's 4th recorded
`search_jobs` tool call (`data/latency_s1_wp05.sqlite`, thread
`latency-s1-wp05-2`) was checked directly against its `ToolMessage`:
`result: null`, `not_applicable_reason: "Maximum of 3 search_jobs calls
per message already reached..."` - the tool refused it, no 4th BA API
call was made. The limit holds exactly as specified; the "4 calls" count
in `spikes/NOTES.md`'s table was attempted calls, not executed searches
- wording corrected in place, no code change.

**Checks (after Addendum 2):** `uv run pytest` 252/252 passed, 98 %
coverage; `uv run ruff check .` and `uv run ruff format --check .` clean;
`uv run mypy src app.py scripts` clean.

**Next:** show the commit proposal for this addendum and wait for
approval before any commit, push or PR. After that: the remaining Must
items per spec §13 (tracker view, memory page, profile form, developer
settings, FR-15 AC2's memory-loading gap, safety tests, evaluation).

## 2026-11-09 — WP-06: tracker view (FR-11)

**Done:**

- Recorded D-13 (consistency of follow-up explanations, coach-prepared)
  and spec v0.1.8 in the first commit, together with
  `docs/prompts/WP-06-tracker-view.md`.
- Shared UI module `ui_shared.py` (repo root, no change in behaviour):
  `get_connection`, `USER_ID` and `load_or_seed_profile` moved out of
  `app.py`, which now imports them. Both `app.py` and the new
  `pages/1_Tracker.py` explicitly add the repo root to `sys.path` before
  importing it - needed because Streamlit's own "add the entry script's
  directory" trick keys off whichever script is actually executed
  (confirmed by reading `streamlit/runtime/scriptrunner/script_runner.py`
  and `local_script_runner.py`): the real app always runs that trick with
  `app.py`'s directory, but a page tested directly via
  `AppTest.from_file(...)` or a module loaded by raw `importlib` (as
  `tests/test_app.py`'s `_load_app_module` does) gets no such help.
- `storage.delete_tracker_entry(conn, user_id, referenznummer) -> bool`
  (FR-11 AC2), inside a transaction; returns whether a row actually
  existed.
- Pure helpers `src/job_hunt_agent/tracker_view.py` (FR-11 AC1, no
  Streamlit import, sibling to `ui_view.py` rather than added to it - a
  different FR, kept separate): `is_overdue(follow_up_date, today)` and
  `order_entries(entries, today)` (overdue first, then by `updated_at`,
  newest first); `today` is always a parameter, never read from the
  system clock inside the helper.
- `pages/1_Tracker.py` (FR-11 AC1, AC2): one row per tracker entry -
  title linked to the listing (reuses `ui_view.listing_url`, the same
  BA Jobsuche URL the shortlist cards use), employer, a status
  `st.selectbox` that saves immediately on change (via
  `save_tracker_entry` with a fresh `updated_at`, `created_at`
  untouched), the follow-up date highlighted in red with an "Overdue"
  label when in the past, the note, and a Delete button that requires a
  second click ("Yes, delete" / "Cancel") before anything is removed -
  no browser dialogs, no approval (these are user actions, FR-11 AC2,
  not agent ones). Empty state: a caption pointing back at the
  shortlist. Every storage call on this page is wrapped so a failure
  becomes `st.error`, never a stack trace (invariant 7).
- No `list_tracker` tool, no memory page, no profile form - out of
  scope per the prompt.

**Tests (NFR-05):** `tests/test_storage.py` (+3:
`test_delete_tracker_entry_removes_the_row`,
`test_delete_tracker_entry_returns_false_when_missing`,
`test_delete_tracker_entry_only_removes_the_given_user`),
`tests/test_tracker_view.py` (new, 7 tests on `is_overdue`/
`order_entries`), `tests/test_pages_tracker.py` (new, 6 `AppTest`
scenarios on a temp DB seeded via a `db_path` fixture mirroring
`test_app.py`'s: ordering + overdue marking, status change updates
SQLite and keeps `created_at`, delete requires a second click, delete
cancel keeps the row, empty state). `tests/test_app.py`'s 6 existing
scenarios needed no change and stayed green through the move.

**Checks:** `uv run pytest` 267/267 passed, no skipped, 98 % coverage
(up from 252 passed before this package; `job_hunt_agent/storage.py`,
`tracker_view.py` and `ui_view.py` now all at 100 %). `uv run ruff
check .` and `uv run ruff format --check .` clean (two import-order
fixes in `app.py`/`pages/1_Tracker.py` after the first pass). `uv run
mypy src app.py pages ui_shared.py scripts` clean, 34 source files. No
real-model run: this package changed no tool, prompt, middleware or the
agent - the tracker page never calls the agent at all.
- Manual smoke check performed here (no real browser tool connected in
  this session, so this is a partial substitute, done in addition to
  the `AppTest` suite, not instead of a real click-through): seeded a
  temp SQLite file with one overdue entry, started `uv run streamlit
  run app.py` against it, and confirmed both `/` and `/Tracker` return
  HTTP 200 with no error in the server log; stopped the server
  afterwards. Ingo's own manual check is still the "Done when" 4 steps
  below.

**Next:** show the commit proposal (prompt+D-13+spec; shared UI module
move; storage delete+helpers+tests; tracker page+AppTest+session log)
and wait for approval before any commit. After that: the remaining Must
items per spec §13 (memory page, profile form, developer settings,
FR-15 AC2's memory-loading gap, safety tests, evaluation).

## 2026-11-09 — WP-07: memory view and loading memories into new threads (FR-15 AC2, AC3)

**Check first (per the prompt):** read `tools/memory.py` (`remember`
writes `{kind, value, created_at}` to `("memories", user_id)` via
`ToolRuntime.store`), `middleware/profile_context.py` (the "inject once
on a thread's first model call" pattern to follow) and
`tools/assess.py`'s `_excluded_employers` (already reads the same
namespace live, inside `assess_fit`, for the FR-15 AC4 hard exclusion -
this already worked independently of AC2). `agent.py`'s own module
docstring already named the exact gap: the system prompt
(`prompts/system.md` §"Stored preferences") tells the model memories
"apply automatically" and are "shown to you at the start of this
thread," but nothing injected them. Employer picked from the data for
the real-model check: **bayoonet AG**, `12117-YF-48852-YF-S`, in D-10's
recorded München search (`data/samples/fixtures/recorded_searches.json`,
cross-checked against `listings.json`).

**Done:**

- `storage.list_memories(conn, user_id)` / `storage.delete_memory(conn,
  user_id, key)` (FR-15 AC3) on top of the store, so `pages/2_Memory.py`
  never calls the store API directly - mirrors D-6's own reasoning for
  the tracker (bare dicts, not a Pydantic model, since that's how
  `remember` already stores an item).
- `middleware/memory_context.py` (FR-15 AC2): a sibling of
  `LoadProfileContextMiddleware`, not an extension of it - memories come
  from `runtime.store`, keyed by `state["user_id"]`, a different source
  read at call time rather than build time. Wired into `agent.py`
  directly after `LoadProfileContextMiddleware` (both "inject once"
  middlewares grouped together, before the PII guards). No memories at
  all → no message (unlike the profile, always present once seeded).
- `pages/2_Memory.py` (FR-15 AC3): one row per item (kind, value, saved
  date), Delete with a second-click confirmation, same pattern as
  `pages/1_Tracker.py`. Empty state points back at the agent. Deleting an
  item takes effect on the next `assess_fit` call (FR-15 AC4 stays a
  live, code-only read from the store - the context message only lets
  the model *explain* the filtering, never decide it).

**Two real bugs found only by the real-model check, not by the mocked
unit tests - both fixed, both documented:**

1. **Middleware-ordering bug (caught by the real-model script):** the
   first version detected "first model call" as
   `len(state["messages"]) == 1`, copied from
   `LoadProfileContextMiddleware`. That middleware runs first in
   `agent.py`'s list and prepends its own message before this one's
   `before_model` ever executes, so by the time it ran, length was
   already 2 - the memory message silently never fired. Fixed by
   detecting "no `AIMessage` yet in this thread" instead (order-
   independent). Added a regression test running both middlewares
   together in `agent.py`'s real order
   (`test_load_memory_context_middleware_still_injects_after_profile_context_middleware`),
   since every other test exercised this middleware in isolation and
   none would have caught it.
2. **Shared-connection race (D-14, caught only once the first bug was
   fixed and the real-model script actually exercised the store on
   every turn):** with the fix above, calling the real agent started
   intermittently raising `sqlite3.OperationalError: cannot commit - no
   transaction is active` inside `SqliteStore`'s own commit - roughly 1
   run in 5-15 in a 40-60 iteration stress test of `build_agent`, never
   in a single demo-paced run (which is why it never showed up in the
   mocked test suite). Root cause: D-5's "one shared connection" has
   `SqliteSaver` and `SqliteStore` each wrapping bare `BEGIN`/`COMMIT`
   SQL around the *same* connection object, coordinated only by their
   own, mutually unaware internal lock; LangGraph's `ToolNode` runs tool
   calls on a worker thread, so this had always been racy, just never
   exercised on every turn before. A single retry looked promising but
   wasn't reliable (the retry itself failed in one stress-test run, and
   a separate tool-call path wasn't covered by it at all). Wrote
   `docs/decisions/D-14-store-connection-race.md`: giving the store its
   own `sqlite3.connect()` to the *same* file (found via `PRAGMA
   database_list` on the shared `conn`) scored 40/40 and 60/60 in two
   separate stress tests, with no call-site changes needed anywhere
   else. Implemented as the reasoned default per this project's
   established pattern (document the alternatives with real numbers,
   flag as open) - **Decision line still pending Ingo's answer.**
   `tools/assess.py`'s `_excluded_employers` (pre-existing, same store,
   same risk, just lower-frequency) now shares the new
   `storage.search_memories` helper and so gets the fix for free; its
   own `store.search(...)` call was also bumped from the store's default
   `limit=10` to the new `config.MAX_MEMORIES_PER_USER` (200) while
   touching this function, a one-line consistency fix for FR-15 AC4 at
   scale, not asked for by the prompt but directly adjacent to it.

**Tests (NFR-05):** `tests/test_storage.py` (+7:
`test_list_memories_returns_kind_value_and_created_at`,
`test_list_memories_orders_most_recently_saved_first`,
`test_list_memories_returns_empty_list_when_none_stored`,
`test_list_memories_isolates_per_user`,
`test_delete_memory_removes_the_item`,
`test_delete_memory_only_removes_the_given_user`,
`test_delete_memory_on_a_missing_key_does_not_raise`),
`tests/test_middleware_memory_context.py` (new, 6 tests: message
content, inject-once-with-memories, inject-nothing-without-memories,
no-repeat-on-a-later-turn, per-user isolation, and the ordering
regression test above), `tests/test_pages_memory.py` (new, 4 `AppTest`
scenarios mirroring `test_pages_tracker.py`: items render, delete with
confirmation, delete-cancel keeps the item, empty state).

**Checks:** `uv run pytest` 284/284 passed (267 before this package +
17 new), no skipped, 98% coverage, `storage.py`/`middleware/
memory_context.py` both 100%; re-ran the suite 3 more times back to
back with no flakes. `uv run ruff check .` and `uv run ruff format
--check .` clean. `uv run mypy src app.py pages ui_shared.py scripts`
clean, 37 source files.

**Real-model check (demo mode, two threads, one DB,
`eval/results/wp07_memory_check.json`):** thread 1 ("Never show me jobs
from bayoonet AG again.") called `remember`, paused for approval,
approved, stored. Thread 2 (new thread id, "Find Softwareentwickler
jobs in München.") did inject the `memory_context` message
(`thread_2_memory_context_message_injected: true`) and the model acted
on it *before* even trying the listing: it called `get_job_details` on
only 5 of the München refs, skipping bayoonet AG's entirely, and its own
final answer states "Excluded employer bayoonet AG was filtered out of
the assessed shortlist" (`thread_2_answer_mentions_exclusion: true`).
Because the model never passed that referenznummer to `assess_fit` this
run, the code-level hard-exclusion path (`"excluded by you: bayoonet
AG"`) wasn't exercised by *this* run -
`excluded_listing_marked_excluded_by_you: false` in the saved file - but
was independently confirmed during debugging (before the ordering fix,
when the model still fetched that listing): the rubric attached
`"excluded by you: bayoonet AG"` correctly. Both paths of FR-15 AC4
(model avoids it proactively, or code catches it if the model tries
anyway) are confirmed; only the first is in the committed JSON since
that is what the real run actually did.

**Manual browser check for Ingo (4 steps):** (1) start the app, tell the
agent "Never show me jobs from bayoonet AG again," approve the
`remember` call; (2) click "New search," ask for "Softwareentwickler
jobs in München"; (3) check that the shortlist/agent's answer does not
surface a bayoonet AG listing as a normal result; (4) open the Memory
page, confirm the "Excluded employer: bayoonet AG" row is there, delete
it with the two-click confirmation, and confirm it is gone.

**Next:** show the commit proposal and wait for approval before any
commit (prompt; storage functions + tests; memory middleware + agent
wiring + regression test; D-14 + the store-connection fix + its tests;
memory page + AppTest; real-model check + session log). D-14's Decision
line needs Ingo's answer. After that: profile form, developer settings,
safety tests, evaluation (§9) remain per spec §13.

## 2026-11-09 — WP-08: profile form, thread list and user selection

**Checked first (per the WP's "Check first"):** `SqliteSaver.delete_thread`
exists in the installed `langgraph-checkpoint-sqlite` 3.1.3 and works on
the shared `storage.get_connection` connection (verified directly: wrote
a checkpoint, called `delete_thread`, no error, consistent with D-5/D-14's
locking). Tracker, memories and the profile were already keyed by
`user_id` everywhere in `storage.py`, `tools/tracker.py`, `tools/memory.py`
and both context middlewares (they all read `state["user_id"]` or take a
`user_id` argument already) - the fixed `ui_shared.USER_ID = "alex"` was
the *only* place still assuming one user; no agent, tool or middleware
change was needed.

**Done (D-15, D-16, FR-13 AC2, FR-14, FR-01 AC4):**

- `storage.py`: new `threads` table (`user_id`, `thread_id`, `title`,
  `created_at`, `updated_at`); `touch_thread` (one upsert registers on the
  first call and only moves `updated_at` on every later one - so the UI
  layer can call it unconditionally on every turn), `list_threads`
  (newest-updated first), `delete_thread_record`; `list_users` (every
  user id with a stored profile, D-16).
- `src/job_hunt_agent/user_view.py` (new, no Streamlit/LLM/network import,
  CLAUDE.md architecture): `thread_title` (cuts to 60 chars, D-15),
  `validate_user_name`/`slugify_user_id` (D-16's name rule and slug
  derivation), `order_users` (alphabetical, case-insensitive).
- `ui_shared.py`: replaced the fixed `USER_ID` with `DEFAULT_USER_ID =
  "alex"` plus `get_selected_user_id`/`select_user`/`render_user_sidebar`
  (D-16) and `load_profile_or_none` (only `DEFAULT_USER_ID` is still
  auto-seeded with the demo profile; every other user without a profile
  gets `None`, so `app.py` shows the hint instead of seeding anything,
  WP-08 goal 2). The selected user is kept in `st.query_params` (checked
  as asked: `st.session_state` does **not** survive a browser reload -
  a fresh `AppTest`/session resets it - `st.query_params` does, the same
  mechanism `app.py`'s own `thread_id` already used; both are shared
  across a Streamlit multipage app's pages already).
- `app.py`: sidebar now shows the user picker (existing users + "add new
  user") before anything else; a user with no stored profile sees an
  `st.info` hint plus `st.page_link` to the profile page instead of the
  chat. New `render_thread_list` (sidebar: title, Resume/Current, Delete
  with a second-click Yes/No confirm; deleting the open thread calls
  `start_new_thread()`). Every user message now also calls
  `storage.touch_thread(...)` before `run_turn` (goal 5); the agent
  payload's `user_id` is the selected user, not the old constant.
- `pages/1_Tracker.py`, `pages/2_Memory.py`: call `render_user_sidebar`
  and use its returned `user_id` everywhere `USER_ID` was used before.
- `pages/3_Profile.py` (new, FR-14): a form with every `Profile` field
  (skills as comma-separated text; no min/max on the radius widget on
  purpose, so an out-of-range value reaches `Profile`'s own `ge=5, le=200`
  validation and this page's friendly `st.error`, not a silently clamped
  widget); "Load demo profile" stores `data/samples/profile_alex.yaml`
  for whichever user is selected; a caption notes the profile reaches the
  rubric immediately but the model's own context message only on the
  next *new* thread (`LoadProfileContextMiddleware` injects once per
  thread, unchanged this package).
- `models.py`: `ThreadRecord` (mirrors `TrackerEntry`'s pattern for the
  new table).

**A Streamlit pitfall found while building the sidebar picker:**
`st.session_state[key]` cannot be written once a widget with that `key`
has already been instantiated in the *same* run (`StreamlitWidget
AlreadyInstantiatedError`) - caught by an `AppTest` run, not by eye.
Programmatically moving the selectbox to a newly added user is deferred
through a `_pending_user_select` session-state entry, applied at the very
top of `render_user_sidebar` on the *next* run, before the selectbox is
created.

**A reading of the WP's wording, flagged rather than silently assumed:**
"name ... stored as entered, user id derived as a lowercase slug" is
implemented with no separate display-name storage - the slug *is* the
selected/shown user id everywhere (sidebar, `threads`, `tracker`,
`profiles`), matching "existing users = all user ids with a profile"
literally. No new table was added for this; flag if a separate display
name turns out to be wanted later.

**Checks:** `uv run pytest` 322/322 passed (284 before this package + 38
new: 9 storage tests, 14 `user_view` tests, 5 `pages/3_Profile.py`
AppTest scenarios, 6 user-selection AppTest scenarios, 2 thread-list
AppTest scenarios in `test_app.py`, 1 tracker-isolation and 1
memory-isolation test), no skipped, 98% coverage, every touched module
100%. `uv run ruff check .` clean. `uv run ruff format --check .` clean
(after formatting the two files it flagged). `uv run mypy src app.py
pages ui_shared.py` clean, 34 source files.

**No real-model run this package** (per the WP: no change to tools,
prompts, middleware or the agent - only `app.py`, `pages/`, `ui_shared.py`
and the new, pure `user_view.py`/`storage.py` additions).

**Manual browser check for Ingo (6 steps):** (1) in the sidebar, type a
second user's name under "Add new user" and click "Add user" - confirm
the main page now shows the no-profile hint; (2) follow the link to the
Profile page, fill in and save a profile for that user; (3) go back to
the main page, run a search; (4) switch back to "alex" in the sidebar -
confirm alex's own threads show, not the new user's; (5) click "Resume"
on an older alex thread and confirm its history loads; (6) delete a
thread with the two-click confirm and confirm it disappears from the
list.

**Next:** show the commit proposal (prompt + D-15 + D-16; `threads` table
+ `list_users` + `user_view.py` + their tests; user selection in
`ui_shared.py` + all pages; profile page + AppTest; thread list + AppTest
+ this session log entry) and wait for approval before any commit. After
that: developer settings, safety tests, evaluation (§9) remain per spec
§13.

## 2026-11-10 — WP-09: developer settings and automatic demo mode

**Check first, reported before building (per the WP):**
1. Token usage for the extraction calls inside `assess_fit` cannot be
   captured via an ambient callback (e.g. `get_usage_metadata_callback()`):
   confirmed with a direct test that Python's `ThreadPoolExecutor` does not
   copy the caller's `contextvars` into worker threads, so a contextvar-based
   callback registered around `assess_fit`'s call never reaches the
   extraction calls running inside it. The fix that needed no tool-contract
   change: a custom `usage.UsageCallbackHandler`, passed *explicitly* as
   `config={"callbacks": [...]}` to every model call - the main loop's
   `agent.stream(...)` and each extraction's own `.invoke(...)` inside
   `tools/assess.py`. Confirmed directly against a real `ThreadPoolExecutor`
   that an explicit `config` (not ambient context) reaches every worker.
2. OpenRouter already reports the cost of a call in
   `response.response_metadata["token_usage"]["cost"]`, for both the main
   loop and the `include_raw`/plain structured-output extraction call, for
   both `openai/gpt-5-mini` and `anthropic/claude-haiku-4.5` - with or
   without an explicit `extra_body["usage"]["include"]`. This differs from
   D-17's Sprint 2 context note ("missing for structured-output calls") -
   worth flagging as a possible OpenRouter/API-version change since D-17 was
   written, not a contradiction to resolve now (D-17's estimate fallback
   still matters whenever the endpoint or a specific model's cost is
   missing).
3. `anthropic/claude-haiku-4.5` works with the existing ZDR provider
   preferences and the reasoning parameter: a real call to both models with
   `extra_body={"reasoning": {"effort": ...}, "provider": {"data_collection":
   "deny", "zdr": true}}` succeeded for both, confirming D-4 again under the
   real developer-settings code path (`llm.build_real_model(model,
   reasoning_effort)`). `claude-haiku-4.5` reports non-trivial
   `reasoning_tokens` inside `output_tokens` (e.g. 31-174 tokens per call in
   the "Check first" probes); `gpt-5-mini` at `reasoning_effort="low"`
   reported 0 in these probes.

No item needed a new decision file - all three had a working answer inside
D-17/D-4's existing scope.

**Built (FR-18 AC1, FR-18 AC2, FR-19 AC3):**
- `config.py`: `OPENROUTER_MODELS_URL`, `OPENROUTER_PRICES_TIMEOUT_SECONDS`,
  `BA_REACHABILITY_TIMEOUT_SECONDS`.
- `pricing.py` (new, D-17): fetches the OpenRouter model price list via
  `httpx` (not `urllib`, project convention), same pattern as
  `ba_client.BAClient` - pass a pre-built `httpx.Client` for tests.
  `fetch_model_prices`/`get_prices`/`get_price`/`estimate_cost_usd`; a
  failed fetch is never cached.
- `usage.py` (new, FR-18 AC2): `LlmUsage` (token counts + reported cost),
  `UsageCallbackHandler` (thread-safe, collects one `LlmUsage` per call it
  observes via `on_llm_end`), `TurnUsageTracker` (pairs an `agent_loop` and
  an `extraction` handler for one turn), `aggregate`/`cost_label`/
  `usage_caption` (pure functions: reported cost preferred, `pricing`
  estimate otherwise, "cost unavailable" when neither is known).
- `context.py`: `AgentContext.usage_tracker: Any = None` (same "typed `Any`,
  defaulted to `None`" reasoning as `extraction_model` - importing
  `usage.TurnUsageTracker` here would pull in `langchain_core.callbacks`
  before it is guaranteed loaded; `None` keeps every existing
  `AgentContext(...)` construction in the test suite working unchanged).
- `tools/assess.py`: `_extract_one`/`run_extraction` pass
  `runtime.context.usage_tracker.extraction` as `config={"callbacks": [...]}`
  to each structured-extraction call, when a tracker is present - no change
  to `ToolResult`/`JobRequirements` (spec §6 untouched).
- `llm.build_real_model(model=None, reasoning_effort=None)`: both now
  overridable, defaulting to `config.py` as before - every existing call site
  (`app.py`, four `scripts/*.py`) keeps working unchanged.
- `agent.build_agent(model, conn, tools=None)`: `tools` now overridable,
  defaulting to `AGENT_TOOLS` - developer settings' `get_job_details` toggle
  passes a filtered list.
- `ba_client.check_reachable(client=None)` (FR-19 AC3): one request, a short
  fixed timeout, no retry loop (deliberately not `BAClient.search`, whose
  §8 retry budget would delay every app start); 403/429/5xx/timeout all
  count as unreachable.
- `ui_shared.py`: session-state keys and defaults for developer settings
  (`ensure_developer_settings_initialized`, called at the top of every page
  like `render_user_sidebar`); `record_turn_usage`/`session_usage_records`/
  `last_turn_usage_records` (kept split into agent-loop/extraction lists
  throughout, per FR-18 AC2's "split into agent loop and extraction");
  `render_usage_summary` (shared by the main page's sidebar/per-turn caption
  and the settings page).
- `pages/4_Developer_settings.py` (new, FR-18 AC1): chat model, reasoning
  effort, `get_job_details` toggle, demo mode (moved from the main
  sidebar), and this session's token usage/cost.
- `app.py`: reads the four settings from session state instead of
  hard-coded defaults; `get_model(model, reasoning_effort)` is now
  `@st.cache_resource`-keyed per combination, so switching either in
  developer settings builds (and then reuses) a distinct client; filters
  `AGENT_TOOLS` when `get_job_details` is disabled; a fresh
  `usage.TurnUsageTracker` per page run, its `agent_loop` handler attached
  to both `agent.stream(...)` (new turns) and the approval-resume
  `agent.invoke(...)`; per-turn usage in a collapsed expander under the
  chat, per-session usage in the sidebar. The test-only `_ScriptedModel`
  (`JOB_HUNT_FAKE_MODEL=1`) now subclasses `BaseChatModel` properly instead
  of being a bare duck-typed object - found while writing the AppTest
  coverage below: `create_agent`'s model node only threads `config` (and
  its `callbacks`) into a model's own call through the full
  `Runnable`/`BaseChatModel` protocol, confirmed by instrumenting a bare
  object's `.invoke()` and observing it receive `config=None` even though
  `agent.stream(..., config={"callbacks": [...]})` was given one explicitly.
  Every scripted turn now also reports a fixed, non-zero `usage_metadata`/
  `response_metadata`, so FR-18 AC2's usage display is exercisable in
  AppTest without a real OpenRouter call.

**Tests (NFR-05):** `tests/test_pricing.py` (new, 9 tests, `httpx.MockTransport`:
ok, malformed entry, timeout, HTTP error, failure-not-cached, success-cached,
unknown model), `tests/test_usage.py` (new, 15 tests: callback handler,
tracker, `aggregate`/`cost_label`/`usage_caption` covering
reported/estimated/unpriced), `tests/test_pages_developer_settings.py` (new,
8 tests: defaults, each setting change persists in session state, the
automatic demo-mode message, cost-unavailable-with-no-calls, session totals
render). Extended: `tests/test_ba_client.py` (45 tests total, incl.
`check_reachable` ok/timeout/5xx/403/no-retry), `tests/test_llm.py` (3 total,
incl. model/effort overrides), `tests/test_build_agent.py` (3 total, incl. a
custom `tools` list actually used), `tests/test_tools_assess.py` (9 total,
incl. extraction usage landing in `usage_tracker.extraction` through the
real `ThreadPoolExecutor` path), `tests/test_app.py` (13 total, incl.
per-turn/per-session usage rendering with the scripted model's fixed usage,
and disabling `get_job_details` making LangGraph's own `ToolNode` return its
"not a valid tool" `ToolMessage` instead of the tool running). A new global
`conftest.py` autouse fixture stubs `ba_client.check_reachable` to `True` for
every test (found while writing the settings-page tests:
`ensure_developer_settings_initialized()`'s once-per-session check would
otherwise have made *every* existing `AppTest` run of `app.py` reach the real
BA API the first time `demo_mode` was read from session state - invariant 5;
`test_ba_client.py`'s own `check_reachable` tests import the function by
name, so this stub does not affect them).

`uv run pytest`: **366 passed**, no skipped, **98% coverage** overall;
`pricing.py` and `usage.py` both 100%, every other touched module 96-100%
(full per-file numbers in the coverage table the test run prints).
`uv run ruff check .` clean. `uv run ruff format --check .` clean (114
files). `uv run mypy src app.py pages ui_shared.py` clean, 37 source files.

**Real-model check** (`scripts/wp09_settings_check.py`, demo query "Find
Softwareentwickler jobs in München.", D-10's recorded search):

| Scenario | Model | Elapsed | Tools | Agent-loop tokens (in/out) | Agent-loop cost | Extraction tokens (in/out) | Extraction cost |
|---|---|---|---|---|---|---|---|
| default | `gpt-5-mini` | 47.8s | search x3, details x5, assess_fit | 29,655 / 2,079 | $0.0076 (reported) | 7,036 / 7,143 | $0.0160 (reported) |
| secondary | `claude-haiku-4.5` | 62.5s | search x3, details x5, assess_fit | 41,501 / 1,801 | $0.0505 (reported) | 12,258 / 21,531 | $0.1199 (reported) |
| `get_job_details` disabled | `gpt-5-mini` | 47.5s | search x2, assess_fit (**no** details calls) | 14,470 / 2,188 | $0.0067 (reported) | 8,613 / 10,229 | $0.0223 (reported) |

Every one of the 32 calls across all three runs (11 + 11 + 10, agent loop
and extraction combined) had its cost reported by OpenRouter directly (0
estimated, 0 unpriced) - consistent with "Check
first" item 2 above. Goal 4 (agent behaviour without `get_job_details`):
the agent skipped straight to `search_jobs` then `assess_fit` - never
attempted `get_job_details` and never produced a tool error - confirming
`assess_fit`'s own detail-loading (spec §6.1) is enough for the core
journey. `claude-haiku-4.5`'s combined cost ($0.1704) was ~7.2x `gpt-5-mini`'s
($0.0237) on this single run (consistent with D-4's token-count numbers),
reinforcing D-4's recommendation that it stay the secondary, not the default. Full raw
per-call data: `eval/results/wp09_settings_check.json`.

**Manual browser check for Ingo (5 steps):** (1) open "Developer settings"
from the sidebar page list; (2) switch the chat model to
`anthropic/claude-haiku-4.5` and the reasoning effort to `high`; (3) go back
to the main page and run the demo query "Find Softwareentwickler jobs in
München."; (4) read the per-turn usage under the newest answer and the
per-session usage in the sidebar (both split into agent loop/extraction,
with cost); (5) return to Developer settings, switch the model back to
`openai/gpt-5-mini` and confirm the session usage total is unchanged (it
accumulates, it does not reset on a setting change).

**Next:** show the commit proposal and wait for approval before any commit.
After that: the LangSmith toggle (WP-10), the `list_tracker` toggle
(WP-11), safety tests, and evaluation (§9) remain per spec §13.
