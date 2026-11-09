# D-16: User management - select a user by name, no authentication

Related: spec §2.2, FR-13, FR-14, FR-15, FR-22, NFR-07

## Question

The app runs with one fixed user id ("alex"). A real product would have user
management with authentication. How much of that does this project build?

## Context

Spec §2.2 already states: "the app runs locally for one user at a time (user
selected by name, no authentication)". Profile, tracker, memories and (with
D-15) threads are all stored per user id, so only the selection is missing.
The app is reviewed locally in a live session.

## Options

1. **Select a user by name** in the sidebar (existing users plus "new user");
   all pages work with the selected user. No authentication. About 30 min on
   top of WP-08. Matches spec §2.2.
2. **Local login with password** (e.g. `streamlit-authenticator`): new
   dependency, about 1-1.5 h; passwords in a local file, so limited security
   gain for a local app.
3. **Login via an identity provider** with Streamlit's built-in OIDC support
   (`st.login()`, `st.user`): about 1.5-2 h plus provider setup and secrets;
   the reviewer would have to log in to see the demo; the e-mail address
   becomes stored personal data (FR-22, README data section).

## Recommendation

Option 1 now; Option 3 named in the README as an improvement idea, with the
reasons above.

## Consequences

- WP-08 adds the user selection; all pages read the selected user from one
  place in `ui_shared.py`.
- README: "Known limitations" states that there is no authentication and the
  app is meant for local single-user use; "Ideas" names OIDC login via
  `st.login()`.

**Decision:** Option 1 (2026-11-09, Ingo). Option 3 goes into the README as an improvement idea.
