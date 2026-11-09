# WP-08: Profile form, thread list and user selection

Related: FR-14 AC1-AC3, FR-13 AC2, FR-13 AC3, FR-15, FR-01 AC4, spec §2.2, §11, NFR-04, NFR-05, D-5, D-6, D-14, D-15, D-16

## Step 0
Save this prompt verbatim as docs/prompts/WP-08-profile-threads-users.md. We are on branch feature/profile-threads-users. Two decision files from the coach are uncommitted and belong in the first commit with the prompt: docs/decisions/D-15-thread-registry.md and docs/decisions/D-16-user-selection.md.

## Decided in advance (do not re-decide)
- D-15: threads are listed from an own table `threads` (user_id, thread_id, title, created_at, updated_at) in storage.py, same pattern as `tracker` and `profiles`. Title = first user message of the thread, cut to 60 characters.
- D-16: a user is selected by name in the sidebar, no authentication (spec §2.2).
- The profile form is its own page pages/3_Profile.py (Developer settings will be page 4 later).

## Stop rule
If anything turns out to need a decision beyond the above (a spec deviation, a contract change, a new dependency), stop at that point, write the decision file and report. Do not implement a solution before Ingo has decided.

## Goal
1. User selection (D-16): the sidebar on every page shows the selected user and lets the user pick another existing one or add a new one (name: letters, digits, spaces, hyphens; max 40 characters; stored as entered, user id derived as a lowercase slug). Existing users = all user ids with a profile. Default on first start: "alex" with the demo profile, as today. All pages (main, tracker, memory, profile) use the selected user from one place in ui_shared.py, replacing the fixed USER_ID. The selection survives a page switch and a browser reload; check which mechanism (st.session_state, st.query_params) actually does that across pages and report it. Switching the user opens a new empty thread for that user.
2. A user without a profile: the main page shows a short hint with a link to the profile page instead of the chat; nothing is seeded silently.
3. Profile page (FR-14): a form with all Profile fields (skills as comma-separated text, seniority, location, radius 5-200 km, remote preference, full-time, permanent, exclude temp agency, German and English level). Save validates via the Profile model and stores via storage.save_profile; invalid input shows a friendly message. "Load demo profile" fills the form with data/samples/profile_alex.yaml and saves it (AC2). No name, e-mail, phone or address field (AC3). A short note: the fit assessment uses the new profile immediately; the agent sees it in full from the next new search.
4. Thread list (FR-13 AC2): the main page's sidebar lists the selected user's threads (title, last update, newest first). Clicking one resumes it; delete with a second click removes it from the checkpointer (SqliteSaver.delete_thread) and from `threads`. Deleting the open thread opens a new empty one. "New search" stays.
5. Registering threads: add to `threads` when the first user message is sent, refresh updated_at on every later turn - in the UI layer via storage functions. No change to the agent, tools or middleware.

## Check first (Checks #4)
- Confirm that SqliteSaver in the installed langgraph version offers delete_thread and that it works on the shared connection (D-5, D-14). Report before building on it.
- Confirm that tracker, memories and profile are already keyed by user id everywhere (storage, tools, middleware) and that the agent payload's user_id is the only thing app.py must change. Report any place that still assumes "alex".

## Build
- storage.py: `threads` table with the others; upsert, list_threads(user_id), delete_thread_record; list_users() from `profiles`. Inside transactions (spec §8). No Streamlit import in src/.
- Pure helpers (title cut, user-id slug, name validation, ordering) in src/ with unit tests.

## Tests (NFR-05)
- Unit tests for the new storage functions (upsert, ordering, per-user isolation, delete, list_users) and the helpers.
- AppTest: user selection - adding a user, switching users, each user sees only their own threads, tracker entries and memories; a user without a profile sees the hint, not the chat.
- AppTest for pages/3_Profile.py: renders the stored profile; save updates SQLite; invalid radius shows a message, no exception; "Load demo profile" stores the YAML values.
- AppTest for the thread list with a scripted model: first message registers the thread with its title; two threads newest first; clicking resumes the other thread; delete with confirmation removes it from checkpointer and table; deleting the open thread opens a new one.
- Existing tests stay green.

## Checks
All checks of CLAUDE.md "Checks before hand-over", with numbers (mypy including pages and ui_shared.py). No real-model run needed - no change to tools, prompts, middleware or the agent; say so explicitly.

## Done when
- Checks pass, docs/session_log.md has an entry.
- A 6-step manual browser check for Ingo (add a second user, fill its profile, run a search, switch back to alex and see alex's threads only, resume an old thread, delete a thread).

## Commits
Propose small commits and wait for Ingo's approval each time. Suggested split: prompt + D-15 + D-16; threads table + list_users + helpers + tests; user selection in ui_shared.py + all pages; profile page + AppTest; thread list + AppTest + session log.
