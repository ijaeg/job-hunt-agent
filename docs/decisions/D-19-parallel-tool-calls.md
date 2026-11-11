# D-19: Parallel tool calls in one agent step

Related: spec §5.3, §5.4, FR-02 AC5, FR-03 AC2, FR-05 AC5, FR-20 AC1, WP-10, WP-11

## Question

The model can call several tools in one step (parallel tool calls). How does
the agent stay correct when two tool calls in the same step update the same
state field?

## Context

Found while recording the WP-10 LangSmith traces: the model called
`search_jobs` twice in one step; both calls updated `seen_refs`, and LangGraph
aborted with `InvalidUpdateError: At key 'seen_refs': Can receive only one
value per step`. All fields of `JobHuntState` (spec §5.3) use plain overwrite
semantics, which assumes one writer per field per step. The same weakness
affects the per-message search counter: two parallel searches could both read
the same count, so the limit of 3 searches per message (FR-20 AC1) would not
hold reliably.

## Options

A. **Fix the cause in the state:** fields that tools update get reducers
   (merge rules) in `state.py`, e.g. union for reference lists, merge for
   dictionaries. The search limit is enforced in a way that stays correct
   when several searches are proposed in one step.
B. **Forbid parallel tool calls** in the model call. One line, but it only
   hides the cause, and it is unclear whether the setting works the same way
   for every model behind OpenRouter.

## Recommendation

Option A.

## Consequences

- `state.py`: reducers for the fields tools write; single-call behaviour stays
  unchanged.
- The search limit must count every proposed `search_jobs` call, including
  several in one step. A plain "add" reducer on the counter conflicts with the
  reset at the start of each user message, so WP-11 checks first whether the
  built-in `ToolCallLimitMiddleware` handles parallel calls correctly, or
  enforces the limit where the model proposes the calls (after the model step,
  before the tools run).
- Spec §5.3 is updated by the coach after WP-11.

**Decision:** Option A (2026-11-11, Ingo).
