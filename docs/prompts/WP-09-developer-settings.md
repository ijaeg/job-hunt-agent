# WP-09: Developer settings and automatic demo mode

Related: FR-18 AC1, FR-18 AC2, FR-19 AC3, FR-16 AC3, NFR-02, NFR-04, NFR-05, spec §5.5, §8, §12.3 (Medium 1, Medium 8, Easy 3, Easy 4), D-4, D-17

## Step 0
Save this prompt verbatim as docs/prompts/WP-09-developer-settings.md. We are on branch feature/developer-settings. docs/decisions/D-17-price-source.md (new, from the coach) belongs in the first commit together with the prompt.

## Decided in advance (do not re-decide)
- D-17: prices follow the pattern of Ingo's Sprint 2 project (~/projects/turing-college/ijager-AE.AFA.updated0209.2.5, src/collection_letter_navigator/pricing.py - read it, do not import it): fetch the price table once per session from the OpenRouter models endpoint (no API key needed), use the cost OpenRouter reports for a call when present, otherwise estimate from token counts (reasoning tokens count as completion tokens). If the endpoint is unavailable the app keeps working and shows "cost unavailable"; failures are never cached. Use httpx (this project's HTTP client, testable with httpx.MockTransport), not urllib. The models URL goes into config.py. The UI labels the number "cost" when reported by OpenRouter and "estimated cost" otherwise.
- Not in this package: the LangSmith toggle (WP-10) and the list_tracker toggle (WP-11).

## Stop rule
If anything turns out to need a decision beyond the above, stop at that point, write the decision file and report. Do not implement a solution before Ingo has decided.

## Check first (Checks #4) - report before building on it
1. Token usage must include the structured-extraction calls inside assess_fit, not only the main agent loop - they are the largest share. They run in a ThreadPoolExecutor, so callbacks from the run config may not reach them. Find a way that captures both (e.g. a usage callback passed in the run config, or assess_fit reporting its own usage). If none works without changing a tool contract (spec §6), stop and write a decision file.
2. Check whether the OpenRouter response cost reaches LangChain's response metadata for the agent loop and for the extraction calls; report what is available for each.
3. Confirm that switching to anthropic/claude-haiku-4.5 works with the existing ZDR provider preferences and the reasoning parameter (D-4); report how reasoning effort is passed for each model.

## Goal
1. Page pages/4_Developer_settings.py (FR-18 AC1), separate from the main flow: chat model from config.CHAT_MODEL_OPTIONS, reasoning effort from config.REASONING_EFFORT_OPTIONS, a toggle for get_job_details, and the demo-mode switch (moved here from the main sidebar; the main page keeps the demo banner). Settings live in the session (st.session_state) and default to config.py; the main page builds model and agent from them. The same model and effort apply to the extraction in assess_fit; say so on the page.
2. Token usage and cost (FR-18 AC2): per turn (shown under each answer, small) and per session (on the settings page and in the sidebar), input and output tokens split into agent loop and extraction, computed by pure functions. Price unknown -> tokens shown, "cost unavailable".
3. Automatic demo mode (FR-19 AC3): at start-up the app checks once per session whether the BA API is reachable (short timeout, one cheap request via BAClient, no retry loop). If not, demo mode switches on and a message says why. The result is cached for the session.
4. Disabling get_job_details removes it from the agent's tools for new turns; assess_fit keeps loading details itself. Report how the agent behaves without it in one real-model run.

## Tests (NFR-05)
- Unit tests: price fetch with httpx.MockTransport (ok, timeout, malformed entry, HTTP error, failure not cached), cost function (reported cost preferred, estimate, unknown model), usage aggregation per turn and per session, reachability check (ok, timeout, 5xx, 403).
- AppTest: settings page changes model/effort/toggle and the main page uses them; per-turn and per-session usage render with a scripted model that reports usage metadata; unreachable API -> demo mode on with the message; prices unavailable -> "cost unavailable", no error.
- Existing tests stay green. No test reaches OpenRouter or the BA API (invariant 5).

## Real-model check (Checks #2)
Demo query "Find Softwareentwickler jobs in München." once with each model (default effort), once with get_job_details disabled. Record per run: elapsed seconds, tool sequence, input/output tokens split into agent loop and extraction, cost and whether it was reported or estimated. eval/results/wp09_settings_check.json.

## Done when
- All checks of CLAUDE.md "Checks before hand-over" pass, with numbers.
- docs/session_log.md has an entry.
- A 5-step manual browser check for Ingo (open settings, switch model, run the demo query, read tokens and cost per turn and per session, switch back).

## Commits
Propose small commits and wait for Ingo's approval each time. Suggested split: prompt + D-17; price fetch + cost and usage functions + tests; usage capture incl. extraction; settings page + wiring + AppTest; reachability check + automatic demo mode + tests; real-model check + session log.
