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
