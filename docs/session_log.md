# Session log

## 2026-11-05 — WP-01: tooling, config, spikes D-4 and D-5

**Done:**

- Tooling and configuration (NFR-01, NFR-06): `pyproject.toml` (real
  description, ruff/mypy/pytest config, placeholder script entry removed),
  `src/job_hunt_agent/config.py` (model, ZDR provider routing, BA API
  settings, spec §8 timeouts, FR-20 limits), `.env.example`,
  `tests/test_config.py`, `.github/workflows/ci.yml`.
- Spike D-4 (model and extraction quality, FR-05, FR-02): compared
  `openai/gpt-5-mini` vs. `anthropic/claude-haiku-4.5` on 5 listings × 2 runs
  for structured extraction, plus 3 tool-calling prompts each - 26 calls
  total. Both kept ZDR routing intact; `gpt-5-mini` faster, cheaper, slightly
  higher verbatim-evidence rate; both 3/3 correct on tool calling. Results:
  `spikes/d4_results.json`, `spikes/NOTES.md` § D-4.
- Spike D-5 (HITL interrupt/resume in Streamlit, FR-10): `spikes/hitl_app.py`
  prototype with `HumanInTheLoopMiddleware` + a custom
  `RejectionLockMiddleware`. Found that `after_model` hooks run in *reverse*
  middleware-list order (undocumented, found by reading
  `langchain/agents/factory.py`) - the rejection lock must be listed *after*
  HITL for its `after_model` to run first. 6 automated `AppTest` checks
  (scripted model, `spikes/test_hitl_app.py`) plus one real-model run, all
  passing. Also answered D-6 (SQLite-backed `langgraph.store.sqlite.SqliteStore`
  is available in already-approved dependencies). Manual checklist:
  `docs/manual_tests/D-5-checklist.md`. Write-up: `spikes/NOTES.md` § D-5.
- Decision files written (Options with numbers from the spike runs):
  `docs/decisions/D-4-model.md`, `docs/decisions/D-5-hitl-streamlit.md`,
  `docs/decisions/D-6-memory-storage.md`. All pending Ingo's recorded
  decision.

**Checks:** `uv run pytest` 10/10 passed, 100 % coverage on `job_hunt_agent`;
`uv run pytest spikes/test_hitl_app.py` 6/6 passed (not part of the
coverage-tracked suite); `uv run ruff check .` clean; `uv run ruff format
--check .` clean; `uv run mypy src` clean.

**Decision files, status:** D-4, D-5, D-6 all **open** - written this
session, awaiting Ingo's *Decision:* line.

**Next:**

- Ingo reads and records decisions in D-4/D-5/D-6.
- Once D-4/D-5/D-6 are recorded: cleaned fixture set and ad-text cleaning
  (`pii.py`, FR-22), `ba_client.py`, fit rubric (§7) with tests (per the
  project plan, spec §13, Sat–Sun).
- `RejectionLockMiddleware` and the `SqliteStore` wiring move from spike
  prototype to real modules (`middleware/rejection_lock.py`, memory storage)
  once the decisions are confirmed.
