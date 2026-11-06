"""Spike: runs ``pii.clean_ad_text`` over all raw D-1 listings, checks for leftovers.

Local-only check (CLAUDE.md "Spikes"), not imported by the package and not
part of the coverage-tracked test suite. Confirms the real production
``pii.py`` (built in WP-02 from the D-3 patterns) actually reaches "0
remaining contact names" on the raw listings collected so far, before that
module is trusted for the cleaned fixture set (D-8) and the real BA
client. Since D-10 follow-up 3 it also checks the *other* failure
direction - over-removal: ``CONTACT_MARKER_PATTERN`` used to match
"Kontakt"/"Ansprechpartner" anywhere in a line (not just a heading) and
then dropped everything to the end of the ad, silently eating requirement
and task lines on 5-6 real listings. This reports the share of each
listing's text removed and flags anything above 10 %, separating out
cases where the excess is fully explained by a legitimate (bounded)
contact block - not a regression - from genuine unexplained over-removal.

Raw ad text never leaves this machine: the detailed, per-listing output
(``spikes/fixtures/pii_check.json``) is gitignored because it still
contains full ad text; only the aggregated counts and any flagged line
(with the name replaced by ``[NAME]``) go into the "D-8 preparation"
section of ``spikes/NOTES.md``, which is committed.

Usage (from the project root):
    uv run python spikes/pii_check.py

Related: FR-22 AC1, FR-22 AC3, D-3, D-8, D-10
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from job_hunt_agent.pii import (  # noqa: E402
    EMAIL_PATTERN,
    INLINE_NAME_PATTERN,
    PHONE_NUMBER_PATTERN,
    _has_phone_context,
    clean_ad_text,
)

DETAILS_DIR = Path(__file__).resolve().parent / "fixtures" / "details"
CHECK_OUT = Path(__file__).resolve().parent / "fixtures" / "pii_check.json"
NOTES_PATH = Path(__file__).resolve().parent / "NOTES.md"

#: A listing above this share of its text removed is flagged, unless the
#: excess is fully explained by a legitimate contact-block drop (D-10
#: follow-up 3).
MAX_REMOVED_SHARE = 0.10

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


def _removed_share(raw_text: str, cleaned_text: str) -> float:
    """Fraction of ``raw_text``'s characters not present in ``cleaned_text``."""
    if not raw_text:
        return 0.0
    return 1 - len(cleaned_text) / len(raw_text)


def _share_removed_without_contact_block(raw_text: str) -> float:
    """What the removed share would be if no contact block/name line were dropped.

    Applies only the *masking* steps of ``clean_ad_text`` (inline name,
    e-mail, phone) directly to the raw text, skipping ``_drop_contact_lines``
    entirely - isolates how much of a listing's removed share is due to
    line-dropping versus substitution, so a high removed share can be told
    apart from a genuine over-removal bug (D-10 follow-up 3).

    Related: D-10
    """
    if not raw_text:
        return 0.0
    without_names = INLINE_NAME_PATTERN.sub(lambda m: f"{m.group(1)} [NAME]", raw_text)
    without_emails = EMAIL_PATTERN.sub("[EMAIL]", without_names)
    lines = []
    for line in without_emails.split("\n"):
        if _has_phone_context(line):
            line = PHONE_NUMBER_PATTERN.sub("[TELEFON]", line)
        lines.append(line)
    only_masked = "\n".join(lines)
    return 1 - len(only_masked) / len(raw_text)


def main() -> int:
    files = sorted(DETAILS_DIR.glob("*.json"))
    per_listing: list[dict[str, object]] = []
    total_counts = {"emails_masked": 0, "phones_masked": 0, "contact_lines_removed": 0}
    listings_with_flags = 0
    explained_overage: list[dict[str, object]] = []
    unexplained_overage: list[dict[str, object]] = []

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

        removed_share = _removed_share(text, cleaned)
        share_without_block = _share_removed_without_contact_block(text)
        entry = {
            "file": path.name,
            "referenznummer": raw.get("referenznummer"),
            "counts": counts,
            "removed_share": round(removed_share, 3),
            "share_without_contact_block": round(share_without_block, 3),
            "flagged_lines": flags,  # local file only - may still contain names
        }
        per_listing.append(entry)

        if removed_share > MAX_REMOVED_SHARE:
            if share_without_block <= MAX_REMOVED_SHARE:
                explained_overage.append(entry)
            else:
                unexplained_overage.append(entry)

    CHECK_OUT.write_text(
        json.dumps({"listings": per_listing, "totals": total_counts}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary_lines = [
        "",
        f"## D-8 preparation: pii_check.py on the raw listings ({len(per_listing)} checked)",
        "",
        "Script: `spikes/pii_check.py`. Per-listing detail (still contains ad text,",
        "gitignored): `spikes/fixtures/pii_check.json`. Runs the real",
        "`job_hunt_agent.pii.clean_ad_text` - the same function the BA client and the",
        "cleaned fixture set (D-8) will use - over all raw listings collected so far.",
        "Since D-10 follow-up 3 it also reports the share of each listing's text",
        f"removed and flags anything above {MAX_REMOVED_SHARE:.0%}, separating a",
        "legitimate (bounded) contact-block drop from genuine over-removal.",
        "",
        f"- Listings checked: {len(per_listing)}",
        f"- E-mail addresses masked: {total_counts['emails_masked']}",
        f"- Phone numbers masked: {total_counts['phones_masked']}",
        f"- Contact/name lines removed: {total_counts['contact_lines_removed']}",
        f"- Listings with a still-suspicious line after cleaning: {listings_with_flags}",
        f"- Listings above {MAX_REMOVED_SHARE:.0%} removed, explained by a contact "
        f"block alone: {len(explained_overage)}",
        f"- Listings above {MAX_REMOVED_SHARE:.0%} removed, NOT explained by a "
        f"contact block: {len(unexplained_overage)}",
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
    if explained_overage:
        summary_lines.append(
            "Listings above the removed-share threshold, explained by a contact "
            "block alone (not a regression):"
        )
        summary_lines.append("")
        for entry in explained_overage:
            summary_lines.append(
                f"- `{entry['file']}`: {entry['removed_share']:.0%} removed "
                f"({entry['counts']['contact_lines_removed']} contact/name lines)"
            )
        summary_lines.append("")
    if unexplained_overage:
        summary_lines.append("Listings above the removed-share threshold, NOT explained:")
        summary_lines.append("")
        for entry in unexplained_overage:
            summary_lines.append(f"- `{entry['file']}`: {entry['removed_share']:.0%} removed")
        summary_lines.append("")

    goal_met = listings_with_flags == 0 and not unexplained_overage
    if goal_met:
        summary_lines.append(
            "**Goal met: 0 remaining contact names, no listing over "
            f"{MAX_REMOVED_SHARE:.0%} removed unless explained by a contact block.**"
        )
    else:
        summary_lines.append("**Goal not yet met** - see above.")
    summary_lines.append("")

    with NOTES_PATH.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(summary_lines))

    print(
        f"Checked {len(per_listing)} listings; {listings_with_flags} still flagged; "
        f"{len(explained_overage)} over {MAX_REMOVED_SHARE:.0%} (contact block only); "
        f"{len(unexplained_overage)} over {MAX_REMOVED_SHARE:.0%} (unexplained)."
    )
    print(f"Detail: {CHECK_OUT}")
    print(f"Summary appended to: {NOTES_PATH}")
    return 0 if goal_met else 1


if __name__ == "__main__":
    sys.exit(main())
