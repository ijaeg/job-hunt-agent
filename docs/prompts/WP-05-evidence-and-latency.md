# WP-05: German evidence on the cards (D-11) and S1 latency measurement (D-12)

Related: FR-05 AC4, FR-07 AC1, FR-08 AC2, NFR-03, spec §6.3, D-11, D-12

## Step 0
Save this prompt verbatim as docs/prompts/WP-05-evidence-and-latency.md. We are on branch feature/evidence-and-latency. docs/decisions/D-12-latency.md is new and untracked - include it in the first commit together with the prompt file.

## Part A: D-11, Option 1 (decided 2026-11-09)
1. In models.py add a model MatchEvidence (name, evidence_de, evidence_en) and change FitAssessment.matches and FitAssessment.gaps to list[MatchEvidence]. rubric.assess() builds them from requirements.skills.
2. Before changing anything, find every consumer of matches/gaps (code, tests, prompts/system.md, prompts/extract_requirements.md) and list them in your report. The model sees FitAssessment as JSON in the assess_fit ToolMessage, so the follow-up answers (FR-08) depend on this shape too.
3. Cards (FR-07 AC1): top 3 matches show the German quote and the English translation; gaps the same. Remove the TODO(D-11) in ui_view.py.
4. Existing SQLite files under data/ hold checkpoints with the old string shape. Check whether an old thread still loads in app.py. If not, do not write migration code: report which files are affected and propose deleting them (they are local dev data).
5. Do not edit PRODUCT_SPEC.md. In your report, propose the exact new wording for spec §6.3 (FitAssessment) - the coach updates the spec.
6. Tests: update test_rubric, test_tools_assess, test_ui_view, test_app; add a test that a card shows both the German quote and the English translation.
7. Real-model check (Checks #2): one demo run of S1 followed by S2 ("Why is #3 only partial?"). S2 must be answered without a new tool call and must cite evidence. Record it in eval/results/wp05_s1_s2.json.

## Part B: D-12, Option 1 (decided 2026-11-09)
Do this after Part A, on the final code.
1. Run S1 in demo mode 5 times ("Find Softwareentwickler jobs in München.", a fresh thread per run, real model, settings from config.py unchanged). Reuse scripts/ui_smoke_wp04.py (add a --runs option) or a successor - no duplicated logic.
2. Per run, record: elapsed seconds, deduplicated tool sequence, assess_fit extraction seconds (from its notes), number of listings assessed, card count, token usage. Summary: median, mean, minimum, maximum. Write eval/results/latency_s1_wp05.json and a short section in spikes/NOTES.md, with numbers taken from the result file.
3. Do not tune anything. If the median or the maximum is above 60 s, append a section "Round 2 options" to D-12 (2-3 levers, e.g. lower reasoning effort for the extraction only, fewer listings per assess_fit call, smaller extraction schema), each with the expected effect and what it would change in the fit evaluation (§9.3), plus a recommendation - then stop. Ingo decides.

## Done when
- All checks of CLAUDE.md "Checks before hand-over" pass and are reported with numbers (pytest, ruff check, ruff format --check, mypy src app.py scripts).
- Your report states the S1 latency result (median, maximum, budget met yes/no) explicitly in the message to Ingo, not only in the session log.
- docs/session_log.md has an entry.

## Commits
Propose small commits, each with file list, summary and message, and wait for approval every time. Suggested split: prompt file + D-12; MatchEvidence + rubric + tests (D-11); cards + UI tests; S1/S2 check + latency measurement + NOTES + session log.

---

## Addendum 1 (2026-11-09, after coach review)

Related: FR-01 AC4, FR-03 AC3, FR-08 AC2, NFR-03, D-12

Before any commit:
1. FR-01 AC4: in 2 of 5 latency runs the agent stopped after search_jobs and asked about the location because the request (München) differs from the profile (Hamburg). Add a rule to prompts/system.md: a location named in the request overrides the profile for this search; do not ask. Real-model check afterwards.
2. Tool sequences must be recorded per tool call (deduplicated by tool_call id only), not collapsed by name - the report must show how many search_jobs calls ran (refinement, FR-03 AC3).
3. Re-run the 5-run latency measurement after fix 1 and replace latency_s1_wp05.json. Report median/max over completed runs, the completion rate (runs reaching assess_fit) and the refinement rate. Update the D-12 results section and NOTES from the new file.
4. FR-08 AC2: in wp05_s1_s2.json the S2 answer says "your profile lists Python, FastAPI and PostgreSQL" and treats Java as a gap, but profile_alex.yaml contains Java, Docker and CI/CD. Check the stored FitAssessment of 10001-1003863378-S (did the rubric match Java?) and find why the explanation contradicts the profile. Report cause and a proposed fix; do not change the rubric.
5. Ingo approves deleting the stale local data/*.sqlite files with the old FitAssessment shape. List them before deleting.
Then run all checks and propose the commits.

---

## Addendum 2 (2026-11-09)

Related: FR-08 AC2, FR-20 AC1

1. Ingo approves the prompt fix proposed in spikes/NOTES.md "WP-05 Addendum 1 #4". Apply it to prompts/system.md, then re-run scripts/s1_s2_check.py on a fresh thread (real model) and confirm in eval/results/wp05_s1_s2.json that the S2 answer neither calls a matched skill a gap nor shortens the profile's skill list.
2. FR-20 AC1: latency run 2 (latency-s1-wp05-2) shows 4 search_jobs calls, the limit is 3 per message. Check from that run's checkpoint whether the 4th call was refused by the tool (not_applicable_reason) and report the exact tool result. If it actually ran a search, stop and report - do not fix.
Then run all checks and propose the commit(s).
