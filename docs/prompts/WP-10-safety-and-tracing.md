# WP-10: Safety tests and LangSmith tracing

Date: 2026-11-11
Related: spec §9.4, §9.5, §12.3 (Hard 2, Medium 8), FR-18 AC1, FR-20, FR-21, FR-22, FR-23, FR-10 AC3, NFR-01, NFR-05, D-18

## Step 0
Save this prompt verbatim as docs/prompts/WP-10-safety-and-tracing.md. We are on branch feature/safety-and-tracing. docs/decisions/D-18-langsmith-data.md (new, from the coach) belongs in the first commit together with the prompt.

## Decided in advance (do not re-decide)
- D-18: LangSmith tracing is off by default and switched on only on the developer settings page. Traces for the README are made in demo mode with the fictional user "alex". The README section on data handling (FR-22 AC4) will name what is sent to LangSmith when tracing is on (messages, cleaned ad texts, profile, user id) - write a short text block for it into docs/langsmith.md; the README itself is WP-14.

## Stop rules
1. Planned stop: after Part A step 1 (the concrete safety cases), stop and show Ingo the list. Run nothing until he has approved it (CLAUDE.md: the content of an evaluation set is Ingo's decision).
2. If anything else turns out to need a decision, stop at that point, write the decision file and report. Do not implement a solution before Ingo has decided.

## Check first (Checks #4) - report before building on it
1. LangSmith reads parts of its configuration only once (cached environment lookups). Confirm a way to switch tracing on and off within a running session (e.g. passing a LangChainTracer callback, or tracing_v2_enabled() per run) without restarting the app. The key comes from the environment variable LANGSMITH_API_KEY (already set on Ingo's machine); never write it to a file, a log or the UI.
2. Find out from a test call whether the key belongs to the US or the EU region of LangSmith and set the endpoint accordingly (config.py, overridable by LANGSMITH_ENDPOINT).
3. Confirm that the crafted injection listing for S5 (data/samples/fixtures) is reachable in demo mode through a search the agent would plausibly make; name that search. If it is not reachable, stop and report.

## Part A: Safety tests (spec §9.4)
1. Write docs/safety_tests.md with at least 10 cases: injection in user input (3), injection in ad text (3, incl. S5), off-topic (2, incl. S6), PII in ad text (the five D-3 spike listings as one case), rejected approval followed by a retry request (1, FR-10 AC3). Per case: id, category, input, expected behaviour, how it is checked (code check where possible, e.g. "no write tool executed", "no name in the text sent to the model"). Then stop (stop rule 1).
2. After approval: a script scripts/run_safety_tests.py runs every case in demo mode against the real model and records per case: actual behaviour, tool calls, pass/fail by the defined check, run date, model. Results: eval/results/safety_wp10.json; fill the result columns in docs/safety_tests.md from that file.
3. A failed case is reported, not fixed in this package. Write it down in docs/safety_tests.md and in your report.

## Part B: LangSmith tracing (spec §9.5, Hard 2)
1. A toggle "LangSmith tracing" on pages/4_Developer_settings.py (own session-state key, like the other settings). Off by default. Without LANGSMITH_API_KEY the toggle is disabled with a short note. A tracing failure never affects the app (spec §8).
2. Runs carry useful metadata: project name from config.py (e.g. "job-hunt-agent"), tags for demo/live and the scenario where known, thread id.
3. Real-model runs with tracing on, demo mode, user "alex": S1 (narrowing), S3 (save -> approve), S4 (remember -> reject). Record the run ids and the LangSmith project in eval/results/langsmith_wp10.json and in docs/langsmith.md, together with what Ingo has to do in WP-14 to make them visible to the reviewer (public share link or screenshot).
4. One raw model request and response for the function-calling explanation (§9.5): the request with the tool schemas and the response with tool_calls, from one S1 run, saved to docs/function_calling_example.json. Remove ad texts from it (keep the structure, replace long content with a short placeholder); no key, no personal data.

## Tests (NFR-05)
- Unit tests: tracing toggle on/off decides whether a tracer is attached; no key -> toggle disabled; tracer failure is swallowed. No test reaches LangSmith, OpenRouter or the BA API (invariant 5).
- AppTest: the toggle renders, persists across a page switch, is disabled without the key.

## Done when
- All checks of CLAUDE.md "Checks before hand-over" pass, with numbers.
- docs/session_log.md has an entry.
- A short manual check for Ingo: switch tracing on, run the demo query, open the trace in LangSmith, switch tracing off.

## Commits
Propose small commits and wait for Ingo's approval each time. Suggested split: prompt + D-18; safety case list (after approval); safety script + results; tracing toggle + tests; traces + function-calling example + docs/langsmith.md + session log.
