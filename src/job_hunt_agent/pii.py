"""Ad-text cleaning: mask contact data before free text reaches the model.

Pure functions, no LLM or network calls (CLAUDE.md "Architecture"). Applied
by ``ba_client.py`` to free-text fields only - title and
``stellenangebotsBeschreibung`` - never to IDs or structured fields
(FR-22 AC5). The BA job board API has no separate contact fields (D-3):
e-mail addresses, phone numbers and contact names all live inside the free
text, so this module has to find and remove them with text rules instead of
dropping a field.

The D-1 spike's own ad-hoc cleaning once masked the reference number
``19522-0068291613-S`` as ``19522-[TELEFON]-S`` because its phone regex
matched any string starting with a leading ``0``, with no context check.
Every phone match here is gated on a phone-context keyword or a ``+49``/
``0049`` prefix on the *same line*, which keeps reference numbers, postal
codes, salaries, dates and years untouched (FR-22 AC5).

Related: FR-22 AC1, FR-22 AC2, FR-22 AC5, D-3
"""

from __future__ import annotations

import re

#: E-mail addresses anywhere in the text (FR-22 AC1).
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

#: A line carries phone context if it contains one of these markers, or a
#: German country-code prefix. Matched with ``search`` (not ``fullmatch``),
#: so "Mobilnummer", "Telefonnummer" and "Faxnummer" all qualify.
PHONE_CONTEXT_PATTERN = re.compile(r"\btel\.?\w*|\btelefon\w*|\bmobil\w*|\bhandy\w*|\bfax\w*", re.I)
PHONE_PREFIX_PATTERN = re.compile(r"\+49|0049")

#: A phone number: an optional country-code prefix (or a leading 0) followed
#: by the typical grouping of digits, spaces, slashes, parentheses and
#: hyphens. Only ever applied on a line that already passed the context
#: check above, so a bare reference number such as ``19522-0068291613-S``
#: is never a candidate (FR-22 AC5).
PHONE_NUMBER_PATTERN = re.compile(r"(?:\+49|0049|0)[\d\s/()\-]{5,}\d")

#: A line that is nothing but "Frau <Name>" / "Herr(n) <Name>" - a
#: signature line (D-3 patterns 2 and 5). Up to three capitalised name
#: tokens so "Herr Torben Schulz" and "Frau Elif Rühl" both match.
NAME_SIGNATURE_LINE_PATTERN = re.compile(
    r"^\s*(?:Frau|Herrn?)\s+[A-ZÄÖÜ][\wäöüß\-]*(?:\s+[A-ZÄÖÜ][\wäöüß\-]*){0,2}\s*$"
)

#: Inline "bei Frau <Name>" / "... bei Herrn <Name>" (D-3 pattern 1); the
#: name is replaced, the surrounding sentence is kept.
INLINE_NAME_PATTERN = re.compile(
    r"\bbei\s+(Frau|Herrn?)\s+([A-ZÄÖÜ][\wäöüß\-]*(?:\s+[A-ZÄÖÜ][\wäöüß\-]*){0,2})"
)

#: A header line that starts a contact block - "Ansprechpartner",
#: "Kontakt", "Ihr Kontakt", "Ihr Ansprechpartner" (D-3 pattern 4).
#: Everything from this line to the end of the text is the signature /
#: contact block in every BA ad seen in the D-1 spike.
CONTACT_MARKER_PATTERN = re.compile(r"\b(ihr\s+)?ansprechpartner\b|\b(ihr\s+)?kontakt\b", re.I)

#: A line that is just "<First> <Last>" with no "Frau/Herr" prefix
#: (D-3 pattern 3: a name immediately before a phone-context line).
PERSON_NAME_LINE_PATTERN = re.compile(
    r"^\s*[A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜ][a-zäöüß]+)?"
    r"\s+[A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜ][a-zäöüß]+)?\s*$"
)


def _has_phone_context(line: str) -> bool:
    return bool(PHONE_CONTEXT_PATTERN.search(line) or PHONE_PREFIX_PATTERN.search(line))


def _drop_contact_lines(text: str) -> tuple[str, int]:
    """Removes name-signature lines and the trailing contact block.

    Three of the five D-3 name patterns are line-shaped: a standalone
    "Frau/Herr <Name>" signature line (patterns 2 and 5), a bare name line
    immediately followed by a phone-context line (pattern 3), and a
    contact-marker line that opens the block running to the end of the ad
    (pattern 4). The fourth and fifth pattern reuse the same two rules.

    Related: FR-22 AC1, D-3
    """
    lines = text.split("\n")
    kept: list[str] = []
    removed = 0
    contact_block = False

    for i, line in enumerate(lines):
        if contact_block:
            removed += 1
            continue
        if CONTACT_MARKER_PATTERN.search(line):
            contact_block = True
            removed += 1
            continue
        if NAME_SIGNATURE_LINE_PATTERN.match(line):
            removed += 1
            continue
        if PERSON_NAME_LINE_PATTERN.match(line):
            next_line = lines[i + 1] if i + 1 < len(lines) else ""
            if _has_phone_context(next_line):
                removed += 1
                continue
        kept.append(line)

    return "\n".join(kept), removed


def clean_ad_text(text: str) -> tuple[str, dict[str, int]]:
    """Masks e-mail addresses and phone numbers, drops contact names.

    Applies only to free text (title, ``stellenangebotsBeschreibung``);
    never call this on an ID or a structured field (FR-22 AC5).

    Args:
        text: Raw ad text (German), already a plain string (no HTML
            handling - the BA API returns plain text in this field, per
            D-1).

    Returns:
        A tuple of the cleaned text and a count of what was removed:
        ``emails_masked``, ``phones_masked`` and ``contact_lines_removed``.

    Related: FR-22 AC1, FR-22 AC5, D-3
    """
    without_contact_lines, contact_lines_removed = _drop_contact_lines(text)

    inline_names_removed = 0

    def _mask_inline_name(match: re.Match[str]) -> str:
        nonlocal inline_names_removed
        inline_names_removed += 1
        return f"bei {match.group(1)} [NAME]"

    without_inline_names = INLINE_NAME_PATTERN.sub(_mask_inline_name, without_contact_lines)

    emails_masked = len(EMAIL_PATTERN.findall(without_inline_names))
    without_emails = EMAIL_PATTERN.sub("[EMAIL]", without_inline_names)

    phones_masked = 0
    cleaned_lines: list[str] = []
    for line in without_emails.split("\n"):
        if _has_phone_context(line):
            line, n = PHONE_NUMBER_PATTERN.subn("[TELEFON]", line)
            phones_masked += n
        cleaned_lines.append(line)
    cleaned_text = "\n".join(cleaned_lines)

    counts = {
        "emails_masked": emails_masked,
        "phones_masked": phones_masked,
        "contact_lines_removed": contact_lines_removed + inline_names_removed,
    }
    return cleaned_text, counts
