# D-18: What is sent to LangSmith when tracing is on

Related: spec §9.5, §12.3 (Hard 2), FR-18 AC1, FR-22 AC4, NFR-01, WP-10

## Question

LangSmith tracing (spec §9.5) sends every traced run to an external service.
Which data goes there, and under which conditions?

## Context

A traced run contains the conversation messages, the cleaned ad texts
(FR-22: contact data already removed), the user's profile (no name, e-mail,
phone or address, FR-14 AC3) and the user id. Since D-16 the user id is
derived from a name the user types in, so it can be a real person's name.
CLAUDE.md asks for a decision whenever personal data is sent differently
from FR-22.

## Options

A. **Tracing off by default, switched on only on the developer settings
   page.** The traces for the README are made in demo mode with the
   fictional user "alex". The README's data-handling section names what is
   sent to LangSmith when tracing is on.
B. **As A, and additionally mask the user id in every trace.** More effort,
   little benefit for a local learning app whose traces are made with a
   fictional user.

## Recommendation

Option A.

## Consequences

- WP-10 adds the tracing toggle (off by default, disabled without
  `LANGSMITH_API_KEY`) and makes the README traces with "alex" in demo mode.
- `docs/langsmith.md` holds a short text block on the data sent to
  LangSmith; WP-14 moves it into the README (FR-22 AC4).
- The API key is read from the environment only; it never appears in a file,
  a log or the UI.

**Decision:** Option A (2026-11-11, Ingo).
