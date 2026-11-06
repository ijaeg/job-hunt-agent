# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this project is

**Job Hunt Agent** — a Streamlit app for software developers looking for a job in
Germany. The user describes in English what they are looking for; a ReAct
tool-calling agent searches the job board of the German Federal Employment Agency
(BA), refines the search on its own, loads selected listings, assesses their fit
against the user's profile and presents an explainable shortlist. Saving to the
application tracker and storing preferences require the user's approval
(human-in-the-loop).

Turing College, AI Engineering Sprint 3 ("Building with AI Agents"). Python 3.13,
uv, LangChain `create_agent` (LangGraph runtime) against OpenRouter, SQLite,
httpx, Pydantic, Streamlit, LangSmith.

## Roles

- **Ingo** is the business owner. He makes every product and evaluation
  decision and must be able to explain the product, the architecture, the data
  flow and every test and evaluation result in the review.
- **Claude Code** implements, tests and runs things in this repository.
- A separate **Claude chat** (the coach) prepares decisions and explanations for
  Ingo. It reads the files listed under "Hand-over" below.

## The spec is the source of truth

[`PRODUCT_SPEC.md`](PRODUCT_SPEC.md) defines everything: functional requirements
`FR-01`–`FR-23` with acceptance criteria, non-functional requirements
`NFR-01`–`NFR-09`, the agent architecture in §5, the structured formats in §6,
the fit rubric in §7, error handling in §8, the evaluation in §9 and the code
structure in §11.

- Read the relevant FR and its ACs **before** writing code for it.
- Every commit message, docstring, test name and TODO names the requirement IDs
  it belongs to. A docstring without a `Related:` line is incomplete.
- Order of work: the **core journey** first (search → refinement → details →
  fit assessment → shortlist → approval → save → still there after restart),
  then `Should`, then `Could`.
- If the code and the spec disagree, stop and report it. **Do not change
  `PRODUCT_SPEC.md` on your own** — propose the change (see "Decisions").

## Decisions: stop and ask

Ingo decides; Claude Code prepares. Stop and write a decision file instead of
choosing yourself when a task touches any of these:

- an item marked **Open** in spec §14 (D-4 and later),
- a threshold, weight or category rule of the fit rubric (§7),
- the content of an evaluation set (scenarios, labels) or the reading of its
  results,
- a deviation from the spec, a new dependency, or a change to a tool contract
  (§6),
- anything that would store or send personal data differently from FR-22.

**Decision file:** `docs/decisions/<ID>-<short-name>.md` with these sections:
*Question* · *Context* (one paragraph) · *Options* (2–3, each with numbers from
a run where possible) · *Recommendation* · *Consequences* (which FRs, files,
tests change). Then end the session with a short summary that names the file.
Continue only after Ingo's answer is recorded in the file (*Decision:* line with
date).

## Hand-over to the coach

**Prompts are part of the record.** As the first step of every work package,
save the prompt verbatim as `docs/prompts/WP-<NN>-<short-name>.md` (two-digit
number, next free one) with a header: date and `Related:` line (requirement and
decision IDs). Include it in the first commit of the package. Never put keys or
ad text into a prompt file.

At the end of every work session, append an entry to `docs/session_log.md`:
date, what was done (with requirement IDs), state of the checks (pytest / ruff /
mypy), new or open decision files, and what comes next. Evaluation and spike
results go to `eval/results/` or `spikes/` as CSV or JSON plus a short Markdown
summary; never only to the terminal.

## Checks before hand-over

Run these yourself, in the same session, before you report a step or a work
package as done. Report each result with numbers; a failed check is fixed or
reported, never skipped.

1. **Code checks:** `uv run pytest` (no skipped tests), `uv run ruff check .`,
   `uv run ruff format --check .`, `uv run mypy src` (plus `app.py pages` once
   they exist).
2. **Real-model smoke run:** any change to tools, prompts, middleware or the
   agent gets at least one run against the real model, not only the mocked
   one (a mocked model cannot catch schema or binding errors).
3. **Data integrity** whenever fixtures, recorded searches or evaluation sets
   change: every `referenznummer` is valid (no `[`, exists where it is
   referenced); the PII check reports 0 names, e-mail addresses and phone
   numbers; text cleaning removes at most 10 % of any ad text unless the
   excess is a contact block (list those cases).
