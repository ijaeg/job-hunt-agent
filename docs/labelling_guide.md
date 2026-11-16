# Labelling guide for the fit evaluation set

Related: spec §7, §9.1, §9.3, D-9, D-20, WP-13

Used with `scripts/label_fit.py` (`uv run streamlit run scripts/label_fit.py`)
to label the 20 listings of `eval/fit_set.yaml` against the demo profile
`data/samples/profile_alex.yaml`. You never see the app's own assessment
while labelling (D-20) - this guide is the only thing you check against.

## Order of decisions

1. **Hard exclusions first (FR-06).** If the listing is temporary-agency work
   (`Arbeitnehmerüberlassung`) and the profile excludes that, or the listing
   is outside the profile's search radius *and* is not fully remote, the
   overall category is **excluded** - regardless of how good a skills match
   it is. Everything below only matters when no hard exclusion applies.
2. **Five rubric dimensions**, each judged independently: skills,
   location/remote, seniority, language, employment type.
3. **Overall category** from your own read of the five verdicts together:
   **strong** (clearly a good match on most dimensions), **partial** (a
   mixed or middling match), **poor** (a weak match on most dimensions that
   does not reach a hard exclusion). Don't compute a score - use judgement,
   the same way you would skim a job ad yourself.

## The five dimensions, in plain words

### Skills (the most important dimension)

Compare the skills named in the ad against the profile's skill list
(Python, Java, FastAPI, PostgreSQL, Docker, CI/CD for the Alex profile).
- **met**: most of what the ad asks for is in the profile.
- **partly**: some overlap, but a large part of what the ad asks for is
  missing from the profile.
- **not met**: little or no overlap.
- **unknown**: the ad names no concrete technical skills at all (a pure
  teaser, or a role description with no tech stack mentioned).

Count a skill as present only if it is really the same thing - "Java" is
not "JavaScript"; a profile skill has to actually appear, not just be
loosely related.

### Location / remote

Compare the ad's location/remote information against the profile's
location, search radius and remote preference.
- **met**: within the radius and the remote preference is satisfied (e.g.
  hybrid preference + some remote share, or onsite preference and any
  distance within radius), or the job is fully remote regardless of
  distance.
- **partly**: within the radius, but the ad says nothing about remote work
  one way or the other.
- **not met**: outside the radius and not fully remote.
- **unknown**: you cannot tell at all (e.g. no location and no distance
  given).

### Seniority

Compare the ad's seniority language (junior/mid/senior/lead, or however it
is phrased) against the profile's own level.
- **met**: same level.
- **partly**: one level apart (e.g. ad wants "lead", profile is "senior").
- **not met**: two or more levels apart.
- **unknown**: the ad does not say anything about seniority.

### Language (German level)

Compare the German level the ad asks for against the profile's German
level.
- **met**: the ad's requirement is at or below the profile's level (or the
  ad does not ask for a specific level beyond what the profile already
  has).
- **partly**: the ad asks for one level more than the profile has.
- **not met**: the ad asks for two or more levels more.
- **unknown**: the ad says nothing about German at all.

### Employment type

Compare full-time/part-time and permanent/fixed-term against the
profile's preference.
- **met**: both match (or the ad does not state one of them, but the one
  it does state matches).
- **partly**: not used for this dimension in practice, but available if
  you genuinely see a middle ground (e.g. only one of the two sub-fields
  is stated and it is ambiguous whether that overrides the other).
- **not met**: a stated value conflicts with the profile's preference.
- **unknown**: the ad states neither full-time/part-time nor contract
  length.

## "unknown" vs. "not met" - the one distinction that matters most

- **unknown** means the ad simply does not say anything you could judge
  this dimension on. You are not guessing a value, you are reporting that
  there is nothing to go on.
- **not met** means the ad does say something, and what it says does not
  match the profile.

When in doubt ("the ad is vague, but leans a certain way"), prefer
**unknown** over forcing a verdict - a false "not met" hides a real gap in
the ad text that the evaluation (§9.3) specifically wants to catch, and a
false "met"/"partly" overstates the fit.

## Worked examples

- *Ad: "Java-Entwickler gesucht, Kenntnisse in Spring Boot von Vorteil."*
  Profile has Java but not Spring Boot specifically -> **skills: partly**
  (the core language matches, the framework doesn't).
- *Ad mentions no seniority at all, just "Softwareentwickler (m/w/d)"* ->
  **seniority: unknown**, not "not met" - there is nothing stated to
  disagree with.
- *Ad: "Homeoffice nach Vereinbarung", distance 40 km, profile radius 25 km,
  remote preference hybrid* -> the ad gives no remote percentage, so it is
  not confirmed fully remote, and the listing is outside the radius ->
  **location/remote: not met** (and, if the profile excludes work outside
  its radius without full remote, this is also a **hard exclusion**, so the
  overall category is **excluded**, not "poor").
- *Ad: "Festanstellung, Vollzeit", profile wants full-time and permanent* ->
  **employment type: met**.
