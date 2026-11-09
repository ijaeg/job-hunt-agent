# D-15: How the app lists a user's threads

Related: FR-13 AC2, FR-13 AC3, spec §5, D-5, D-6, D-16

## Question

FR-13 AC2 asks for a sidebar list of the user's threads that can be resumed
or deleted. Where does the app get that list from?

## Context

The checkpointer (`SqliteSaver`) stores each conversation under its thread
id only. It knows neither which user a thread belongs to nor a readable
title. With the user selection of D-16, the sidebar must show "this user's
threads, with titles", so a mapping user -> thread id -> title is needed.

## Options

1. **Own table `threads`** (user_id, thread_id, title, created_at,
   updated_at) in `storage.py`, same pattern as `tracker` and `profiles`.
   Title = first user message, cut to 60 characters. Fast, simple to test,
   independent of LangGraph internals.
2. **Scan the checkpointer** on every render and read `user_id` and the
   first message from each stored state. No new table, but slower with many
   threads and tied to the checkpointer's internal storage format.

## Recommendation

Option 1.

## Consequences

- `storage.py` gets the `threads` table and functions to register, list and
  delete thread records.
- The UI registers a thread on its first user message and refreshes
  `updated_at` on later turns; deleting a thread removes it from the
  checkpointer (`SqliteSaver.delete_thread`) and from `threads`.
- No change to the agent, tools or middleware.

**Decision:** Option 1 (2026-11-09, Ingo).