4. **Data covers the scenario:** before building on a demo or evaluation
   scenario, check that the data can actually produce it (e.g. a search that
   must return more than 50 results, listings that must exist in the fixture
   set). If not, stop and report.
5. **Docs match the data:** numbers and model names in `spikes/NOTES.md`,
   decision files and the session log are taken from the result files, not
   from memory.
6. **Scope of the package:** if a step turns out much larger than planned,
   stop at the next clean point and report instead of continuing.

## Commands

**uv only.** Never run bare `pip`, `python` or `pytest`.

```bash
uv sync                                     # install, including dev dependencies
uv run streamlit run app.py                 # run the app (needs OPENROUTER_API_KEY)
uv run pytest                               # tests with coverage (NFR-05)
uv run ruff check .                         # lint (NFR-06)
uv run ruff format .                        # format (NFR-06)
uv run mypy src app.py pages                # type check (NFR-06)
uv run python spikes/ba_api_spike.py        # job board API spike (D-1)

uv add <package>                            # runtime dependency (decision file first)
uv add --dev <package>                      # dev dependency
```

Evaluation commands are added here when the scripts exist (§9). All checks must
pass before a pull request.

## Architecture and dependency direction

```text
app.py · pages/                     UI: chat, shortlist, approval, tracker, memory, settings
  ↓
agent.py                            create_agent: model, tools, middleware, state, checkpointer
  ↓
tools/ · middleware/                search, details, assess, tracker, memory; guards, limits, lock
  ↓
ba_client.py · rubric.py · pii.py · storage.py
  ↓
models.py · state.py · config.py    contracts and constants; depend on nothing in the package
```

Dependencies point **downwards only**. `rubric.py` and `pii.py` are pure
functions without LLM or network calls. All prompt text lives in `prompts/*.md`.

## Invariants

Breaking one is a bug, not a trade-off.

1. **OpenRouter only** for the language model, with zero data retention
   (spec §5.5). Model names, limits and timeouts come from `config.py`.
2. **The model proposes, the code decides.** Hard exclusions, the fit category
   and the approval of write actions are code (spec §1.2). The model never sets
   a fit category.
3. **No write without approval.** `save_to_tracker` and `remember` run only
   after an approval recorded by `HumanInTheLoopMiddleware`; a rejected action
   is never executed later (FR-10).
4. **Personal data.** Ad texts are cleaned before they reach the model (FR-22).
   Raw API responses are never committed (`spikes/fixtures/` is gitignored);
   only the cleaned fixture set in `data/samples/fixtures/` is, and a test checks
   it for names, e-mail addresses and phone numbers. No real CV, no API key in
   the repository, the UI or an error message.
5. **Tests mock every external call.** No test reaches OpenRouter or the BA
   API; use a mocked chat model and `httpx.MockTransport`.
6. **Evaluation runs on the fixture set** (demo mode), so results are
   reproducible. Development and test sets stay separate; the test set is never
   used for tuning.
7. **No stack trace in the UI.** Errors become friendly messages and leave the
   chat usable (spec §8).
8. **English only** in the UI, the docs and the code. German appears only in
   quoted ad text, always with an English translation.

## Conventions

- **Commits:** lowercase imperative, requirement IDs in the subject, one concern
  per commit, e.g. `add search_jobs tool (FR-02)`.
- **No autonomous commits.** Before **every** commit, show Ingo the files to be
  committed, a short summary of the changes and the proposed commit message,
  then wait. Commit only after his explicit approval of **that** commit, with
  his corrections applied; an approval never carries over to the next commit.
  The same applies to `git push`, opening or merging pull requests and any
  other change to the Git history.
- **Branches:** feature branches off `main`, named `feature/<short-description>`;
  never commit to `main`; merged via pull request with a merge commit. Never
  delete a local branch (`git branch -d`) before the project ends.
- **Docstrings:** Google style with `Args`, `Returns`, `Raises`, ending with a
  `Related:` line. Every module starts with `from __future__ import annotations`
  and a module docstring.
- **Types:** full annotations; mypy must be clean. **Line length:** 100.
- **Unimplemented code** raises `NotImplementedError("FR-xx: …")`. No skipped
  tests: a placeholder test uses `pytest.mark.xfail(strict=True)`.
- **Spikes** live in `spikes/`, are kept as a record and are not imported by the
  package.
