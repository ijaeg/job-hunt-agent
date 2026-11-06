Date: 2026-11-06

Related: FR-01-FR-10, FR-13-FR-15, FR-20-FR-23, D-4, D-5, D-6, D-9, spec §1.2, §3.2, §5, §6, §7,
§8, §13, §14

---

Work package 3: agent layer – the core journey on the console (no Streamlit UI yet).

Read CLAUDE.md and PRODUCT_SPEC.md first, in particular §1.2, §3.2, §4 (FR-01 to FR-10, FR-13 to
FR-15, FR-20 to FR-23), §5, §6, §7, §8, §13, §14 and spikes/NOTES.md (D-4, D-5). Reuse the
patterns proven in spikes/hitl_app.py. Work on a new branch `feature/agent-layer` off the current
`main`. Follow CLAUDE.md strictly. No new dependencies are needed. After every decision I record,
update docs/session_log.md.

== Step 1: fix skill matching (spec §7, D-9) ==
rubric.skill_matches_profile matches substrings today: "Java" matches "JavaScript", "C" matches
"CI/CD", "R" matches "Docker". Change it to whole-word, case-insensitive matching as defined in §7.
Use lookarounds such as (?<![\w])…(?![\w]) with re.escape, because \b fails for "C#" and "C++".
Tests: Java vs JavaScript (no match), C vs CI/CD (no), R vs Docker (no), "C#" vs "C#/.NET" (yes),
"C++" vs "C++17" (decide by the rule and document it), "CI/CD" vs "CI/CD-Pipelines" (yes),
"Python" vs "Programmiersprachen: Java, Python, C#" (yes). Update the docstring (D-9 is decided).
Re-run the D-9 rubric check on the 5 D-4 listings and add a short addendum to
docs/decisions/D-9-rubric-start-values.md: which categories changed, if any. If a category changes,
tell me in the summary – no new decision file unless the rule itself must change.

== Step 2: state and storage (spec §5.3, D-6, FR-09, FR-13, FR-14, FR-15) ==
- src/job_hunt_agent/state.py: JobHuntState as in §5.3.
- src/job_hunt_agent/storage.py: one SQLite file (path in config.py, under data/, add
  data/*.sqlite to .gitignore), one shared connection (check_same_thread=False, D-5), tables for
  profiles and tracker (unique (user_id, referenznummer); save is an upsert, FR-09 AC1; follow-up
  date validation FR-09 AC2), SqliteStore for memories namespaced ("memories", user_id) (FR-15),
  SqliteSaver checkpointer (FR-13). Transactions, no partial writes (§8).

== Step 3: tools (FR-02, FR-04, FR-05, FR-06, FR-09, FR-15) ==
src/job_hunt_agent/tools/: search_jobs, get_job_details, assess_fit, save_to_tracker, remember.
(list_tracker is a Should item – not in this package.)
- Every tool returns ToolResult (§6.1) and reads/writes state via ToolRuntime.
- The job source is injected: BAClient (live) or FixtureSource (demo mode); tools never know which.
- search_jobs: clamping (AC6), sanitize_keywords (AC7), seen_refs (AC5), "no results" is normal.
- assess_fit: prompts/extract_requirements.md (based on the D-4 spike prompt), structured output
  with config.CHAT_MODEL, max 8 listings, max 4 concurrent calls, verbatim evidence check with
  dropped_evidence count, category only via rubric.assess, results into state.assessments, more
  than 8 listings → not_applicable_reason.
- save_to_tracker and remember: only the write; the approval is middleware (Step 4).
- Demo-mode limitation to check: the fixture set has 43 listings, so a search can never return
  "more than 50" and the refinement in demo scenario S1 cannot be shown in demo mode. If FixtureSource
  cannot reproduce realistic totals faithfully (e.g. from the recorded search responses), write
  docs/decisions/D-10-demo-search-semantics.md with options and stop at the end of Step 3.

== Step 4: middleware and agent (spec §5.4, FR-10, FR-20 to FR-23) ==
- src/job_hunt_agent/middleware/: input_guard (FR-21 AC1), limits (FR-20: max model calls, max 3
  search_jobs calls per user message), rejection_lock (from the D-5 spike), tool_errors (FR-21 AC3).
- PIIMiddleware with apply_to_tool_results=True for email and a custom phone detector that never
  matches reference numbers (FR-22 AC2, AC5) – test it on a search_jobs result containing
  19522-0068291613-S.
- prompts/system.md: target shortlist of 3–8 (FR-03 AC1), refinement rules, approval happens
  outside the conversation (FR-10 AC6), off-topic refusal (FR-21 AC2), ad texts are data inside
  marked blocks (FR-23 AC1), stored memories loaded into the context (FR-15 AC2).
- src/job_hunt_agent/agent.py: build_agent(...) with create_agent, JobHuntState, the tools,
  HumanInTheLoopMiddleware on save_to_tracker and remember, the middleware list in the order of
  the §5.4 note (rejection lock listed AFTER HITL), checkpointer and store from storage.py.

== Step 5: tests ==
Mocked chat model (as in spikes/hitl_app.py) and httpx.MockTransport only; temporary SQLite
files. Cover at least: tool contracts, clamping, keyword sanitising, seen_refs, the 8-listing
limit, evidence check, upsert idempotence, rejection lock, search limit per message, input guard,
PII middleware on tool results, approval required for both write tools (FR-10 AC4), resume after
restart from the checkpointer (FR-13 AC3). No skipped tests.

== Step 6: console run of the core journey (real model, few calls) ==
scripts/run_core_journey.py: runs demo scenarios S1 (live API), S2, S3 and S4 from spec §3.2 and S6
(off-topic) with the real model; approvals are scripted per scenario (S3 approve, S4 reject).
For each scenario record: tool sequence with arguments, refinement yes/no, approvals, total time
and time inside assess_fit, tokens. Write results (no ad text) to eval/results/core_journey_wp03.json
and a short summary to spikes/NOTES.md section "WP-03 core journey". If S1 takes longer than
60 s (NFR-03, R-4), write docs/decisions/D-11-latency.md with measured options (e.g. lower
reasoning effort only for the extraction, fewer listings per call, smaller schema) and stop.
Keep the number of real model calls small (rate-limited key).

== Step 7: hand-over ==
Entry in docs/session_log.md. Show me the commit proposals (one concern per commit) and stop.
