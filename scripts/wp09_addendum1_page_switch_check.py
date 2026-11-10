"""Real-model check for Addendum 1 to WP-09: a setting survives a page switch.

Drives the actual Streamlit UI through ``AppTest`` (not ``build_agent``
directly, unlike ``wp09_settings_check.py``): switches to the developer
settings page, selects ``anthropic/claude-haiku-4.5`` and turns on demo mode,
switches to the main page, and submits the demo query - then reads which
model actually answered off the *response* (``response_metadata["model_name"]``,
captured by ``usage.UsageCallbackHandler``), never off the configured
setting, as proof the fix (moving each setting onto a key no widget owns,
``ui_shared.sync_setting_from_widget``) made the right model run, not just
that the session-state key looked right.

Usage (needs OPENROUTER_API_KEY):
    uv run python scripts/wp09_addendum1_page_switch_check.py

Writes: appends one entry to eval/results/wp09_settings_check.json

Related: FR-18 AC1, FR-19 AC3, D-17, WP-09 Addendum 1
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "data" / "wp09_addendum1_check.sqlite"
RESULTS_PATH = PROJECT_ROOT / "eval" / "results" / "wp09_settings_check.json"
APP_PATH = str(PROJECT_ROOT / "app.py")

#: D-10's recorded München search - guarantees the fixture set returns
#: listings for it (same query as wp09_settings_check.py).
DEMO_QUERY = "Find Softwareentwickler jobs in München."


def _selectbox(at: Any, label: str) -> Any:
    return next(sb for sb in at.selectbox if sb.label == label)


def _toggle(at: Any, label: str) -> Any:
    return next(tg for tg in at.toggle if tg.label == label)


def main() -> int:
    os.environ["DB_PATH"] = str(DB_PATH)
    if DB_PATH.exists():
        DB_PATH.unlink()

    from streamlit.testing.v1 import AppTest

    from ui_shared import (
        CHAT_MODEL_KEY,
        LAST_TURN_AGENT_LOOP_USAGE_KEY,
        LAST_TURN_EXTRACTION_USAGE_KEY,
    )

    at = AppTest.from_file(APP_PATH, default_timeout=120)
    at.run()
    assert not at.exception, at.exception

    at.switch_page("pages/4_Developer_settings.py")
    at.run()
    assert not at.exception, at.exception
    _selectbox(at, "Chat model").select("anthropic/claude-haiku-4.5").run()
    _toggle(at, "Demo mode").set_value(True).run()
    assert at.session_state[CHAT_MODEL_KEY] == "anthropic/claude-haiku-4.5"

    at.switch_page("app.py")
    at.run()
    assert not at.exception, at.exception
    chat_model_after_switch = at.session_state[CHAT_MODEL_KEY]

    at.chat_input[0].set_value(DEMO_QUERY).run()
    assert not at.exception, at.exception

    agent_loop = at.session_state.get(LAST_TURN_AGENT_LOOP_USAGE_KEY, [])
    extraction = at.session_state.get(LAST_TURN_EXTRACTION_USAGE_KEY, [])
    models_in_response_metadata = sorted({r.model for r in [*agent_loop, *extraction]})

    caption_texts = [str(c.value) for c in at.caption]
    model_caption = next((c for c in caption_texts if c.startswith("Model:")), None)

    record = {
        "label": "page_switch_check",
        "scenario": (
            "Addendum 1 to WP-09: select haiku on the settings page, switch to the "
            "main page, run the demo query"
        ),
        "chat_model_key_after_switch": chat_model_after_switch,
        "models_in_response_metadata": models_in_response_metadata,
        "per_turn_usage_caption": model_caption,
        "confirmed_haiku_ran": models_in_response_metadata == ["anthropic/claude-haiku-4.5"],
    }

    existing = json.loads(RESULTS_PATH.read_text(encoding="utf-8")) if RESULTS_PATH.exists() else []
    existing.append(record)
    RESULTS_PATH.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(record, indent=2, ensure_ascii=False))
    print(f"\nAppended to {RESULTS_PATH}")
    return 0 if record["confirmed_haiku_ran"] else 1


if __name__ == "__main__":
    sys.exit(main())
