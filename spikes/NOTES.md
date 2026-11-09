# Spike notes

Record of the spike results. Feeds the product spec.

## D-1 Job board API (Thu 2026-11-05)

Script: `spikes/ba_api_spike.py`. Raw responses in `spikes/fixtures/` (local only, see D-3); aggregated results in `spikes/fixtures/spike_report.json`.

### Setup

- Base URL `https://rest.arbeitsagentur.de/jobboerse/jobsuche-service`, header `X-API-Key: jobboerse-jobsuche` (public client ID of the official job search web app, not a secret).
- Five searches (Python/AI/Java/ML/software developer in Hamburg, Berlin, Munich), 40 job details, two error cases, 52 calls in total, 0.5 s pause between calls.

### Results

| Question | Result |
|---|---|
| Search works (v6 `/pc/v6/jobs`) | yes, HTTP 200 for all searches |
| Response shape | results in `ergebnisliste` (not `stellenangebote` as in older docs); ID field `referenznummer`; `maxErgebnisse` is an integer; with 0 results the list key is missing |
| Page size | default 25 results per call |
| `veroeffentlichtseit` (days since publication) | works: 1 day → 1, 7 days → 3, 28 days → 4 results (Python developer, Hamburg) |
| `zeitarbeit=false` | works: 4 → 1 result; matches the facet `zeitarbeit` (`true: 3`, `false: 1`) |
| Pagination | **not verified** – the test search had only 4 results; to be covered by the `search_jobs` tests |
| Details (v4 `/pc/v4/jobdetails/{base64(referenznummer)}`) | 40/40 HTTP 200; v3 fallback never needed |
| Full text | `stellenangebotsBeschreibung` in 40/40; median 4,200 characters, max 9,712; ads with `externeURL` (11/40) partly only a teaser (min 284 characters) |
| Wrong API key | HTTP 403, empty body |
| Unknown reference number | HTTP 404, `{"messages": [{"code": "STELLENANGEBOT_NICHT_GEFUNDEN"}]}` |
| Latency | median 54 ms, max 125 ms (52 calls) |

### Structured fields useful for the fit assessment

| Field | Where | Coverage (40 details) | Use |
|---|---|---|---|
| `istArbeitnehmerUeberlassung` | details | true 7, false 26, missing 7 | hard exclusion "temporary agency work" |
| `istPrivateArbeitsvermittlung` | details | true 1, false 32, missing 7 | hint: private recruiter |
| `homeofficetyp` / `homeofficeprozent` | search + details | set in 19/40 (`ANGABE_IN_PROZENT` 11, `NACH_VEREINBARUNG` 8) | remote dimension; missing = "not mentioned", not "not met" |
| `entfernung` | search | always | distance in km from the search location |
| `gehaltsspanneVon` / `gehaltsspanneBis` | search + details | 8/29 search results | salary, if stated |
| `arbeitszeitVollzeit`, `befristungInMonaten`, `vertragsdauer` | search + details | mostly | employment type |
| `stellenlokationen[].breite/laenge` | search + details | always | coordinates (possible later: commute time) |

### Decision

- **Data source: Job board API v6 search + v4 details.** Reachable, fast and stable enough for the agent; the demo mode with recorded responses stays required because the API is not officially guaranteed.
- **Hard exclusion of temporary agency work by code, not by the LLM:** search with `zeitarbeit=false` when the user excludes it; in addition check `istArbeitnehmerUeberlassung` in the details. Missing value = "unknown", shown as such.
- **Fit dimensions from structured fields where available** (remote, distance, employment type, salary); the LLM only extracts what is in the free text (skills, seniority).
- **"No results" is a normal response**, not an error: the tool must distinguish it from 403/404/timeouts.
- Latency is not a concern for the API; the LLM calls in `assess_fit` will dominate.

## D-2 Ad texts as LLM input (Thu 2026-11-05)

- Full texts are long (median 4,200 characters). Sending 10–20 of them to the LLM per search costs time and tokens → limit the number of ads assessed per run and keep the extraction schema small.
- Ads with an external link may only contain a teaser → `assess_fit` must report low evidence instead of guessing.

## D-3 Personal data in ad texts (Thu 2026-11-05)

- The API has **no separate contact fields**; contact data is inside the free text.
- The spike masked e-mail addresses and phone numbers with regex. **Names of contact persons remain** (5 of 40 ads, e.g. "bei Frau …", a signature with name and address, a name before a masked phone number).
- Names cannot be detected reliably with regex.

### Decision

- **Raw responses are not committed** (`.gitignore`: `spikes/fixtures/*`, except `spike_report.json`). Reasons: third-party personal data, and the ad texts are content of employers and the Federal Employment Agency.
- Demo-mode and evaluation fixtures are built later as a **cleaned set** (names replaced, e-mail/phone masked), checked before commit.
- Consequence for the spec: PII handling must also apply to **tool results** (`PIIMiddleware(..., apply_to_tool_results=True)`), with custom detectors for phone numbers; contact names need a separate approach (e.g. drop the contact section of the ad before it reaches the LLM).

## D-4 Model and extraction quality (Thu 2026-11-05)

Script: `spikes/extraction_check.py`. Raw outputs (contain ad text) in `spikes/fixtures/d4/` (local only, see D-3); aggregated numbers in `spikes/d4_results.json`.

### Setup

- Models compared: `openai/gpt-5-mini` (spec default) vs. `anthropic/claude-haiku-4.5`, both via OpenRouter with provider routing `{"data_collection": "deny", "zdr": true}` — **never relaxed**.
- 5 listings from `spikes/fixtures/details/`, chosen for length spread (284–9,712 chars) and special cases: a 284-char teaser with `externeURL`, a temporary-agency listing (`istArbeitnehmerUeberlassung: true`) with a contact name in the free text, and one with a missing `istArbeitnehmerUeberlassung`.
- Ad-text cleaning before sending (spike approximation of FR-22 AC1): mask e-mail/phone, drop lines starting with "Frau"/"Herr " + a name, drop contact-header lines ("Kontakt:", "Ansprechpartner:").
- Each model × listing ran twice (structured extraction, `with_structured_output(JobRequirements)`); each model got the 3 fixed tool-calling prompts once. 26 calls total (budget: ~40).

