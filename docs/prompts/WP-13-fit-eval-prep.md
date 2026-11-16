Date: 2026-11-16
Related: spec §7, §9.1, §9.3, NFR-09, invariant 6, D-9, D-20

# WP-13: Preparing the fit evaluation (labelled set)

Related: spec §7, §9.1, §9.3, NFR-09, invariant 6, D-9, D-20

## Step 0
Save this prompt verbatim as docs/prompts/WP-13-fit-eval-prep.md. We are on branch feature/fit-eval-prep. docs/decisions/D-20-labelling-design.md (new, from the coach) belongs in the first commit together with the prompt.

## Decided in advance (do not re-decide)
- D-20: Ingo labels blind (the app's category and verdicts are never shown to him before he has labelled). Per listing he gives the overall category (strong / partial / poor / excluded) and one verdict per rubric dimension (skills, location/remote, seniority, language, employment type: met / partly / not met / unknown), each with an optional short note. Profile: data/samples/profile_alex.yaml. Rules: spec §7 exactly as it stands (D-9 start values).
- 20 listings from the committed fixture set (data/samples/fixtures/listings.json, real listings only, not the 3 crafted ones), split 8 development / 12 test (spec §9.1). The test set is never used for tuning (invariant 6).

## Stop rules
1. Planned stop: after the selection (Part A), show Ingo the list and stop. Build nothing else until he has approved it (CLAUDE.md: the content of an evaluation set is Ingo's decision).
2. If anything else turns out to need a decision, stop at that point, write the decision file and report.

## Part A: Selection
1. Data check (Checks #4): the selection must contain listings that can plausibly reach each category for the Alex profile - at least a few with Python or Java in the text, some with a temp-agency flag or other hard exclusion, some clearly unrelated. Report the counts available in the fixture set per feature before selecting. If the set cannot cover "strong" at all, say so and stop.
2. Selection rule, without running the app or the model: stratify by features visible in the data alone (e.g. Python/Java mentioned, temp agency flag, distance known, low_evidence, source search), then pick at random with a fixed seed. Split 8/12 at random with a fixed seed, keeping the strata balanced as far as possible.
3. Write eval/fit_set.yaml: per listing referenznummer, title, employer, stratum, set (dev/test); seed and rule in the header. Then stop (stop rule 1).

## Part B: Labelling tool (after approval)
1. scripts/label_fit.py, a small Streamlit app run with `uv run streamlit run scripts/label_fit.py` (not part of the product app, not under pages/). It shows one listing at a time: cleaned ad text, the structured fields (distance, remote, contract, full-time, temp agency), the Alex profile, and the §7 rules in plain words. Inputs: overall category, five dimension verdicts, notes. Saves to eval/fit_labels.csv after every listing (resumable), with a timestamp per row. It never shows the app's own assessment.
2. A short labelling guide docs/labelling_guide.md: the §7 rules with one example per verdict, how "unknown" differs from "not met", and that hard exclusions (FR-06) decide "excluded" before anything else.
3. Tests: label_fit.py's pure helpers (loading the set, writing and resuming the CSV) with unit tests; an AppTest that the tool renders a listing and saves a row, and that no assessment value appears on the page.

## Done when
- All checks of CLAUDE.md "Checks before hand-over" pass, with numbers (mypy including scripts).
- docs/session_log.md has an entry.
- Ingo can start labelling with one command; the report gives it.

## Commits
Propose small commits and wait for Ingo's approval each time. Suggested split: prompt + D-20; fit_set.yaml (after approval); labelling guide; labelling tool + tests + session log.
