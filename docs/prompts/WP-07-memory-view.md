# WP-07: Memory view and loading memories into new threads (FR-15 AC2, AC3)

Related: FR-15 AC1-AC4, FR-06 AC1, FR-01 AC4, NFR-04, NFR-05, spec §11, D-6

## Step 0
Save this prompt verbatim as docs/prompts/WP-07-memory-view.md. We are on branch feature/memory-view.

## Goal
1. FR-15 AC2: the user's stored memories (store namespace ("memories", user_id), written by tools/memory.py) are loaded into the agent's context at the start of every new thread, so the agent knows excluded employers and preferences without being told again.
2. FR-15 AC3: a separate page pages/2_Memory.py lists all memory items of the user (kind, value, created date); the user can delete each one directly, without approval (a user action, like FR-11 AC2), with a second click to confirm.
Nothing else: no profile form, no thread list, no developer settings.

## Check first (CLAUDE.md "Checks before hand-over" #4)
- Read tools/memory.py, middleware/profile_context.py, tools/assess.py (how excluded employers are read from the store) and the "apply automatically" wording in prompts/system.md. Report how they fit together before changing anything.
- For the real-model check below you need an employer that actually appears in the München demo results (data/samples/fixtures). Pick one from the data and name it in the report.

## Build
- Loading (AC2): follow the pattern of LoadProfileContextMiddleware: once per thread, on the first model call, inject one clearly labelled context message listing the memories, read via runtime.store. Either extend the existing middleware or add a sibling one; explain the choice. No memories -> no message. Keep the middleware order in agent.py consistent with spec §5.4 and say where you put it.
- Memory access for the page: add small functions in storage.py (list memories, delete one memory by key) on top of the store, so the page does not touch the store API directly. No Streamlit import in src/.
- The page uses ui_shared.py for connection and user id (same pattern as pages/1_Tracker.py). Empty state: a short hint that memories are saved by asking the agent, with approval.
- Excluded employers keep being applied by code in assess_fit (FR-15 AC4), read live from the store - deleting an item on the page takes effect on the next assessment. The context message is only so the model can explain; it never decides an exclusion.
- No stack trace in the UI (invariant 7).

## Tests (NFR-05)
- Unit tests for the new storage functions (list, delete, per-user isolation).
- Middleware tests with a scripted model: memories present -> one context message on the first model call of a new thread, none on later calls; no memories -> no message.
- AppTest for pages/2_Memory.py on a temp DB: items render, delete with confirmation removes the item from the store, cancel keeps it, empty state.

## Real-model check (Checks #2)
Demo mode, two threads on one DB: thread 1 "Never show me jobs from <employer from the data> again." -> approve the remember call. Thread 2 (new thread id) "Find Softwareentwickler jobs in München." -> record whether that employer's listing is excluded with "excluded by you" and whether the agent mentions the stored exclusion. Record in eval/results/wp07_memory_check.json.

## Done when
- All checks of CLAUDE.md "Checks before hand-over" pass, with numbers (mypy including pages and ui_shared.py).
- docs/session_log.md has an entry.
- A 4-step manual browser check for Ingo (save an exclusion with approval, new search, check the card, delete the item on the memory page).

## Commits
Propose small commits and wait for Ingo's approval each time. Suggested split: prompt; storage functions + tests; memory loading middleware + agent wiring + tests; memory page + AppTest; real-model check + session log.