### Results — extraction (10 calls per model)

| Metric | openai/gpt-5-mini | anthropic/claude-haiku-4.5 |
|---|---|---|
| Valid `JobRequirements` | 10/10 | 10/10 |
| ZDR endpoint available | yes (no routing error) | yes (no routing error) |
| Requirements per listing (min/mean/max) | 7 / 12.6 / 19 | 6 / 10.6 / 20 |
| Evidence verbatim-substring share | 139/143 = **97.2 %** | 118/125 = **94.4 %** |
| Latency (s, min/mean/max) | 9.5 / 15.8 / 22.0 | 16.3 / 24.5 / 47.8 |
| Input tokens (mean) | 1,481 | 2,503 |
| Output tokens (mean) | 1,761 | 4,496 |

### Results — tool calling (3 prompts per model)

| Prompt | Expected | gpt-5-mini | claude-haiku-4.5 |
|---|---|---|---|
| "Python jobs in Hamburg, no temp agencies" | `search_jobs`, location Hamburg, `exclude_temp_agency=true` | correct | correct |
| "AI roles in Berlin from this week" | `search_jobs`, location Berlin, `published_within_days≤7` | correct | correct |
| "What's the weather?" | no tool call | correct (no call) | correct (no call) |

Both models: 3/3 correct. For "AI roles in Berlin", `gpt-5-mini` expanded "AI" into a long OR-list of synonyms (`AI OR "Artificial Intelligence" OR "Machine Learning" OR ML OR Data Scientist OR "Deep Learning"`), while `claude-haiku-4.5` searched for `AI` only (`spikes/d4_results.json`). Whether the BA API supports this syntax is unverified; FR-02 AC7 requires plain keywords and removes operators in code. *(Corrected 2026-11-06: the first version of this paragraph had the two models swapped.)*

### Ad-text cleaning example (contact-name listing, `13545-dztbhcdpfnhf7dsr-s.json`, temporary-agency listing)

Before → after (signature block only, name redacted — the real name and the rest of the ad text stay only in the gitignored raw output, D-3):

```
before: ...Ihr Team von Dock 22\n\nHerr [NAME]\nDock 22 GmbH\nAm Sandtorkai 23\n20457 Hamburg\n\nTelefon: [TELEFON]...
after:  ...Ihr Team von Dock 22\n\nDock 22 GmbH\nAm Sandtorkai 23\n20457 Hamburg\n\nTelefon: [TELEFON]...
```

