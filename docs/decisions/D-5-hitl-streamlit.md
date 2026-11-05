# D-5: Approval with interrupt and resume in Streamlit

## Question

How should the real agent wire `HumanInTheLoopMiddleware`, the rejection-lock
middleware (spec §5.4 #4) and `SqliteSaver` so that approve/edit/reject works
correctly across Streamlit reruns and app restarts (FR-10)?

## Context

`spikes/hitl_app.py` + `spikes/test_hitl_app.py` (6 automated `AppTest`
checks, scripted model, no network call) plus one real-model run prove the
mechanics end to end. Full write-up: `spikes/NOTES.md` § D-5. Headline
finding: `after_model` hooks run in **reverse** middleware-list order (the
*last*-listed middleware's `after_model` runs *first*), the opposite of
`before_model`'s forward order. This is undocumented behaviour discovered by
reading `langchain/agents/factory.py`, not something the public API states.

Also confirmed: the pending interrupt lives entirely in the checkpointer
(`agent.get_state(config).interrupts`), not in Streamlit session state, so it
survives reruns and restarts "for free" as long as the same `thread_id` and
the same SQLite file are used; one shared `sqlite3.connect(..., check_same_thread=False)`
cached with `st.cache_resource` is sufficient (`SqliteSaver` serialises
access itself).

## Options

1. **Carry the spike's design into the real agent, unchanged.** Custom
   `RejectionLockMiddleware(before_model, after_model)` with a
   `rejected_actions: list[str]` state field (hash of tool name + args),
   listed **after** `HumanInTheLoopMiddleware` in `middleware=[...]` so its
   `after_model` strips a repeated call before HITL's `after_model` would
   re-interrupt on it. Proven in 6 automated tests (approve, reject, repeat-
   after-reject, rerun, restart, read-only-never-gated) and one real-model
   run.
2. **Skip the custom lock, rely on model behaviour.** The real model, well
   prompted, did not retry after a rejection in the one real run. But spec
   §5.4 #4 and FR-10 AC3 explicitly ask for a *code-enforced* lock, and the
   spike shows a scripted (or simply different/cheaper) model re-proposing
   the identical call would otherwise re-interrupt the user on something
   already rejected - an avoidable repeat ask.
3. **Move the lock into `wrap_tool_call` instead of `before_model`/
   `after_model`.** Not evaluated in the spike; `wrap_tool_call` runs at tool
   execution time, which is after HITL's own `after_model` has already
   decided to interrupt - too late to prevent the interrupt itself. Would
   need its own spike to confirm; no evidence it can replace option 1.

## Recommendation

Option 1: implement `RejectionLockMiddleware` in
`src/job_hunt_agent/middleware/rejection_lock.py` exactly as prototyped,
including the explicit middleware-list order.

## Consequences

- `PRODUCT_SPEC.md` §5.4 lists the rejection lock as "#4" before HITL's "#5",
  which reads as the middleware list order. Proposed clarification (not a
  behaviour change): add a footnote that the code list order is
  `[HumanInTheLoopMiddleware, RejectionLockMiddleware]` (reverse of the
  table's visual order) because of how `after_model` hooks compose - this
  was already flagged as "verified in spike D-5" in the spec text itself.
- New files: `src/job_hunt_agent/middleware/rejection_lock.py`,
  `tests/test_rejection_lock.py` (mocked model, NFR-05).
- `state.py`'s `JobHuntState` gains `rejected_actions: list[str]` exactly as
  already specified in spec §5.3 - no change needed there.
- The production system prompt (`prompts/system.md`) needs an explicit line
  that approval happens automatically outside the conversation, so the model
  proposes write actions directly instead of asking permission itself first
  (observed with the real model in the one real-model run, § D-5 in
  `spikes/NOTES.md`).

**Decision (draft, Claude Code's recommendation - please confirm or correct):**
Option 1 - carry the spike's `RejectionLockMiddleware` design (hook, state
field, and the `[HumanInTheLoopMiddleware, RejectionLockMiddleware]` list
order) into the real agent unchanged; add the proposed §5.4 footnote and the
system-prompt instruction under Consequences.
2026-11-05, pending Ingo's confirmation.
