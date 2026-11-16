# D-20: How the fit evaluation set is labelled

Related: spec §7, §9.1, §9.3, invariant 6, D-9, WP-13

## Question

Spec §9.3 compares the code-computed fit category with Ingo's hand label on
the test listings and asks for the cause of every disagreement (extraction
error vs. rubric threshold). What exactly does Ingo label, and how?

## Context

20 listings from the committed fixture set, 8 for development and 12 for
testing (§9.1), labelled against the demo profile `profile_alex.yaml` with
the rubric of §7 (start values of D-9). One labeller, who also designed the
rubric - a limitation the README states openly (§9.3).

## Options

A. **Blind, with per-dimension verdicts:** Ingo never sees the app's category
   before labelling. Per listing he gives the overall category (strong /
   partial / poor / excluded) and one verdict per rubric dimension (skills,
   location/remote, seniority, language, employment type: met / partly /
   not met / unknown), with optional notes. About 6-8 minutes per listing,
   2-2.5 hours in total. The per-dimension verdicts let every disagreement
   be traced to one dimension and classified as extraction error or
   threshold.
B. **Overall category only:** about half the time, but disagreements can
   hardly be explained, which is what §9.3 asks for.

## Recommendation

Option A.

## Consequences

- WP-13 selects the 20 listings by a fixed rule (strata visible in the data
  alone, fixed random seed, 8/12 split), shown to Ingo for approval before
  anything else is built.
- A small labelling tool (`scripts/label_fit.py`) shows one listing at a
  time without the app's assessment and writes `eval/fit_labels.csv`.
- WP-14 computes agreement and the confusion matrix on the 12 test listings
  and classifies every disagreement per dimension.

**Decision:** Option A (2026-11-16, Ingo).