The "Herr [NAME]" line was dropped; 1 name line removed, 0 e-mails/phones found in this particular listing (already masked as `[TELEFON]`/`[EMAIL]` by the D-1 spike's own cleaning). Confirms D-3: the e-mail/phone regex works, but a real production `pii.py` still needs the line-based name removal — a generic name-pattern regex alone would have missed this because the name sits on its own signature line, not inline.

### Facts for the decision

- Both models answer through OpenRouter with ZDR provider routing intact — no fallback to relaxed routing was needed for either.
- `gpt-5-mini` is faster (~1.5× lower mean latency), cheaper (fewer input and far fewer output tokens), and has a higher evidence-verbatim rate on this small sample.
- Both models called the right tool with correct, usable arguments on all 3 prompts and correctly avoided a tool call for the off-topic question.
- Sample is small (5 listings × 2 runs); see `docs/decisions/D-4-model.md` for the recommendation.

## D-5 Approval with interrupt and resume in Streamlit (Thu 2026-11-05)

Script: `spikes/hitl_app.py` (the prototype), `spikes/test_hitl_app.py` (automated checks, run with `uv run pytest spikes/test_hitl_app.py`, not part of the package's coverage-tracked suite). Two dummy tools, `find_item` (read) and `save_item` (write, gated), `HumanInTheLoopMiddleware` + a custom `RejectionLockMiddleware`, `SqliteSaver` on `spikes/fixtures/d5.sqlite` (gitignored, tests use their own temp file via `HITL_DB_PATH`).

### 1. Does the interrupt survive a Streamlit rerun and an app restart?

**Yes to both**, and the mechanism is simpler than expected: the pending interrupt is **not** Streamlit session state at all — it lives entirely in the checkpointer. Every script run calls `agent.get_state(config).interrupts`, which LangGraph reconstructs from the last saved checkpoint. Proven two ways:

- `test_rerun_keeps_the_pending_interrupt`: a second `AppTest.run()` with no new input still shows the same 3 buttons.
- `test_restart_resumes_the_same_thread_from_sqlite`: calls `get_connection.clear()` (the `st.cache_resource` cache) before building a second, independent `AppTest` — forcing a genuinely fresh `sqlite3.Connection` object, not a reused Python object. The interrupt is still there, read straight from the file. Confirmed again outside `AppTest`, with two separate `sqlite3.connect()` calls to the same file in the same process (see the smoke test transcript below) and with the **real** model (one short run, see §4).

### 2. After reject, does the model propose the same call again? Is it interrupted again?

Two different answers depending on who is asked:

- **The real model, well-prompted, does not retry on its own.** HITL's own rejection message to the model is explicit: *"The tool was not executed. Do not retry this tool call unless the user explicitly requests it."* In the one real-model run (§4) the model honoured this.
- **If a model (or a bug) does retry with the identical call, our `RejectionLockMiddleware` drops it before any second interrupt.** Proven with the scripted model deliberately re-proposing the exact same `save_item` call right after a reject (`test_repeated_proposal_after_reject_is_dropped_without_a_second_interrupt`): zero buttons render on the next turn, and the chat shows *"(Not repeating save_item: this exact action was already rejected in this conversation.)"* instead.

Minor finding for the real system prompt (`prompts/system.md`, FR-21/FR-10): the raw model is reluctant to call a tool whose docstring says "gated by approval" — on a first attempt it asked the user for permission itself instead of calling the tool. Telling it explicitly that approval happens automatically outside the conversation ("call the tool directly; a human reviewer approves or rejects it afterward") fixed this. The production system prompt needs this instruction so the agent proposes write actions instead of asking first.

### 3. Rejection-lock middleware: hook and position relative to HumanInTheLoopMiddleware

**Non-obvious finding, the main point of this spike.** Reading `langchain/agents/factory.py`:

- `before_model` hooks run in **forward** middleware-list order (first-listed runs first) — `entry_node = middleware_w_before_model[0].name + ".before_model"`.
- `after_model` hooks run in **reverse** middleware-list order (last-listed runs first) — `graph.add_edge("model", f"{middleware_w_after_model[-1].name}.after_model")`.

So to have the rejection lock's `after_model` run **before** `HumanInTheLoopMiddleware`'s `after_model` (and strip a repeated call before HITL would re-interrupt on it), `RejectionLockMiddleware` must be listed **after** `HumanInTheLoopMiddleware` in `middleware=[...]` — the reverse of the intuitive order, and the reverse of the numbering in spec §5.4 (#4 before #5). The working variant:

```python
middleware = [
    HumanInTheLoopMiddleware(interrupt_on={"save_item": True}),
    RejectionLockMiddleware(),  # listed AFTER HITL - its after_model runs FIRST
]
```

`RejectionLockMiddleware` itself (`spikes/hitl_app.py`):

- `before_model`: scans the full message history for HITL's own reject `ToolMessage`s (`status == "error"`, content starting with `"User rejected the tool call for"`), looks up the original call's name+args by `tool_call_id`, and records a stable hash of `(name, args)` into state field `rejected_actions` (spec §5.3).
- `after_model`: on the newest `AIMessage`, strips any tool call whose `(name, args)` hash is already in `rejected_actions`, replacing the message (same `id`, so the state reducer updates it in place rather than appending) with the remaining tool calls plus an explanatory note in `content`. If nothing is left to strip, returns `None` and HITL proceeds normally.

Dropping the tool call entirely (not just answering it with a `ToolMessage`) is required: HITL's `after_model` decides whether to interrupt purely from `AIMessage.tool_calls`, with no check for an existing answer, so leaving the call in place - even if answered - would still trigger a second interrupt.

### 4. SQLite connection handling across Streamlit reruns

One `sqlite3.connect(path, check_same_thread=False)` behind `@st.cache_resource` (keyed by the path string), built once and reused by every rerun in the same process; `SqliteSaver` serialises access internally, so `check_same_thread=False` is safe (per the langgraph docstring). Simulating a restart means clearing that specific cache (`get_connection.clear()`), not restarting the process - confirmed this still reads the same pending interrupt from the file.

### 5. For D-6: SQLite-backed LangGraph store?

**Yes - already available**, no extra dependency: `langgraph.store.sqlite.SqliteStore`, shipped inside `langgraph-checkpoint-sqlite` (already an approved dependency, no new package). Confirmed working directly:

```python
from langgraph.store.sqlite import SqliteStore

with SqliteStore.from_conn_string("memories.sqlite") as store:
    store.setup()
    store.put(("memories", "user1"), "pref1", {"kind": "preference", "value": "remote only"})
    store.search(("memories", "user1"))  # -> list of items, namespace/key/value
    store.get(("memories", "user1"), "pref1")
```

Namespaced by a tuple (e.g. `("memories", user_id)`), keyed items, with `put`/`get`/`search`/`delete` and even an optional `TTLConfig`. See `docs/decisions/D-6-memory-storage.md` for the recommendation.

### Automated tests (`spikes/test_hitl_app.py`, `streamlit.testing.v1.AppTest`, scripted model)

| Test | Proves |
|---|---|
| `test_approve_runs_the_tool` | Approve -> tool executes (FR-10 AC1) |
| `test_reject_does_not_run_the_tool` | Reject -> tool never runs, user sees why |
| `test_repeated_proposal_after_reject_is_dropped_without_a_second_interrupt` | The rejection lock (point 3 above) |
| `test_rerun_keeps_the_pending_interrupt` | Point 1, rerun case |
| `test_restart_resumes_the_same_thread_from_sqlite` | Point 1, restart case |
| `test_find_item_is_never_gated` | A read-only tool never interrupts |

All 6 pass (`uv run pytest spikes/test_hitl_app.py`, ~1.4 s, no network call, `HITL_FAKE_MODEL=1`).

### One real-model run (§9.5-style trace, thread `real-model-smoke3`)

With a system prompt telling the model approval happens automatically outside the conversation:

```
SystemMessage  "...call save_item directly...a human reviewer approves...afterward..."
HumanMessage   "Please save the gadget with note 'looks interesting'."
AIMessage      tool_calls=[save_item(name=gadget, note="looks interesting")]
  -> interrupt -> Command(resume={"decisions":[{"type":"approve"}]})
ToolMessage    {"saved": true, "name": "gadget", "note": "looks interesting"}
AIMessage      'Done — I saved "gadget" with the note "looks interesting."'
```

Confirms the whole flow (propose -> interrupt -> approve -> execute -> model continues) against the real `openai/gpt-5-mini` model, not just the scripted one.

### Manual test checklist

See `docs/manual_tests/D-5-checklist.md`.

## D-8 preparation: pii_check.py on the 40 raw D-1 listings (2026-11-06)

Script: `spikes/pii_check.py`. Per-listing detail (still contains ad text,
gitignored): `spikes/fixtures/pii_check.json`. Runs the real
`job_hunt_agent.pii.clean_ad_text` - the same function the BA client and the
cleaned fixture set (D-8) will use - over all raw listings from the D-1 spike.

- Listings checked: 40
- E-mail addresses masked: 0
- Phone numbers masked: 0
- Contact/name lines removed: 186
- Listings with a still-suspicious line after cleaning: 0

**Goal met: 0 remaining contact names** after cleaning.

## WP-03 core journey: real-model console run (2026-11-06)

Script: `scripts/run_core_journey.py`. One continuous thread (`core-journey-wp03`), live
BA API (`job_source=BAClient`, D-10), real model (`openai/gpt-5-mini`, reasoning effort
`low`). Full per-scenario record (no ad text): `eval/results/core_journey_wp03.json`.

Per-scenario tool calls are the **new** calls that scenario added to the thread (a script
bug recorded the full cumulative history instead; corrected post-hoc by diffing, not by
re-running - see the `note` field in the JSON file for the exact fix).

| Scenario | Elapsed (s) | New tool calls | Tokens (in/out, cumulative) |
|---|---|---|---|
| S1 | 30.6 | search_jobs, get_job_details ×6, assess_fit | 22,467 / 1,138 |
| S2 | 7.5 | (none - answered from state) | 32,731 / 2,074 |
| S3_propose | 2.8 | save_to_tracker (interrupted) | 43,772 / 2,289 |
| S3_approve | 1.9 | (resume; tool executes, no new proposal) | 55,036 / 2,358 |
| S4_propose | 2.1 | remember (interrupted) | 66,386 / 2,412 |
| S4_reject | 2.6 | (resume; tool does not execute) | 77,824 / 2,610 |
| S6 | 3.2 | (none - off-topic refusal) | 89,360 / 2,732 |

**Confirmed correct, verified directly against the SQLite file (not just the model's own
words) after the run:**
- S3 (FR-10 AC1): `save_to_tracker` ran only after approval - the tracker table has
  exactly the one entry (NTT DATA, Senior AI Engineer, `follow_up_date` 2026-11-13, the
  user's note).
- S4 (FR-10 AC3): the rejected `remember` call never persisted - the memory store is
  empty (`store.search(("memories", "alex")) == []`).
- S2 (FR-08 AC1): the follow-up question added zero new tool calls, confirming it was
  answered from the stored assessment, not a new search/assess_fit.
- S6 (FR-21 AC2): the off-topic question added zero new tool calls and got a short
  refusal that steered back to job search.

**S1 refinement was NOT shown this run:** exactly one `search_jobs` call; the agent did
not narrow or broaden. Either the real total for "Python AI" in Hamburg over 14 days
genuinely did not cross the ">50 narrow" or "<3 broaden" thresholds (plausible - D-1's
own spike numbers for similarly specific queries were in the single-to-low-double
digits), or the model simply judged the ~11 results reported in its final answer "good
enough" without the agent needing to retry. FR-03 AC3 ("the trace of demo scenario S1
shows at least one refinement") is **not yet demonstrated** by this run; a follow-up run
with a deliberately broad query (e.g. a generic title with no city restriction, or a
very short `published_within_days`) is needed before using S1 as the refinement demo
for the review.

**Minor wording observation (not a code defect, verified against the DB above):** after
the S4 rejection, the model's own summary said "the tracker call failed" when it meant
the `remember` (exclusion) call - confusing phrasing, worth tightening in
`prompts/system.md` later, but the actual behaviour (nothing persisted) was correct.

**Latency (NFR-03, R-4):** S1 took 30.6 s total, of which `assess_fit`'s extraction step
(6 listings, 4 concurrent) was 14.0 s - well within the 60 s budget. No D-11 decision
needed this run.

**Found and fixed during this work package, before this run:** `runtime: ToolRuntime[...]
| None = None` on every tool silently broke the framework's injected-argument detection
(`_is_injected_arg_type` only recognises the bare/un-wrapped type), so `runtime` stayed
in the model-facing JSON schema LangChain builds for `bind_tools()` - invisible against
every scripted-model test (which never calls real `bind_tools()`), but fatal against the
real `ChatOpenAI.bind_tools()` on the very first live call. Fixed by making `runtime` a
required, keyword-only parameter (`*, runtime: ToolRuntime[...]`) with no default, the
documented pattern. A structural argument for always doing at least one real-model smoke
run before considering tool-layer work done, not just scripted-model tests.

## D-10 Option 4 follow-up: S1 re-run in demo mode, "Softwareentwickler" / München (2026-11-06)

Decision D-10 (Option 4, Ingo): `FixtureSource` now replays the 5 recorded D-1 search
totals exactly (`data/samples/fixtures/recorded_searches.json`, query params + total +
reference numbers only, no ad text). Re-ran S1 in demo mode with the real model, same
agent/thread pattern as the earlier live run, to confirm the narrowing direction now
fires.

**Turn 1** - "Find Softwareentwickler jobs in München.": one `search_jobs` call
(keywords "Softwareentwickler", location "München", default radius 25 km / 28 days) -
`FixtureSource` matched the recorded query exactly and reported **total: 103** (the
real D-1 number, not the fixture set's own ~6-result ceiling). The model recognised
"too many results" and asked the user which dimension to narrow (tech stack, seniority,
employment type, remote, radius, recency) rather than guessing - it did not
autonomously retry within this turn.

**Turn 2** - "Java, Senior level please.": two `search_jobs` calls, both now outside
the recorded-query match (different keywords, so the normal filter path over the 43
committed listings applies): "Java Senior Softwareentwickler" (total 0), then "Senior
Java Entwickler" with `published_within_days` widened 28->60 (total 0). Both returned
zero because `FixtureSource`'s keyword match requires every term present in
title+employer, and none of the 3 München-tagged real listings contain "Senior" and
"Java" and "Entwickler"/"Developer" together under that exact wording - a known,
separate limitation of the fixture search's simple AND-of-terms matching, not a D-10
or replay defect.

**Conclusion:** D-10 Option 4 works as intended - demo mode now genuinely exercises
*both* refinement directions in one conversation: `total=103` (">50, narrow") on turn
1, followed by two re-tries with different, more specific keywords and a widened
publication window on turn 2 (the model's own reaction to two 0-result searches,
matching FR-03 AC1's "< 3 results -> broaden" instinct even though here it was 0, not
literally reported as "<3" text - the agent treated "no results" as the broaden
trigger). No results were ultimately found for the narrowed query - an honest fixture
limitation (worth revisiting if a cleaner demo ending is wanted later), not hidden here.
3 total `search_jobs` calls across the two-turn conversation confirm FR-03 AC3 ("the
trace of demo scenario S1 shows at least one refinement") is now demonstrable in demo
mode, not only against the live API.

## D-10 addendum: corrupted referenznummern fixed, autonomous narrowing re-run (2026-11-06)

Full write-up: `docs/decisions/D-10-demo-search-semantics.md` § "Addendum". Summary:

**Fix 1:** `recorded_searches.json` had 3 corrupted reference numbers (the raw D-1
search responses were scrubbed by the same context-free phone regex as the details
responses). `scripts/build_fixtures.py::recover_referenznummer()` now matches every
referenznummer against `listings.json` (prefix/suffix around the `[TELEFON]` artifact
for a corrupted one), never trusts the scrubbed search file directly, and drops any
reference never detail-fetched rather than keeping an unverifiable guess.

**Fix 2:** `prompts/system.md` now tells the model to narrow *autonomously*, using the
profile, before asking the user; a new `LoadProfileContextMiddleware` makes the profile
actually visible to the model (it was not, before). `FixtureSource` gained a
narrowing-match path: a query that keeps a recorded query's keywords as a subset is
filtered to that recorded search's own referenznummern (restricted to `listings.json`) -
honestly 0 if none overlap, never invented either way.

**Re-run, "Find Softwareentwickler jobs in München.", demo mode, real model:**

| # | search_jobs call | total |
|---|---|---|
| 1 | Softwareentwickler / München, 25 km, 28 days | 103 (exact replay) |
| 2 | Senior Softwareentwickler Python FastAPI / München, 25 km, 28 days (narrowed) | 0 |
| 3 | Softwareentwickler Python Java Docker PostgreSQL CI/CD / München, 25 km, 60 days | 0 |

The agent narrowed on its own across 2 attempts (using profile skills + seniority),
within the 3-call limit, without asking first - then stopped and asked the user,
correctly diagnosing that the Hamburg-based profile radius wasn't helping a München
query. It never reached `get_job_details` or `assess_fit` for this query.

**Honest conclusion:** this is a data-coverage gap, not a logic bug. München's recorded
search's own 25 reference numbers have zero overlap with the 40 detail-fetched listings
in `listings.json` (the original D-1 spike's 40-detail budget was spent on the 4 other
searches, which run before München in `spikes/ba_api_spike.py`'s list). No narrowing of
*that specific recorded search* can honestly return anything but 0. The mechanism itself
(autonomous, profile-driven narrowing; honest non-invented totals) works exactly as
specified - confirmed by the trace above - but "Softwareentwickler"/München specifically
cannot demo the full "narrow -> details -> assess_fit" chain with the current fixture
data. "AI Engineer"/Hamburg (24 of its listings are in `listings.json`) is a better
candidate if a guaranteed non-zero narrowed result is wanted for the review.

## D-8 preparation: pii_check.py on the raw D-1 listings (2026-11-06)

Script: `spikes/pii_check.py`. Per-listing detail (still contains ad text,
gitignored): `spikes/fixtures/pii_check.json`. Runs the real
`job_hunt_agent.pii.clean_ad_text` - the same function the BA client and the
cleaned fixture set (D-8) will use - over all raw listings collected so far
(40 from D-1, plus 22 from D-10 follow-up 2's München detail fetch - 62
total).

First run (before the fix below): 2 of the 22 new München listings still
carried a real name after cleaning - `10001-1003853660-s.json` ("Herr
Salmen gibt Ihnen weitere Informationen...") and `14751-417a24069-s.json`
("...steht Frau Stefanie Ruf gerne unter der Telefonnummer..."). `pii.py`'s
`INLINE_NAME_PATTERN` only matched `bei Frau/Herrn <Name>` (D-3
pattern 1) - neither sentence used "bei", so the name wasn't touched.
Fixed by dropping the "bei" requirement (matches `Frau/Herr(n) <Name>`
anywhere in a sentence now); re-ran `scripts/build_fixtures.py` and
`pii_check.py` after the fix.

- Listings checked: 62
- E-mail addresses masked: 5
- Phone numbers masked: 3
- Contact/name lines removed: 280
- Listings with a still-suspicious line after cleaning: 0

**Goal met: 0 remaining contact names** after cleaning.

## D-10 follow-up 2: München data gap closed (2026-11-06)

`spikes/fetch_muenchen_details.py` fetched v4 details for the 25
referenznummern of the recorded "Softwareentwickler"/München search
directly from the live BA API (one run, polite pacing, reusing
`ba_api_spike.py`'s `call`/`encode_refnr`): 22 saved, 3 already 404
(expired since the D-1 search ran, 2026-11-05). `scripts/build_fixtures.py`
cleaned and added them; `recorded_searches.json`'s München entry now
references all 22 (was 0).

Closing the gap also exposed and fixed two latent bugs, both pre-dating
this session:

1. **Lossy referenznummer recovery.** `build_listing_from_details` derived
   `referenznummer` from the details file's *name* (a one-way slug - every
   `_` and `/` collapses to `-`), not from the correct value already
   sitting in the file's own `referenznummer` field. Silently wrong for
   any reference number containing `_` or `/` - 4 of the original 40
   listings, 8 of the 22 new ones. Fixed: read the field directly (it is
   correct for every listing except the 3 the phone regex corrupted
   in-place, D-1/D-4 - those 3 still fall back to the file name, which
   stayed correct for them). München's recorded search now references all
   22 of its own listings (was 14 before this fix); the other 4 recorded
   searches gained reference numbers too (Python/Hamburg 2->4,
   AI Engineer/Hamburg 24->25, Java/Hamburg 7->9, Machine Learning/Berlin
   unchanged at 10).
2. **PII leak in two new listings** - see the pii_check.py entry above.

`ba_client.FixtureSource`'s narrowing path (D-10 addendum) now also checks
each candidate's *description*, not just title/employer - "the whole point
of narrowing is the model's more specific terms, which are more likely to
only appear in the ad body" (`src/job_hunt_agent/ba_client.py`). 2 new
tests (`tests/test_ba_client.py`, `tests/test_pii.py`).

### Re-run: "Find Softwareentwickler jobs in München." (real model, demo mode)

| # | `search_jobs` call | Result |
|---|---|---|
| 1 | `Softwareentwickler` / München, 25 km, 28 days | **total: 103** (exact replay) |
| 2 | `Python Softwareentwickler` / München, 25 km, 28 days | narrowed from the recorded query - **total: 0** (honest: none of München's own listings mention Python) |

Full trace: `search_jobs` (103) -> `search_jobs` (narrowed, 0) ->
`get_job_details` x6 -> `assess_fit` (6 listings) -> shortlist. **This is
the first time this specific query reaches `get_job_details`/`assess_fit`**
- the full "narrow -> details -> assess_fit" chain the D-10 addendum could
not yet demo.

After the narrowed search came back empty, the agent fell back to the 6
listings from its own first (broad, non-temp-agency) search result rather
than asking the user - fetched details and assessed fit for all 6:
`poor, poor, partial, poor, poor, partial` (categories are code-computed,
spec §1.2/§7, not set by the model). It correctly told the user München's
real market for this keyword is mostly .NET/C# and system-level roles, not
a match for the profile's Python/FastAPI stack - an honest result, not a
forced "success". Elapsed: 54.3s (within the 60s NFR-03 budget, no D-11
needed). Full machine-readable trace, no ad text beyond the model's own
evidence-quoting final message (same pattern as `core_journey_wp03.json`):
`eval/results/d10_followup2_verification.json`.


## D-10 follow-up 3: fix pii.py over-removal, close the loop (2026-11-06)

Coach review found that `CONTACT_MARKER_PATTERN` matched "Kontakt"/
"Ansprechpartner" *anywhere* in a line, not just a heading - a requirement
bullet like "Enger Kontakt mit den technischen Produktverantwortlichen..."
opened a "contact block" that then ran to the end of the ad, silently
dropping requirement and task lines. Measured on the 40 raw D-1 listings:
5 lost 50-91% of their text, one lost 19%.

**Fix:** `CONTACT_HEADING_PATTERN` now only matches a heading-like line -
anchored at the start, after only an optional markdown decoration (`#`,
`*`/`**`/`***`, `_`/`__`/`___`) and an optional "Ihr(e)"/"Dein(:e)"
possessive, length-capped at 90 characters so a full sentence that happens
to start with the marker still doesn't qualify. The dropped block is
bounded (`CONTACT_BLOCK_MAX_LINES = 6`), ends at the first blank line, the
next markdown heading, or a continuation line too long to be a contact
entry (`CONTACT_BLOCK_LINE_MAX_LENGTH`, name/company/phone lines are
always short) - one leading blank line directly after the heading is
skipped rather than ending the block immediately, matching the common
"## Kontakt\n\n<block>" markdown spacing. 6 new tests in `tests/test_pii.py`.

**`spikes/pii_check.py` extended** to report each listing's removed-text
share and flag anything above 10%, separating a legitimate (bounded)
contact-block drop from genuine unexplained over-removal (counterfactual:
what the share would be if no contact block were dropped at all).

Rebuilding the fixtures and re-running the extended check found two more
real, previously-undetected PII leaks and one new over-removal regression,
all introduced or exposed by lines that don't fit the simple
"Frau/Herr <Name>" or "heading, then address block" shapes the original
D-3 patterns were built from - fixed in the same pass:

1. **`**Ansprechpartner: <Name>, Tel: [TELEFON], Mobil: [TELEFON]**`** - a
   markdown-bold single-line contact block, name included - not caught
   before because `CONTACT_HEADING_PATTERN` didn't allow `**` as a leading
   decoration. Fixed by the decoration alternation above.
2. **`**ANSPRECHPARTNER FÜR FACHLICHE FRAGEN**`** (also `**`-wrapped)
   followed, after one blank line, by two bare `<Name>, <role>, Tel. <nr>`
   lines with no "Frau/Herr" prefix and more on the line than just the
   name - not caught by any of the five D-3 patterns at all. Fixed by the
   same decoration fix plus the "skip one leading blank, then continue the
   block" change (otherwise the blank line right after the heading would
   have ended the block before reaching the names).
3. **Over-removal regression**: `"Dein Kontakt für diese Stelle ist:
   <Name>"` was immediately followed, with no blank line, by a
   differently-styled subsection ("Das bringst du mit") and six
   full-sentence requirement bullets - swallowed as "part of the block" by
   the line-count budget alone (17% of the ad removed). Fixed by the
   continuation-line length cap: a candidate line longer than 90
   characters ends the block instead of being dropped.

### Final numbers (62 listings: 40 D-1 + 22 München, D-10 follow-up 2)

- E-mail addresses masked: 5; phone numbers masked: 3; contact/name lines
  removed: 23
- Listings above 10% removed: **0** (neither explained-by-block nor
  unexplained) - the 19121 regression above is now at 1.3%
- Listings still flagged by `pii_check.py`'s plain keyword search after
  cleaning: 7 - **all manually verified as benign**, not leaked names:
  ordinary sentences using "Kontakt"/"Ansprechpartner" as vocabulary
  ("Enger Kontakt mit...", "...agierst als führender Ansprechpartner...",
  "...ist zentraler Ansprechpartner für den gesamten Bereich...", two
  near-duplicate "Enger Kontakt..." task bullets, a two-word benefit
  bullet "- Persönlichen Ansprechpartner", and a generic "contact us"
  paragraph with no name attached). `pii_check.py`'s `SUSPICIOUS_PATTERN`
  is a blunt keyword search by design (see its own docstring) and cannot
  tell "mentions the word" from "leaked a name" on its own - left
  unchanged, since narrowing it further would just re-implement
  `pii.py`'s own heading heuristic and could never flag anything beyond
  what `pii.py` already catches.

**Goal met: 0 real names leaked, 0 listings over 10% removed**, given the
7 remaining flagged lines are confirmed non-PII by manual review.

Full per-listing detail (gitignored, still has ad text):
`spikes/fixtures/pii_check.json`.

### Re-run: did the 6 assessed München listings' fit categories change?

Re-ran "Find Softwareentwickler jobs in München." in demo mode with the
real model after rebuilding the fixtures. Same chain as the D-10 follow-up
2 verification: search (103) -> narrowed search (honest 0) -> a third,
age-widened search (also 0) -> `get_job_details` x6 -> `assess_fit` on the
same 6 referenznummern -> shortlist. Elapsed 56.2s (within the 60s NFR-03
budget).

**Categories did not change:** `poor, poor, partial, poor, poor, partial`
- identical to the follow-up 2 run, in the same order. Two of the six
listings had their description text change substantively by this fix:

- `10001-1003863378-S` (the `Stefan Müller`/`Andreas Fuchs` name leak,
  now masked) stayed **partial**.
- `19121-44499216-1011-S` (the `Lina Rackl` over-removal regression, 6
  requirement bullets about Unix/C/shell/TCP-IP now restored) stayed
  **poor**.

Neither change affected the outcome: the removed/restored text in both
cases doesn't overlap with the profile's Python/FastAPI/PostgreSQL/Docker/
CI-CD skills, so the rubric's code-computed category was unaffected either
way - a real name leaking (or not) and a few requirement bullets being
silently dropped (or not) changed what the model could see, but not
whether this match is fundamentally a Python-profile-vs-.NET/C#/Unix-ad
mismatch. Full machine-readable trace, no ad text beyond the model's own
evidence-quoting final message: `eval/results/d10_followup3_verification.json`.

## WP-04 UI smoke run: real-model headless AppTest-equivalent (2026-11-09)

Script: `scripts/ui_smoke_wp04.py` (not a pytest test - reuses `app.py`'s own
status-label logic, `app.iter_new_tool_calls`, against the real model and
`FixtureSource`, demo mode). Demo query: **"Find Softwareentwickler jobs in
München."** (matches the D-10/D-1 recorded München search exactly: keywords
"Softwareentwickler", radius 25 km, published within 28 days, real recorded
total 103). Full machine-readable record (no ad text):
`eval/results/ui_smoke_wp04.json`.

**First run had a counting bug, found in coach review, fixed before this
number:** `stream_mode="updates"` re-emits the same `AIMessage` (same tool
call id) from later middleware steps that return the whole `messages` list,
not just what is new (e.g. the built-in `PIIMiddleware`'s `before_model`).
The first run's raw loop counted every occurrence, making every tool call
and status label look doubled (`search_jobs, search_jobs, assess_fit`
*twice*, identical args both times) - the checkpointer's actual message
history had only 3 unique tool calls, each with its own id. Fixed by
`app.iter_new_tool_calls` (dedup by `tool_call["id"]`, mutating a
`seen_tool_call_ids` set across steps), used by both `app.py::run_turn` and
this script; unit-tested in `tests/test_app.py::
test_iter_new_tool_calls_dedups_the_same_call_echoed_by_later_middleware_steps`.

**Corrected numbers (re-run after the fix):**

- Elapsed: **65.8 s - exceeds the 60 s NFR-03 budget** (first run, before
  the fix, was 56.4 s with a different tool sequence; run-to-run model
  variance, not something this fix caused). Reported as instructed, nothing
  tuned to bring it under budget; `run_core_journey.py`'s own D-12-latency
  mechanism is scoped to its own S1 scenario, not this script, so no
  decision file was auto-written here - flagged to Ingo instead.
- Tool sequence (each call now genuinely once): `search_jobs, search_jobs,
  get_job_details` x6, `assess_fit`. The model narrowed itself
  ("Softwareentwickler Python Java FastAPI PostgreSQL Docker CI/CD senior"
  -> a wider age/radius retry) per FR-03 AC1, then read 6 listings' details
  before assessing them - the fuller, more expected tool chain than the
  first (buggy-count) run showed.
- Status labels shown (`app.py::_status_label`): `Searching the job
  board…` (x2), `Reading 1..6 listing(s)…` (incrementing correctly), 
  `Assessing fit…` (x1) - 9 labels for 9 real tool calls, 1:1.
- Card count: **6 visible (2 partial, 4 poor), 0 excluded, 6 total.**
  Consistent with D-10 follow-up findings: München's real market for a
  plain "Softwareentwickler" search is mostly not a match for the Python/
  FastAPI/PostgreSQL/Docker/CI-CD profile.

Related: FR-07, FR-16 AC2, NFR-03, D-10, D-12, WP-04

## WP-05 S1 latency measurement, 5 real-model runs (2026-11-09)

D-12, Option 1: 5 runs of S1 ("Find Softwareentwickler jobs in München.",
D-10's recorded München search), demo mode (`FixtureSource`), real model
(`openai/gpt-5-mini`, reasoning effort `low`), fresh thread per run, config
unchanged. Script: `scripts/ui_smoke_wp04.py --runs 5` (new option on the
WP-04 smoke script, no duplicated logic). Full per-run record: `eval/
results/latency_s1_wp05.json`.

**Across all 5 runs:** elapsed seconds median **52.75 s**, mean 36.96 s,
min 7.63 s, max **59.63 s** - both median and max inside the 60 s NFR-03
budget.

**Important caveat, not papered over:** only 3 of the 5 runs actually ran
the full S1 pipeline to `assess_fit` (`search_jobs -> get_job_details ->
assess_fit`, 6 listings assessed each time, 59.63 s / 55.48 s / 52.75 s).
The other 2 (7.63 s and 9.33 s) stopped after one `search_jobs` call with
0 listings assessed and 0 cards - the same model behaviour seen in the
WP-05 S1/S2 real-model check (`eval/results/wp05_s1_s2.json`'s first,
discarded attempt): with the demo query's location ("München") not
matching the committed profile's `location: Hamburg`, the model
sometimes asks for clarification instead of searching, rather than
treating the user's literal request as the search target and letting the
rubric's own radius/remote hard exclusion (§7) filter the result
afterwards. This is a **search-time location handling** difference across
runs, not a latency-tuning issue, and it halves the number of latency data
points that actually measure the thing NFR-03 is about.

**Numbers for the 3 completed runs only:** median 55.48 s, mean 55.95 s,
min 52.75 s, max 59.63 s - still inside budget, but the maximum is 0.37 s
under the 60 s ceiling, and n=3 is a thinner sample than the 5 planned.
`assess_fit` extraction alone: 27.8 s / 24.9 s / 25.1 s for 6 listings each
(4 concurrent extractions, `config.MAX_CONCURRENT_EXTRACTIONS`) - the
dominant cost, consistent with D-4's per-extraction spike and D-12's risk
R-4.

**Reading against D-12's question:** on the numbers measured, the median
and the maximum are both at or under the 60 s budget, so D-12's "append
Round 2 options" trigger (median or max above 60 s) is not met and nothing
in `config.py`/`tools/assess.py`/the prompts was tuned. Flagged to Ingo as
a judgment call regardless: the margin on the 3 genuine completions (0.37 s
under budget on the worst of 3) is thin enough, and the early-stop
confound real enough, that a literal "budget met" reading deserves that
context before being relied on.

Related: FR-05 AC1, FR-16 AC2, NFR-03, R-4, D-4, D-10, D-12, WP-05

## WP-05 Addendum 1: location-override fix and re-measured S1 latency (2026-11-09)

**Cause of the 2/5 early stops above:** confirmed by two independent
real-model runs (both this early-stop measurement and the WP-05 S1/S2
check's first, discarded attempt) - the model sometimes treats the
profile's stored `location: Hamburg` as a hard boundary for a "jobs in
München" request and asks which location to use, instead of searching
München directly. Spec FR-01 AC4 already allows this ("the request may
override [the profile] for this search"), but `prompts/system.md` never
said so explicitly - the model's own judgment filled the gap
inconsistently (3 of 5 runs searched directly, 2 asked).

**Fix:** one new bullet in `prompts/system.md`'s "Search and refinement"
section: a location named in the request overrides the profile's stored
location for this search; do not ask first (the profile's radius/remote
rules still apply once results are assessed). No rubric or tool change.

**Tool-sequence recording fix (Addendum 1 #2):** `scripts/ui_smoke_wp04.py`
previously collapsed the recorded tool sequence to unique names, hiding
how many `search_jobs` calls (refinement, FR-03 AC3) each run actually
made. Now records the full per-call sequence, deduplicated by
`tool_call` id only (`_tool_sequence_of`) - `search_jobs_calls` and
`reached_assess_fit` are derived from it per run.

**Re-measured, 5 fresh-thread runs, same config** (`eval/results/
latency_s1_wp05.json`, replaces the first measurement above):

| Run | Elapsed (s) | `search_jobs` calls | Reached `assess_fit` | Listings assessed |
|---|---|---|---|---|
| 0 | 36.19 | 2 | yes | 4 |
| 1 | 58.44 | 2 | yes | 6 |
| 2 | 53.51 | 4 | yes | 3 |
| 3 | 42.87 | 2 | yes | 4 |
| 4 | 44.77 | 2 | yes | 5 |

- **Completion rate: 5/5 (100%).** The location-override fix eliminated
  the early-stop behaviour entirely in this sample - every run reached
  `assess_fit`.
- **Refinement rate: 5/5 (100%).** Every run made more than one
  `search_jobs` call (FR-03 AC1/AC3's narrowing-when->50-results behaviour
  firing consistently); run 2 made 4 calls and still finished in 53.51 s.
- **Elapsed seconds: median 44.77 s, mean 47.16 s, min 36.19 s, max
  58.44 s** - all inside the 60 s NFR-03 budget, computed over a clean
  5-run sample this time (no early-stop confound). Worst-case margin:
  1.56 s under budget (run 1).
- `assess_fit` extraction seconds per run: 13.1 / 26.9 / 11.2 / 15.9 /
  22.8 s, scaling roughly with listings assessed (4/6/3/4/5) - consistent
  with D-4's per-extraction cost and D-12's risk R-4.

**Reading against D-12's question (updated):** median and maximum are
both inside the 60 s budget on a complete 5/5 sample, so no "Round 2
options" were added and nothing in `config.py`/`tools/assess.py`/the
extraction prompt was tuned. **Budget met: yes**, with a cleaner
measurement than the first attempt.

Related: FR-01 AC4, FR-03 AC1, FR-03 AC3, FR-05 AC1, NFR-03, R-4, D-4,
D-10, D-12, WP-05 Addendum 1

## WP-05 Addendum 1 #4: S2 explanation contradicts the computed matches (investigation, no fix applied)

**Symptom** (`eval/results/wp05_s1_s2.json`, both the original and the
re-run after the location fix): the S2 answer for referenznummer
`10001-1003863378-S` calls Java part of a "skills mismatch" and says
"your profile lists Python, FastAPI and PostgreSQL" (first run) /
"Python, FastAPI, PostgreSQL, Docker" (second run) - both times omitting
at least Java and `CI/CD` from `profile_alex.yaml`'s actual 6 skills
(Python, Java, FastAPI, PostgreSQL, Docker, CI/CD).

**Checked the stored `FitAssessment` directly** (not from memory - read
back from the `s1-s2-check.sqlite` checkpoint):

```text
rubric: {"skills": "not_met", ...}
matches: [
  "Pflege und Neuentwicklung von Desktop- und Serversoftware, vorrangig in Java" (-> Java),
  "Beherrschung der Programmiersprache Java inkl. ..." (-> Java),
]
gaps: [8 other extracted requirements - Landesvermessung/geodata work, IT-security
       hardening, "relationale Datenbanken inkl. SQL", interfaces/protocols,
       the IT vocational-training credential, "Sehr gute Deutschkenntnisse"]
```

**Rubric is correct, not the cause:** `skill_matches_profile` did match
both Java-named requirements against the profile's `Java` skill - they are
in `matches`, not `gaps`. The `skills` dimension's `not_met` verdict is an
aggregate: only 2 of 10 extracted requirements matched (20%, below the
40% partial threshold, D-9) - `not_met` is correct for the *dimension*,
but does not mean every individual requirement mismatched.

**Cause:** the model conflates the aggregate dimension verdict with a
per-requirement judgment when writing the free-text explanation (FR-08
AC2) - it re-derives "mismatch" for Java from `skills: not_met` instead of
reading the already-computed `matches` list, which says the opposite.
Separately, when citing "your profile", it paraphrases a shortened recall
of the 6-skill list from memory instead of quoting the `Skills:` line it
was given verbatim in the one-off profile-context message
(`middleware/profile_context.py`) - the full list is in its context both
times, the omission is a generation-fidelity issue, not a missing-data
one. Neither run invents a requirement not actually extracted (the letter
of FR-08 AC2 is met), but both misattribute a match as a gap in prose,
which is the same failure in spirit.

**Proposed fix (prompt-only; rubric and tool contracts unchanged, per
instruction) - not applied, for Ingo to approve:** add to
`prompts/system.md`'s "Explaining the shortlist" section: *"The
assessment's `matches` and `gaps` are already computed by code - treat
them as authoritative. Never call a skill listed in `matches` a mismatch,
even when the `skills` dimension's own verdict is `not_met` (a `not_met`
dimension can still contain individual matches - it is a share, not a
unanimous verdict). When citing the user's own skills, quote the
`Skills:` line from the profile context message in full rather than
recalling a shortened list."*

Related: FR-05 AC3, FR-08 AC1, FR-08 AC2, D-9, WP-05 Addendum 1
