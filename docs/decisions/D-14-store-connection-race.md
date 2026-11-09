# D-14: SqliteStore and SqliteSaver racing on the one shared connection

Related: FR-15 AC2, FR-15 AC4, D-5, D-6, WP-07

## Question

D-5 decided "one shared SQLite connection" for the checkpointer, the
store and the tracker/profile tables. Building `LoadMemoryContextMiddleware`
(FR-15 AC2) exposed a real, reproducible bug in that design. Keep one
connection and work around it, or give the store its own connection to
the same file?

## Context

`LoadMemoryContextMiddleware` calls `runtime.store.search(...)`
unconditionally on every thread's first model call - the first code path
to call the store from *inside* a running LangGraph step on every single
turn (`tools/assess.py`'s existing `_excluded_employers` only runs inside
the `assess_fit` tool node, much less often). A stress test of
`build_agent` (fresh agent, fresh fixture DB, one `search_jobs` turn, 40
iterations in one process) found:

- With the committed code unchanged (both subsystems sharing one
  connection): intermittent `sqlite3.OperationalError: cannot commit - no
  transaction is active`, raised inside `SqliteStore._cursor()`'s own
  `COMMIT`. Root cause: LangGraph's `ToolNode` runs tool calls on a
  worker thread (`concurrent.futures.thread`, confirmed in the
  traceback) while `before_model` hooks run elsewhere; `SqliteSaver` and
  `SqliteStore` each wrap bare `BEGIN`/`COMMIT` SQL around the *same*
  `sqlite3.Connection` object, each guarded only by their own internal
  lock, with no coordination between the two. `check_same_thread=False`
  (set for exactly this kind of sharing, per `get_connection`'s own
  comment) disables Python's thread guard but does not make concurrent
  `BEGIN`/`COMMIT` from two uncoordinated callers safe.
- A single retry around the failing `search()` call: looked promising at
  first (such a failure's *second* attempt usually succeeds - the racing
  commit has settled by then), but a 30-iteration instrumented run still
  hit a run where **the retry itself also failed**, and a separate
  60-iteration run raised from a tool-call path the retry never covers.
  Not reliable enough to ship.
- Giving the store its *own* `sqlite3.connect()` to the *same* file
  (`conn.execute("PRAGMA database_list")` to find the path, a second
  connection for `SqliteStore` only, `SqliteSaver` keeps the original):
  **40/40** iterations of the same stress test, zero failures. SQLite's
  own file-level locking is designed for exactly this (independent
  connections to one file); sharing one Python connection object across
  two uncoordinated subsystems is not the same thing even though it
  looks similar.

## Options

1. **Keep one connection, retry on the specific error.** No architecture
   change, but data above shows it is not reliable - an intermittent
   write-path failure in a shipped feature, not an acceptable trade-off.
2. **Give the store its own connection to the same file; the checkpointer
   and `storage.py`'s own tables (`profiles`, `tracker`) keep the
   original connection.** One file on disk, as D-6 already decided
   ("backup/delete" benefit preserved); `get_store`'s signature and every
   call site stay unchanged - it still takes the shared `conn` and derives
   the file path from it, so `agent.py`, `tools/assess.py`,
   `pages/2_Memory.py` and the tests calling `storage.get_store(conn)`
   need no changes beyond this function's body. 40/40 in the stress test.
3. **Separate files** for the store vs. checkpointer+tracker+profiles.
   Also fixes it (no shared object at all), but gives up the "one file to
   back up/delete" property D-6 explicitly weighed in favour of, for no
   extra reliability over Option 2.

## Recommendation

Option 2. It is the smallest change that actually fixes the measured
problem, keeps D-6's one-file property, and touches no call site outside
`storage.get_store`.

## Consequences

- `storage.get_store(conn)` opens a second `sqlite3.connect()` to the
  same file (via `PRAGMA database_list` on the passed-in `conn`) instead
  of wrapping `conn` directly; still cached per the original `conn`'s
  identity, so repeated calls with the same shared connection keep
  returning the same `SqliteStore` instance.
- `storage.search_memories`'s retry-on-`OperationalError` is removed
  again - no longer needed once the two subsystems stop sharing a
  connection, and CLAUDE.md's "no error handling for scenarios that can't
  happen" argues against keeping it as a safety net for a bug that no
  longer exists.
- No change to `D-5`'s or `D-6`'s own text is proposed here beyond noting
  this follow-up; the "one shared connection" wording in D-5 now means
  "one shared connection for the checkpointer and `storage.py`'s own
  tables," with the store on its own connection to that same file.
- Re-ran the full stress test (40 iterations) after the fix and the full
  `uv run pytest` suite; both clean (see session log).

**Decision:** Option 2 (2026-11-09, Ingo). The store gets its own connection to the same SQLite file; the checkpointer and the tracker/profile tables keep the shared connection. (Implemented in WP-07 before the decision was recorded; kept as implemented.)
