# D-6: Long-term memory storage

## Question

For FR-15 (`remember` tool, long-term memory): a SQLite-backed LangGraph
store, or an own SQLite table (as sketched in spec §11's `storage.py`)?

## Context

Checked directly during spike D-5 (facts only, no app built against it yet):
`langgraph.store.sqlite.SqliteStore` ships inside `langgraph-checkpoint-sqlite`,
already an approved dependency for this package - no new dependency needed.
Confirmed working:

```python
from langgraph.store.sqlite import SqliteStore

with SqliteStore.from_conn_string("memories.sqlite") as store:
    store.setup()
    store.put(("memories", "user1"), "pref1", {"kind": "preference", "value": "remote only"})
    store.search(("memories", "user1")))   # -> items with namespace/key/value
    store.get(("memories", "user1"), "pref1")
```

It is namespaced by a tuple (e.g. `("memories", user_id)`), keyed per item,
with `put` / `get` / `search` / `delete`, and an optional `TTLConfig` if ever
needed. The tracker (FR-09, FR-11) has different needs: status filtering,
follow-up-date highlighting, and direct edits/deletes from a dedicated UI
page - closer to normal SQL columns than a namespaced key-value store.

## Options

1. **`SqliteStore` for memories, `SqliteStore` for the tracker too** (one
   storage mechanism everywhere). Least code, but the tracker's querying
   needs (status filter, "follow-up date in the past", FR-11 AC1) would have
   to be done by scanning and filtering in Python after `search()`, since the
   store has no SQL `WHERE`.
2. **Own SQLite table for both** (as sketched in spec §11, course-module
   pattern), no `SqliteStore` at all. Full control, one mental model, but
   reimplements namespacing/key handling that `SqliteStore` already provides
   for memories, and FR-15 AC3 ("the memory view lists all items, user can
   delete each one") is exactly what `search`/`delete` already do.
3. **`SqliteStore` for memories (FR-15), an own table for the tracker
   (FR-09/FR-11)** - split by which storage model actually fits the access
   pattern. Memories are simple namespaced key-value lookups (kind, value,
   per user); the tracker needs real columns to filter and sort on.

## Recommendation

Option 3: `SqliteStore` for `memories`, a hand-written table for `tracker`
(and the user profile, FR-14) in `storage.py`.

## Consequences

- `PRODUCT_SPEC.md` FR-15 AC1 currently says "Stores the item in the SQLite
  table `memories`". Proposed wording tweak (storage mechanism only, no
  behaviour change): "Stores the item in a SQLite-backed LangGraph store
  (`SqliteStore`), namespaced per user." §11's code structure already lists
  `storage.py: SQLite: profiles, tracker, memories` - propose narrowing that
  line to `profiles, tracker` and adding `store.py: SqliteStore wiring for
  memories (FR-15)`, or folding the `SqliteStore` setup into `storage.py`
  under a clearly separate function - implementer's choice, no spec
  objection either way.
- `create_agent(..., store=...)` needs the store passed at agent-build time;
  tools reach it via `ToolRuntime.store` (not yet tried against the real
  `remember` tool - a small follow-up check when `tools/memory.py` is built).
- New/changed files when FR-15 is implemented: `src/job_hunt_agent/storage.py`
  (tracker/profile tables, unchanged plan) plus a few lines wiring
  `SqliteStore` (either there or in a new tiny module); `tools/memory.py`;
  `tests/test_memory_store.py`.
- Separate SQLite files vs. one shared file for store + checkpointer + tracker
  is still open - no evidence either way from this spike; default to one
  shared file (simpler `NFR-01` setup, one path to back up/delete) unless a
  later problem shows otherwise.

**Decision:** _(pending - Ingo to record, with date)_
