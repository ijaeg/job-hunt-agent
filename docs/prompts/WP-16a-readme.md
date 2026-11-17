# WP-16a: README — independent verification

Date: 2026-11-17
Related: README.md, PRODUCT_SPEC.md (coach update v0.1.14)

## Prompt (verbatim)

WP-16a: README - independent verification (the README was written by the coach)

Save this prompt verbatim as docs/prompts/WP-16a-readme.md (header: date, Related line)
as the first step. Branch: feature/readme off main. Uncommitted on main and part of this
package: README.md (new, written by the coach) and PRODUCT_SPEC.md (coach update
v0.1.14). No commits, pushes, PRs or merges by you - propose the commit and wait for
Ingo's approval.

Your role is verification only: do NOT edit README.md or PRODUCT_SPEC.md. Report every
finding; the coach fixes them. The writer does not check his own work.

Check, and report each item as OK or a finding with file and line:
1. Setup from a fresh clone: clone the repository into a temporary folder, follow the
   README's Setup section exactly (cp .env.example .env with the existing key copied in,
   uv sync, start the app headless for about 20 seconds and confirm it serves HTTP 200).
   Delete the temporary folder afterwards.
2. Every relative link and file path in README.md exists in the repository.
3. Every number in README.md matches the file it cites (fit evaluation, trajectory
   evaluation, explanation check, safety tests, test count / coverage from a fresh
   `uv run pytest`, 65 / 62 / 3 fixture listings, limits 10 model calls / 3 searches /
   25 listings per search / 8 per assess_fit, S1 "3 of 6 runs" across the three
   trajectory runs dev, dev_run2, test). List each number with its source and verdict.
4. Every factual statement about the code matches the code, at least: the middleware
   order and the Mermaid diagram vs src/job_hunt_agent/agent.py; the tool table and the
   approval column; tool toggles, demo mode location, model options and defaults;
   default user "alex" seeded with the demo profile; what is stored where and every
   "Delete with" entry in the data table (does each delete path exist in the UI?);
   DB path; zero data retention settings; PIIMiddleware usage; rejection-lock behaviour;
   the commands in "Evaluation results > Commands" exist with these arguments; the CI
   workflow runs the checks named.
5. Mermaid: if a Mermaid CLI is available via npx, validate the diagram; otherwise
   report "not validated".
6. Anything in README.md that contradicts PRODUCT_SPEC.md or a decision file.
Run the usual checks (pytest, ruff, mypy) and add a session log entry.
- HALT: report the findings list and the word count. Propose the commit (prompt file,
  README.md, PRODUCT_SPEC.md, session log) but do not commit until the coach's fixes
  are in.

Stop rule: any change to a file other than the prompt file and the session log ->
stop and ask first.
