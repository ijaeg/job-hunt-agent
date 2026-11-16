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

---

## Addendum 1 (2026-11-16, selection review)

Selection approved by Ingo (2026-11-16) with two changes; record the approval and the final rule in eval/fit_set.yaml:
1. Fixed allocation instead of proportional: temp_agency 3 (1 dev / 2 test), skill_match 9 (3 dev / 6 test), no_skill_match 8 (4 dev / 4 test). Reason: temp-agency listings are excluded by code from a structured field alone and would inflate agreement without testing the extraction.
2. At most 2 listings per employer across the whole set.
Keep seed 1300 and the shuffle-then-take procedure; redraw within the strata where the employer cap removes a listing. Show me the new list once more, then continue with Part B without waiting for another approval if the list follows these rules.

---

## Addendum 2 (2026-11-16, coach review of the labelling guide)

Fix before Ingo starts labelling:
1. docs/labelling_guide.md, location/remote: remove "unknown". Spec §7 has no "unknown" for this dimension; a missing distance counts as within the radius (as rubric.py does).
2. docs/labelling_guide.md, employment type: remove "partly". Spec §7 has no "partly" for this dimension.
3. Add a short section "Which location the distance refers to": the distance shown is the distance from the location of the search the listing came from (e.g. München for the München listings), not from the profile's location; a location named in the request overrides the profile (FR-01 AC4). Show the search location next to the distance in scripts/label_fit.py, so Ingo sees it while labelling.
4. The labelling tool's verdict choices must match: location/remote without "unknown", employment type without "partly".
5. Record in eval/fit_set.yaml (or docs/labelling_guide.md) that WP-14 must compute the app's assessment with the same distance and search location that the tool shows.
Update tests, run all checks, propose the commit.

---

## Addendum 3 (2026-11-16, data check after labelling)

Data check for the labelled fit set (no app run, no rubric, no model call - keep the labelling blind): for every listing in eval/fit_set.yaml whose location_remote_verdict in eval/fit_labels.csv is "partly" or "not_met", list: referenznummer, title, location, distance_km and the search location it refers to (as scripts/label_fit.py shows it), remote_type, remote_percent, and any sentence in the description with remote-work wording (Homeoffice, Home-Office, mobiles Arbeiten, mobile Arbeit, remote, hybrid, Telearbeit, ortsunabhängig), or "none found". Change nothing.

Outcome (Ingo, 2026-11-16, entered by the coach): 9 location/remote verdicts corrected in eval/fit_labels.csv under the rule "within radius or no distance + any remote wording (incl. 'nach Vereinbarung') -> met; fully remote -> met; no remote wording -> partly", each with a note; overall categories unchanged. 19522-0068291613-S: location met (Homeoffice nach Vereinbarung). 15548-1650634-1-S stays excluded by Ingo's decision, with a note on the contradicting location field and distance.
