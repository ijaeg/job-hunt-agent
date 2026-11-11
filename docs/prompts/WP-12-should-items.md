# WP-12: Agent steps panel and list_tracker tool (Should items)

Date: 2026-11-11
Related: FR-17 AC1, FR-12 AC1, FR-18 AC1, FR-09, FR-10, FR-16, NFR-04, NFR-05, spec §5, §12.3 (Medium 6)

## Step 0
Save this prompt verbatim as docs/prompts/WP-12-should-items.md. We are on branch feature/should-items.

## Decided in advance (do not re-decide)
- Steps panel durations: shown for turns run in the current session (measured from the stream); for turns of a resumed older thread the same steps are shown without duration ("-"). No new table for durations.
- Short result per tool call, never ad text: e.g. search_jobs "103 results, 25 returned", get_job_details "details loaded" or "no longer available", assess_fit "6 listings assessed", save_to_tracker / remember "saved" or "rejected", list_tracker "4 entries", and the not_applicable_reason when set.

## Stop rule
If anything turns out to need a decision beyond the above (a spec deviation, a contract change, a new dependency), stop at that point, write the decision file and report. Do not implement a solution before Ingo has decided.

## Check first (Checks #4) - report before building on it
1. How the steps of one turn can be read back from the checkpointer (AIMessage tool_calls with their ToolMessages, grouped per user message), also for parallel calls in one step (D-19).
2. Where the system prompt has to mention list_tracker, and that a disabled tool is handled the same way as a disabled get_job_details (WP-09).

## Goal
1. Steps panel (FR-17 AC1): under each assistant answer on the main page, a collapsed expander "Agent steps (N)" lists the tool calls of that turn in order: tool, arguments (compact), short result, duration. Parallel calls of one step are marked as such. Pure helper functions in src/ build the rows from messages; app.py only renders.
2. Tool list_tracker (FR-12 AC1): read-only, no approval, returns the selected user's tracker entries (referenznummer, title, employer, status, follow-up date) as a ToolResult. The agent uses it to answer "What have I saved?" and to mark or skip listings that are already in the tracker. Update prompts/system.md accordingly.
3. Toggle for list_tracker on pages/4_Developer_settings.py (FR-18 AC1, Medium 6), own session-state key like the other settings, default on.

## Tests (NFR-05)
- Unit tests: step rows from messages (single calls, parallel calls, not_applicable_reason, missing ToolMessage), short results per tool, list_tracker (entries, empty, per-user isolation).
- AppTest: the expander renders under an answer with a scripted model; the toggle persists across a page switch and removes list_tracker from the agent's tools.
- Existing tests stay green.

## Real-model check (Checks #2)
Demo mode, user "alex", one thread: (1) save one listing from a demo search with approval, (2) "What have I saved?", (3) the demo query again. Record tool sequence, whether list_tracker was used in (2) and whether the saved listing is marked or skipped in (3). Repeat (2) once with list_tracker disabled. eval/results/wp12_should_check.json.

## Done when
- All checks of CLAUDE.md "Checks before hand-over" pass, with numbers.
- docs/session_log.md has an entry.
- A 4-step manual browser check for Ingo (run the demo query and open "Agent steps", save a listing, ask "What have I saved?", switch list_tracker off and ask again).

## Commits
Propose small commits and wait for Ingo's approval each time. Suggested split: prompt; step-row helpers + tests; steps panel in app.py + AppTest; list_tracker tool + system prompt + tests; toggle + AppTest; real-model check + session log.
