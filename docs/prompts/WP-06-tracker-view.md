# WP-06: Tracker view (FR-11)

Related: FR-11 AC1, FR-11 AC2, FR-09 AC1, NFR-04, NFR-05, spec §11

## Step 0
Save this prompt verbatim as docs/prompts/WP-06-tracker-view.md. We are on branch feature/tracker-view. Two changes from the coach are uncommitted and belong in the first commit together with the prompt file: docs/decisions/D-13-explanation-consistency.md (new) and PRODUCT_SPEC.md (v0.1.8, D-13 in §14).

## Goal
A separate page pages/1_Tracker.py (spec §11) lists all tracker entries of the user with title (linked to the listing), employer, status, follow-up date and note. Entries whose follow-up date is in the past are visibly highlighted (FR-11 AC1). The user can change an entry's status and delete an entry directly on the page, without approval - these are user actions, not agent actions (FR-11 AC2). Nothing else: no list_tracker tool (FR-12), no memory page, no profile form.

## Build
- Shared UI resources: the page needs the same cached SQLite connection, user id and profile seeding as app.py. Move get_connection, USER_ID and load_or_seed_profile (and whatever else both need) out of app.py into one shared UI module next to app.py (e.g. ui_shared.py) and use it from app.py and the page. The page must not import app.py. Keep the dependency direction of CLAUDE.md (UI -> package, never the reverse); no Streamlit import inside src/.
- storage.py: add delete_tracker_entry(conn, user_id, referenznummer) -> bool (inside a transaction, spec §8). Changing the status reuses save_tracker_entry with a new updated_at; created_at stays unchanged.
- Pure helpers in src/job_hunt_agent/ui_view.py (or a sibling module), with unit tests: whether an entry is overdue, given "today" as a parameter (no hidden date.today() in the helper); ordering of the rows (overdue first, then by updated_at, newest first).
- Delete needs a second click to confirm (no accidental deletes); no browser dialogs.
- Empty state: a short hint that entries are saved from the shortlist on the main page.
- No stack trace in the UI (invariant 7).

## Tests (NFR-05)
- Unit tests for the new storage function and the pure helpers.
- AppTest for pages/1_Tracker.py on a temp DB seeded with three entries (one overdue): rows render in the right order and the overdue one is marked; changing the status updates the row in SQLite (check directly) and keeps created_at; delete with confirmation removes the row; empty state renders.
- Existing tests in tests/test_app.py stay green after the move to the shared module.

## Checks
All checks of CLAUDE.md "Checks before hand-over", with numbers. mypy now covers the page and the shared module: uv run mypy src app.py pages ui_shared.py scripts (adjust the names to what you created). No real-model run needed: no change to tools, prompts, middleware or the agent - say so explicitly in the report.

## Done when
- Checks pass, docs/session_log.md has an entry.
- You give Ingo a 4-step manual check in the browser (start, save one listing from the main page, open the tracker page, change status and delete).

## Commits
Propose small commits and wait for Ingo's approval each time. Suggested split: prompt + D-13 + spec; shared UI module (move only, no behaviour change); storage delete + helpers + tests; tracker page + AppTest + session log.
