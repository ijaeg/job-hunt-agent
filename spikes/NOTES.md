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
