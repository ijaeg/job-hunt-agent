# WP-11: Parallel tool calls in one agent step

Date: 2026-11-11
Related: spec §5.3, §5.4, FR-02 AC5, FR-03 AC2, FR-05 AC5, FR-20 AC1, FR-20 AC2, NFR-05, D-19

## Step 0
Save this prompt verbatim as docs/prompts/WP-11-parallel-tool-calls.md. We are on branch feature/parallel-tool-calls. docs/decisions/D-19-parallel-tool-calls.md (new, from the coach) belongs in the first commit together with the prompt.

## Decided in advance (do not re-decide)
- D-19, Option A: fix the cause in the state. Fields that tools update get reducers in state.py; behaviour with a single call per step stays exactly as it is now. The search limit (FR-20 AC1: max. 3 search_jobs calls per user message) must count every proposed call, including several in one step.

## Stop rule
If a reducer would change what happens with a single call per step (e.g. shortlist semantics), or the limit cannot be enforced correctly without a contract change (spec §6), stop at that point, write the decision file and report. Do not implement a solution before Ingo has decided.

## Check first (Checks #4) - report before building on it
1. List every JobHuntState field, which tool or middleware writes it, and with which semantics (replace, append, merge). This decides the reducer per field.
2. Reproduce the bug with a scripted model: one AIMessage with two search_jobs calls -> InvalidUpdateError today. Same for two get_job_details and two assess_fit calls in one step, if those write state.
3. Search limit: check whether the built-in ToolCallLimitMiddleware (installed langchain version) counts several calls in one model step correctly and blocks the excess ones, and whether its counting fits "per user message". If yes, use it and drop the own counter; if not, enforce the limit after the model step and before the tools run (like RejectionLockMiddleware: drop excess search_jobs calls from the newest AIMessage, replaced by a short note). Report which way and why.

## Build
- state.py: reducers per field from check 1 (e.g. order-preserving union without duplicates for reference lists, dict merge for summaries/assessments). Docstring per field: who writes it and why the reducer is safe.
- Search limit per check 3; the existing ResetSearchCallCounterMiddleware goes away if it is no longer needed.
- No change to tools' return contracts (spec §6), prompts or the UI.

## Tests (NFR-05)
- The reproductions from check 2 now pass: two parallel search_jobs -> no error, seen_refs and summaries contain both results, no duplicates.
- Four search_jobs calls proposed in one step after none before -> exactly 3 run, the 4th is refused with a note; two in one step after two earlier ones in the same message -> exactly 1 runs.
- A new user message resets the limit.
- All existing tests stay green (single-call behaviour unchanged).

## Real-model check (Checks #2)
5 runs of the demo query "Find Softwareentwickler jobs in München." on fresh threads: record per run completion (reached assess_fit), number of search_jobs calls proposed and executed, whether any step had parallel tool calls, errors. eval/results/wp11_parallel_check.json. No run may end in an error.

## Done when
- All checks of CLAUDE.md "Checks before hand-over" pass, with numbers.
- docs/session_log.md has an entry; propose the exact new wording for spec §5.3 in the report (the coach updates the spec).

## Commits
Propose small commits and wait for Ingo's approval each time. Suggested split: prompt + D-19; reproduction tests (marked xfail strict until the fix); reducers + tests; search limit + tests; real-model check + session log.
