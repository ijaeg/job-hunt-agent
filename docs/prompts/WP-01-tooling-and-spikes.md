Date: 2026-11-05

Related: NFR-01, NFR-06, FR-02, FR-18, FR-20, FR-22, D-4, D-5, D-6, spec §5,
§6.2, §8, §10, §13, §14

---

Work package 1: tooling, configuration, spikes D-4 and D-5.

Read CLAUDE.md and PRODUCT_SPEC.md (§5, §6.2, §8, §10, §13, §14) first. Work on a new branch
`feature/tooling-and-spikes` off the current `main`. Follow CLAUDE.md strictly: no commit, push or PR
without my explicit approval of that specific commit; stop and write decision files where required.

Reference (read-only, do not modify): my Sprint 2 project at
~/projects/turing-college/ijager-AE.AFA.updated0209.2.5 – look at its pyproject.toml, config.py,
llm.py, .github/workflows and tests/conftest.py for proven patterns (OpenRouter via ChatOpenAI,
zero-data-retention provider routing, mocked chat model, CI job). Reuse patterns, not domain code.

Dependencies approved for this package (no decision file needed for exactly these):
runtime: langchain, langchain-openai, langgraph, langgraph-checkpoint-sqlite, streamlit, pydantic,
python-dotenv, pyyaml (httpx is already there).
dev: pytest, pytest-cov, ruff, mypy, types-PyYAML.
Any other dependency → decision file.

== Step 1: tooling and configuration (NFR-01, NFR-06) ==
- pyproject.toml: real description, remove the uv placeholder script entry, ruff (line length 100,
  rules E F I B UP SIM), mypy (python 3.13, check_untyped_defs), pytest with coverage of
  `job_hunt_agent`. Replace the placeholder main() in src/job_hunt_agent/__init__.py.
- src/job_hunt_agent/config.py: loads .env first, then defines model name (default
  openai/gpt-5-mini), reasoning effort, OpenRouter base URL, ZDR provider routing, timeouts and
  limits from spec §8 and FR-20, BA API base URL and public client ID. Every value defined once.
- .env.example with placeholders only (OPENROUTER_API_KEY, optional LANGSMITH_API_KEY and
  LANGSMITH_TRACING).
- tests/test_config.py (real tests, no skips) and .github/workflows/ci.yml running ruff, mypy and
  pytest on every pull request.
- Run all checks. Done when `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`
  and `uv run mypy src` pass.
→ Then show me the commit proposal and wait.

== Step 2: spike D-4 – model and extraction quality ==
Goal: data for the decision whether openai/gpt-5-mini is good enough for (a) structured extraction
of JobRequirements (spec §6.2) and (b) tool calling – compared with one alternative,
anthropic/claude-haiku-4.5. Both only with ZDR provider routing; if a model has no ZDR endpoint,
record that and do not relax the routing.
- Script `spikes/extraction_check.py`. Input: 5 listings from spikes/fixtures/details/ (choose
  different lengths, at least one with temporary agency work, one teaser with externeURL, one with
  a contact name in the text). Before sending, clean each text as in FR-22 AC1 (mask e-mail and
  phone, drop the contact block and lines like "Frau/Herr <Name>"); show the cleaning result for
  the contact-name listing in the summary as "before → after" without the name itself.
- Per model and listing: valid JobRequirements yes/no, number of requirements, share of evidence
  quotes that are verbatim substrings of the ad text, latency, input/output tokens. Run each
  combination twice.
- Tool-calling check: bind a dummy `search_jobs` tool (spec FR-02 signature, returns a fixed
  result) and send 3 requests ("Python jobs in Hamburg, no temp agencies", "AI roles in Berlin from
  this week", "What's the weather?"). Record whether the right tool and arguments were chosen, and
  that the third request calls no tool.
- Keep the call count small (the API key is rate-limited): about 40 calls in total.
- Raw outputs (they contain ad text) go to spikes/fixtures/d4/ (gitignored). Aggregated numbers go
  to spikes/d4_results.json and a section "D-4" in spikes/NOTES.md – without ad text.

== Step 3: spike D-5 – approval with interrupt and resume in Streamlit ==
Goal: prove the HITL flow of FR-10 before the agent is built.
- Minimal prototype `spikes/hitl_app.py`: create_agent with two dummy tools, `find_item` (read) and
  `save_item` (write), HumanInTheLoopMiddleware on `save_item` (approve/edit/reject), SqliteSaver in
  spikes/fixtures/d5.sqlite, a Streamlit page with chat and approve/edit/reject buttons that resumes
  with Command(resume=...) on the same thread.
- Find out and record:
  1. Does the interrupt survive Streamlit reruns and an app restart (resume the same thread)?
  2. After reject: does the model propose the same call again? Is it interrupted again?
  3. A rejection-lock middleware (spec §5.4 #4): which hook and which position relative to
     HumanInTheLoopMiddleware make it drop an already rejected proposal before the interrupt?
     Show a working variant.
  4. SQLite connection handling across Streamlit reruns (check_same_thread, one shared connection).
  5. For D-6: is a SQLite-backed LangGraph store available in the installed packages, or would
     long-term memory need an own table? Facts only.
- Test the flow automatically with streamlit.testing.v1.AppTest (click approve, reject, edit;
  rerun; new AppTest on the same thread = restart) using a mocked chat model where possible, plus
  one short run with the real model.
- Write a 5-step manual test checklist for me (what to click, what I should see), so I can confirm
  it in the browser in about 5 minutes.
- Results to a section "D-5" in spikes/NOTES.md.

== Step 4: decision files and hand-over ==
- docs/decisions/D-4-model.md, docs/decisions/D-5-hitl-streamlit.md, docs/decisions/D-6-memory-storage.md,
  each in the format from CLAUDE.md (Question · Context · Options with numbers · Recommendation ·
  Consequences). Do not change PRODUCT_SPEC.md; list proposed spec changes under Consequences.
- Entry in docs/session_log.md.
→ Show me the commit proposal(s) for steps 2–4 (one concern per commit) and stop.
