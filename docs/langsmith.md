# LangSmith tracing

Related: spec §9.5 (Hard 2), FR-18 AC1, FR-22 AC4, D-18, WP-10

## Data-handling text (for the README's §12.3 "memory and data handling" section, WP-14)

Copy the paragraph below into the README when it is assembled (FR-22 AC4: what is
sent to the model and to any third party). Not written there yet - the README
itself is WP-14.

> **LangSmith tracing** is off by default and switched on only on the developer
> settings page (D-18). When it is on, every agent run is sent to LangSmith
> (`https://eu.api.smith.langchain.com`, project `job-hunt-agent`): the
> conversation messages, the cleaned ad text of any listing the agent read
> (contact data already removed, FR-22 AC1), the selected user's profile (no
> name, e-mail, phone or address, FR-14 AC3) and the user id. The LangSmith API
> key is read from the `LANGSMITH_API_KEY` environment variable only and never
> appears in a file, a log or the UI. A tracing failure never affects the app
> (spec §8) - the agent runs the same with tracing on or off.

## How tracing is switched on (implementation note, not README text)

`job_hunt_agent/tracing.py` builds a `LangChainTracer` per run from one
process-wide LangSmith `Client` (`ui_shared.get_langsmith_client`, cached):
building the client makes one network call (`GET /info`), so it is built once,
not once per turn; a missing key, an unreachable LangSmith or any other failure
yields `None` and the run proceeds untraced (spec §8). The developer-settings
toggle (`pages/4_Developer_settings.py`) is off by default and disabled
whenever `LANGSMITH_API_KEY` is not set.

## WP-10 real-model trace recording (2026-11-11)

`scripts/run_langsmith_traces.py`, demo mode, user `alex`, model
`openai/gpt-5-mini` (reasoning effort `low`), one continuous thread (S3's "#1"
refers to S1's own shortlist, same pattern as `scripts/run_core_journey.py`,
WP-03). Full record: `eval/results/langsmith_wp10.json`.

| Scenario | What it demonstrates | LangSmith run id |
|---|---|---|
| S1 | Search, refinement decision (tags `demo`, `S1`) | `01a1c9c5-378e-754f-86b3-deacb66f7df6` |
| S3_propose | `save_to_tracker` proposed, interrupt | `01a1c9c5-bf17-73fe-ac0a-3ab14c8b530a` |
| S3_approve | Resume after approval; the entry is written | `01a1c9c5-cc14-70e8-a529-6bfdee316331` |
| S4_propose | `remember` proposed, interrupt | `01a1c9c5-dad0-70de-a3e1-aa7512731685` |
| S4_reject | Resume after rejection; nothing is stored | `01a1c9c5-e288-7362-9dbf-d50ad8e45787` |

Project: `job-hunt-agent`, endpoint `https://eu.api.smith.langchain.com` (EU
region - confirmed in WP-10's "Check first": the US endpoint returns 403 for
this key). Verified directly against the run's own SQLite file afterwards (not
just the model's own words): the `tracker` table has exactly the one S3 entry
(`17338-c2de5ff0cd55000215-S`, status `saved`, follow-up `2026-11-18`); the
memory store is empty (the rejected S4 `remember` call never persisted).

**What Ingo needs to do for WP-14** (these run ids are only visible in
Ingo's own LangSmith account right now; the README cannot link to a private
page):

1. Open each run id above in the LangSmith UI (`job-hunt-agent` project, EU
   region) and either:
   - click "Share" to get a public link (`client.share_run(run_id)` does the
     same thing from the SDK, has not been run from here - that is a
     publish/visibility decision for Ingo to make, not something to do without
     asking), and paste the five links into the README's tracing section; or
   - take a screenshot of each trace (the tool-call tree is the useful part)
     and embed the images instead.
2. The project `job-hunt-agent` on a `shortlived` trace tier (confirmed when
   the project was auto-created during WP-10's "Check first") may expire
   traces before the review - check the tier/retention setting before
   submission and extend it or re-run the script closer to the review date if
   needed.

## Manual check (for Ingo)

1. Developer settings -> switch "LangSmith tracing" on (needs
   `LANGSMITH_API_KEY` set).
2. Run any demo query in the main chat.
3. Open the `job-hunt-agent` project in LangSmith (EU region) and find the new
   trace.
4. Switch tracing off again; confirm the app still works exactly the same
   without it.
