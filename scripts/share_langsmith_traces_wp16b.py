"""Public share links for the WP-16b LangSmith traces (spec §9.5, Addendum 1).

Calls ``Client.share_run`` on every run id in ``eval/results/langsmith_wp16b.json``
and writes the resulting public link next to each entry. Visibility change approved
by Ingo (Addendum 1 to ``docs/prompts/WP-16b-traces-screenshots-demo.md`,
2026-11-18): "public share links for all eight traces" - not run until that
approval was recorded, per CLAUDE.md's "stop and ask" rule and D-18's own text
("no share_run call... without Ingo's decision").

``Client.share_run`` is deprecated upstream in favour of ``client.runs.share.create``
(removal after 2027-01-31, well past this project's submission date) but is the
only share method this SDK version exposes; used as-is rather than adding a new
dependency pin for one script.

Idempotent: a run already shared is skipped (its existing link is read back via
``read_run_shared_link`` instead of creating a second one).

Usage (needs LANGSMITH_API_KEY):
    uv run python scripts/share_langsmith_traces_wp16b.py

Writes:
    eval/results/langsmith_wp16b.json   (adds a "share_url" field per run)

Related: spec §9.5, D-18, WP-16b
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from job_hunt_agent import config, tracing  # noqa: E402

RESULTS_PATH = PROJECT_ROOT / "eval" / "results" / "langsmith_wp16b.json"


def main() -> int:
    if not tracing.langsmith_key_present():
        print(f"{config.LANGSMITH_API_KEY_ENV} is not set - nothing to do.")
        return 1
    client = tracing.build_client()
    if client is None:
        print("Could not build a LangSmith client - check the key and LANGSMITH_ENDPOINT.")
        return 1
    if not RESULTS_PATH.exists():
        print(f"{RESULTS_PATH} does not exist - run the trace-recording script first.")
        return 1

    data = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        for run in data["runs"]:
            existing = client.read_run_shared_link(run["run_id"])
            if existing:
                run["share_url"] = existing
                print(f"[{run['scenario']}] already shared: {existing}")
                continue
            share_url = client.share_run(run["run_id"])
            run["share_url"] = share_url
            print(f"[{run['scenario']}] shared: {share_url}")

    RESULTS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults: {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
