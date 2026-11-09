Date: 2026-11-09

Related: FR-01 AC1, FR-07, FR-10 AC2, FR-10 AC5, FR-16, FR-19 AC1-AC2 (switch and banner only),
NFR-03, NFR-04, NFR-05, D-5, D-10

---

# WP-04: Streamlit UI for the core journey

Related: FR-01 AC1, FR-07, FR-10 AC2, FR-10 AC5, FR-16, FR-19 AC1-AC2 (switch and banner only), NFR-03, NFR-04, NFR-05, D-5, D-10

## Step 0
Save this prompt verbatim as docs/prompts/WP-04-streamlit-core-ui.md (CLAUDE.md "Hand-over"). We are on branch feature/streamlit-core-ui.

## Goal
The core journey works in the browser: chat -> agent searches, narrows, assesses -> shortlist cards -> "Save to tracker" -> approval buttons -> saved -> still there after a browser reload and an app restart. Nothing beyond that. The tracker page, memory page, profile form, thread list, developer settings, agent steps panel and the automatic demo fallback (FR-19 AC3) are later packages - do not start them.

## Check the data first (CLAUDE.md "Checks before hand-over" #4) - before writing UI code
1. FR-07 AC1 needs, per card, the top 3 matches with the German quote AND the English translation. FitAssessment.matches (models.py) holds only "name — evidence_en" strings; the German quote seems to be absent from the state. Confirm this by reading tools/assess.py and state.py. If confirmed, this is a tool-contract change (spec §6): write docs/decisions/D-11-card-evidence.md (2-3 options, e.g. structured matches in FitAssessment vs. keeping JobRequirements in state) and STOP that part. Build the cards with what exists (English evidence) and mark the German quote as a TODO naming D-11. Do not change models.py before Ingo decides.
2. Card fields title, employer, location, distance, remote, published date come from state["summaries"] (JobSummary). Check that every referenznummer in state["shortlist"] has a summary after a real S1 run; report gaps.
3. The BA listing link: reuse an existing URL builder if there is one (check tools/tracker.py); do not create a second one.
4. Demo mode uses FixtureSource (D-10). Take the query for the demo run from data/samples/fixtures/recorded_searches.json (the München search with 103 results) and confirm it triggers narrowing. Report the exact query text so Ingo can type it in the review.

## Build
- Move build_real_model() from scripts/run_core_journey.py into src/job_hunt_agent/llm.py and use it from the script and the app (no duplicate).
- app.py at the repo root (spec §11, NFR-01: `uv run streamlit run app.py`). app.py holds layout and wiring only, no prompt text and no business logic (NFR-04). Pure helpers go into src/job_hunt_agent/ui_view.py with unit tests, at least: ordering of cards strong -> partial -> poor, excluded separate (FR-07 AC2); low_evidence note (FR-07 AC4); building the card data from summaries + assessments.
- One shared SQLite connection via st.cache_resource (D-5, FR-10 AC5). User id fixed to "alex" for now. Profile: storage.load_profile; if none, load data/samples/profile_alex.yaml and save it.
- Thread id: kept in st.query_params so a browser reload keeps the thread; "New search" button in the sidebar starts a new thread id (FR-16 AC3).
- Demo-mode switch in the sidebar (default: on) selects FixtureSource or BAClient; with demo on, a visible banner "Demo data – not live listings" (FR-19 AC1, AC2).
- Layout: chat left, shortlist cards right (FR-16 AC1). Chat history comes from the checkpointer state, not from session state (FR-01 AC1).
- Progress labels (FR-16 AC2): run the agent with stream(...) and show the current step in st.status, e.g. "Searching the job board…", "Reading N listings…", "Assessing fit…", derived from the tool calls as they arrive.
- Each card has "Save to tracker" (FR-07 AC3): it sends a chat message to the agent naming the listing (title and referenznummer); the agent then proposes save_to_tracker and the interrupt follows.
- Approval (FR-10 AC2, AC5): read the pending interrupt from agent.get_state(config).interrupts, never from session state. Show tool name and exact arguments, with buttons Approve / Edit / Reject. Edit shows the arguments as form fields (save_to_tracker: status, follow_up_date, note; remember: kind, value) and resumes with an "edit" decision. Resume with Command(resume=...) on the same thread. Use spikes/hitl_app.py as the reference, do not import it.
- No stack trace in the UI (invariant 7): errors become a friendly message and the chat stays usable.

## Tests (NFR-05, invariant 5)
- Unit tests for ui_view.py.
- Streamlit AppTest with a scripted model (reuse the scripted model from the existing agent tests) and the fixture source: (a) a turn renders cards in the right order; (b) a save request raises the approval and shows the arguments; (c) approve writes the tracker row (check SQLite directly); (d) reject writes nothing; (e) a new AppTest on the same DB file and thread id (simulated restart) still shows the pending interrupt and the history.

## Real-model smoke run (Checks #2)
One run of the demo query against the real model, headless (AppTest driving app.py, or a small script in scripts/ - not a pytest test). Record tool sequence, elapsed seconds, card count and the status labels shown in eval/results/ui_smoke_wp04.json. If S1 takes longer than 60 s (NFR-03), report it; do not tune anything.

## Done when
- All checks of CLAUDE.md "Checks before hand-over" pass and are reported with numbers, including `uv run mypy src app.py`.
- D-11 exists if check 1 was confirmed.
- docs/session_log.md has an entry.
- You give Ingo a 5-step manual check for the browser (start command, demo query, save, approve, reload).

## Commits
Propose small commits, each with file list, summary and message, and wait for approval every time (CLAUDE.md "No autonomous commits"). Suggested split: prompt file + llm.py move; ui_view.py + tests; app.py + AppTest; smoke result + session log (+ D-11).

---

## Addendum 1 (2026-11-09, after coach review)

Related: FR-10 AC2, FR-16 AC2, D-11

Before any commit, fix these in WP-04:
1. Tool calls are counted twice: eval/results/ui_smoke_wp04.json lists search_jobs, search_jobs, assess_fit twice with identical args. Check the real sequence against the checkpointer messages, deduplicate by tool_call["id"] in app.run_turn (and the smoke script), re-run scripts/ui_smoke_wp04.py and report the corrected numbers.
2. FR-10 AC2 says three buttons. Replace the selectbox + "Submit decision(s)" with buttons Approve / Edit / Reject; Edit shows the form with its own "Save edited action" button. Update tests/test_app.py and add a test for the edit decision (edited args reach the tracker row).
3. D-11 is decided: Option 1, to be done in WP-05 - do not implement it now; keep the TODO(D-11).
4. Add the WP-04 entry to docs/session_log.md, run all checks from CLAUDE.md "Checks before hand-over" and report the numbers. Then propose the commits one by one.
