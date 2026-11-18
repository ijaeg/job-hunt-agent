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

**Superseded by WP-16b** (below): the README now links the WP-16b traces, not
these WP-10 ones. Kept here for traceability (NFR-09); the steps below were
WP-10's own open items at the time, not a current to-do.

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

## WP-16b real-model trace recording (2026-11-18)

Fresh traces for the README (spec §9.5), replacing WP-10's as the ones linked
there - WP-10's own result file (`eval/results/langsmith_wp10.json`) and the
table above are left untouched, for traceability (NFR-09).
`scripts/run_langsmith_traces_wp16b.py`, demo mode, user `alex`, model
`openai/gpt-5-mini` (reasoning effort `low`). One continuous thread S1 -> S2 ->
S3 (propose, approve) -> S4 (propose, reject); S5 and S6 on their own threads.
S1's wording is W3 ("Find Softwareentwickler jobs in München from the last 4
weeks, no temp agencies.") - the only one of three candidate wordings whose
slowest run stayed inside the 60s NFR-03 budget on all 5 runs of a dedicated
check (`eval/results/s1_wording_wp16b.json`, Addendum 1 to
`docs/prompts/WP-16b-traces-screenshots-demo.md`). Full record:
`eval/results/langsmith_wp16b.json`.

| Scenario | What it demonstrates | LangSmith run id | Public share link |
|---|---|---|---|
| S1 | Search (103 results), refinement, details, assessment | `01a1edcf-3ca2-71c7-b6f2-c5cf636aed31` | [link](https://eu.smith.langchain.com/public/2695e649-e98c-4cc6-8239-25f8dd6705e0/r) |
| S2 | No new tool call; explanation from the stored assessment | `01a1edd0-0ca6-7100-8b66-5530b28463c1` | [link](https://eu.smith.langchain.com/public/8298ad83-792a-41ec-8930-a1a839d07e36/r) |
| S3_propose | `save_to_tracker` proposed, interrupt | `01a1edd0-25b9-73ea-aec7-9dd482647aff` | [link](https://eu.smith.langchain.com/public/e6ab3465-029d-43c0-ae97-13c36e13a928/r) |
| S3_approve | Resume after approval; the entry is written | `01a1edd0-3595-7582-abd8-6d24b7cebe90` | [link](https://eu.smith.langchain.com/public/38202a12-523a-4621-b5a8-436bea6f9c51/r) |
| S4_propose | `remember` proposed, interrupt | `01a1edd0-3dfd-76ff-ae99-9e10ab3b3c6f` | [link](https://eu.smith.langchain.com/public/b86f8008-5c43-4f45-b503-47d54d0dc724/r) |
| S4_reject | Resume after rejection; nothing is stored | `01a1edd0-4650-7620-bc2b-6e08c922cbc7` | [link](https://eu.smith.langchain.com/public/c06e6b12-6b18-44a4-8633-e27ad408aed3/r) |
| S5 | Prompt-injection resistance (FIKTIV listing) | `01a1edc1-e467-7068-98fc-e0879839753b` | [link](https://eu.smith.langchain.com/public/70de8933-477d-4a45-b28d-4b78554f5a50/r) |
| S6 | Off-topic guard, no tool call | `01a1edc2-684d-75e5-9b0b-d14dc4771391` | [link](https://eu.smith.langchain.com/public/e6140a30-c22f-44f6-84b6-672ba7fa12c5/r) |

Project: `job-hunt-agent`, endpoint `https://eu.api.smith.langchain.com` (EU
region). Verified directly against the run's own SQLite file (not just the
model's own words): the `tracker` table has exactly the one S3 entry (status
`saved`, follow-up `2026-11-25`); the memory store is empty (the rejected S4
`remember` call never persisted).

**Public share links** (Addendum 1, Ingo's decision): created with
`scripts/share_langsmith_traces_wp16b.py` (`Client.share_run`, idempotent).
Confirmed public with a plain `curl` GET (no auth, no cookies) on one link:
HTTP 200, `cache-control: public`. Links expire after LangSmith's 14-day base
retention (~2026-12-02); re-run the script closer to the review date if
needed - it reads back an existing link instead of creating a duplicate. The
README's S1 and S3/S4 trace mentions (spec §9.5) link directly to these;
`docs/images/langsmith-s1-trace.png` is the S1 trace's permanent screenshot
fallback for once the links expire.

**Superseded recording (not shared):** a first S1 -> S2 -> S3 -> S4 thread used
W1 (the tie-break default before the wording decision above) - thread
`langsmith-demo-wp16b-8dc6b392`, kept under `"superseded"` in
`eval/results/langsmith_wp16b.json` for traceability, never linked or shared.

## Manual check (for Ingo)

1. Developer settings -> switch "LangSmith tracing" on (needs
   `LANGSMITH_API_KEY` set).
2. Run any demo query in the main chat.
3. Open the `job-hunt-agent` project in LangSmith (EU region) and find the new
   trace.
4. Switch tracing off again; confirm the app still works exactly the same
   without it.
