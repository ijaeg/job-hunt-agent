"""Spike: runs ``pii.clean_ad_text`` over all raw D-1 listings, checks for leftovers.

Local-only check (CLAUDE.md "Spikes"), not imported by the package and not
part of the coverage-tracked test suite. Confirms the real production
``pii.py`` (built in WP-02 from the D-3 patterns) actually reaches "0
remaining contact names" on the 40 raw listings the D-1 spike collected,
before that module is trusted for the cleaned fixture set (D-8) and the
real BA client.

Raw ad text never leaves this machine: the detailed, per-listing output
(``spikes/fixtures/pii_check.json``) is gitignored because it still
contains full ad text; only the aggregated counts and any flagged line
(with the name replaced by ``[NAME]``) go into the "D-8 preparation"
section of ``spikes/NOTES.md``, which is committed.

Usage (from the project root):
    uv run python spikes/pii_check.py

Related: FR-22 AC1, FR-22 AC3, D-3, D-8
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from job_hunt_agent.pii import clean_ad_text  # noqa: E402

DETAILS_DIR = Path(__file__).resolve().parent / "fixtures" / "details"
CHECK_OUT = Path(__file__).resolve().parent / "fixtures" / "pii_check.json"
NOTES_PATH = Path(__file__).resolve().parent / "NOTES.md"

#: After cleaning, a line is still "suspicious" if it carries one of the
#: exact contact keywords ``pii.py`` is supposed to have already acted on
#: (``Frau``/``Herr(n)``, ``Ansprechpartner``, ``Kontakt``). Deliberately
#: *not* a generic "two capitalised words" heuristic: German capitalises
#: every noun, so headers like "Deine Aufgaben" or "Mobiles Arbeiten" would
#: trip that on every listing without ever being a name - noise that would
#: bury the one real signal this check exists to find.
SUSPICIOUS_PATTERN = re.compile(r"\b(frau|herrn?)\b|\bansprechpartner\b|\bkontakt\b", re.I)

#: Used only to redact a flagged line before it is written to NOTES.md - a
#: best-effort mask for the summary, not a replacement for ``pii.py`` itself.
NAME_TOKEN_PATTERN = re.compile(r"[A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜ][a-zäöüß]+)?")


def redact_for_summary(line: str) -> str:
    """Replaces capitalised word tokens with ``[NAME]`` for the committed summary."""
    return NAME_TOKEN_PATTERN.sub("[NAME]", line).strip()


def flagged_lines(cleaned_text: str) -> list[str]:
    """Lines that still carry a contact keyword `clean_ad_text` did not already redact.

    A line containing the literal ``[NAME]`` marker is cleaning that
    *worked* (the name was replaced in place, the surrounding sentence
    kept) - excluded here so it is not reported as a miss.
    """
    return [
        line.strip()
        for line in cleaned_text.split("\n")
        if line.strip() and "[NAME]" not in line and SUSPICIOUS_PATTERN.search(line)
    ]


def main() -> int:
    files = sorted(DETAILS_DIR.glob("*.json"))
    per_listing: list[dict[str, object]] = []
    total_counts = {"emails_masked": 0, "phones_masked": 0, "contact_lines_removed": 0}
    listings_with_flags = 0

    for path in files:
        raw = json.loads(path.read_text(encoding="utf-8"))
        text = raw.get("stellenangebotsBeschreibung", "")
        if not isinstance(text, str) or not text:
            continue
        cleaned, counts = clean_ad_text(text)
        for key in total_counts:
            total_counts[key] += counts[key]
        flags = flagged_lines(cleaned)
        if flags:
            listings_with_flags += 1
        per_listing.append(
            {
                "file": path.name,
                "referenznummer": raw.get("referenznummer"),
                "counts": counts,
                "flagged_lines": flags,  # local file only - may still contain names
            }
        )

    CHECK_OUT.write_text(
        json.dumps({"listings": per_listing, "totals": total_counts}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary_lines = [
        "",
        "## D-8 preparation: pii_check.py on the 40 raw D-1 listings (2026-11-06)",
        "",
        "Script: `spikes/pii_check.py`. Per-listing detail (still contains ad text,",
        "gitignored): `spikes/fixtures/pii_check.json`. Runs the real",
        "`job_hunt_agent.pii.clean_ad_text` - the same function the BA client and the",
        "cleaned fixture set (D-8) will use - over all raw listings from the D-1 spike.",
        "",
        f"- Listings checked: {len(per_listing)}",
        f"- E-mail addresses masked: {total_counts['emails_masked']}",
        f"- Phone numbers masked: {total_counts['phones_masked']}",
        f"- Contact/name lines removed: {total_counts['contact_lines_removed']}",
        f"- Listings with a still-suspicious line after cleaning: {listings_with_flags}",
        "",
    ]
    if listings_with_flags:
        summary_lines.append("Flagged lines (names redacted for this committed summary):")
        summary_lines.append("")
        for entry in per_listing:
            flags = entry["flagged_lines"]
            if not flags:
                continue
            assert isinstance(flags, list)
            for line in flags:
                summary_lines.append(f"- `{entry['file']}`: {redact_for_summary(line)}")
        summary_lines.append("")
        summary_lines.append("**Goal of 0 remaining contact names not yet met** - see above.")
    else:
        summary_lines.append("**Goal met: 0 remaining contact names** after cleaning.")
    summary_lines.append("")

    with NOTES_PATH.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(summary_lines))

    print(f"Checked {len(per_listing)} listings; {listings_with_flags} still flagged.")
    print(f"Detail: {CHECK_OUT}")
    print(f"Summary appended to: {NOTES_PATH}")
    return 0 if listings_with_flags == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
