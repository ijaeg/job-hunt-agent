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

## Which location the distance refers to

The `distance_km` shown for a listing is not always relative to the Alex
profile's own location (Hamburg, 25 km radius). The fixture listings were
collected from 5 real searches run at different locations - Hamburg,
Berlin and München (spec D-1) - and the BA API reports distance from
whichever location a search actually asked for, not from the profile: a
location named in the chat request overrides the profile for that search
("in Berlin this time", FR-01 AC4). A München-origin listing's distance is
relative to München, not Hamburg, even though the demo profile lives in
Hamburg.

This does not change how you score the location/remote dimension below -
you still compare the number against the profile's 25 km radius exactly
as the rubric does, regardless of which city it came from. The labelling
tool shows the originating search's location and radius right next to the
distance purely so a small number doesn't mislead you into thinking a
listing is near Hamburg when it is really near München or Berlin.

**For WP-14:** when the app's own assessment is computed for comparison,
it must use this same `distance_km` value (and therefore implicitly the
same originating search) for each listing - not a freshly looked-up
distance from a different search location - so the comparison is
apples-to-apples with what was labelled here (also recorded in
`eval/fit_set.yaml`).

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

There is no **unknown** for this dimension: spec §7 does not define one,
and a missing distance always counts as *within* the radius (the same
rule `rubric.py` uses) rather than as "can't tell" - so a listing with no
distance and no remote information at all is **partly**, not unknown.

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
- **not met**: a stated value conflicts with the profile's preference.
- **unknown**: the ad states neither full-time/part-time nor contract
  length.

There is no **partly** for this dimension: spec §7 does not define one -
either both stated sub-fields agree with the profile (met), one of them
conflicts (not met), or neither is stated (unknown).

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
