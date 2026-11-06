"""PII middleware wiring (spec §5.4 #2, FR-22 AC2): built-in email + custom phone.

The built-in ``url`` detector is deliberately not used - it would redact
the links to listings (FR-22 AC2). The phone detector reuses
``pii.py``'s own context-gated regexes (never matching a bare reference
number such as ``19522-0068291613-S`` - the exact D-1 regression, FR-22
AC5) rather than a second, independent implementation.

Related: FR-22 AC1, FR-22 AC2, FR-22 AC5, D-3
"""

from __future__ import annotations

from langchain.agents.middleware import PIIMatch, PIIMiddleware

from job_hunt_agent.pii import PHONE_CONTEXT_PATTERN, PHONE_NUMBER_PATTERN, PHONE_PREFIX_PATTERN


def detect_phone_pii(text: str) -> list[PIIMatch]:
    """Finds phone numbers in ``text``, gated the same way as ``pii.clean_ad_text``.

    Only matches on a line that already carries a phone-context keyword or
    a ``+49``/``0049`` prefix - the same rule that keeps a bare reference
    number from ever being mistaken for a phone number (FR-22 AC5).

    Related: FR-22 AC2, FR-22 AC5
    """
    matches: list[PIIMatch] = []
    offset = 0
    for line in text.split("\n"):
        has_context = bool(PHONE_CONTEXT_PATTERN.search(line) or PHONE_PREFIX_PATTERN.search(line))
        if has_context:
            for m in PHONE_NUMBER_PATTERN.finditer(line):
                matches.append(
                    {
                        "type": "phone",
                        "value": m.group(0),
                        "start": offset + m.start(),
                        "end": offset + m.end(),
                    }
                )
        offset += len(line) + 1  # +1 for the "\n" split away
    return matches


def build_pii_middlewares() -> list[PIIMiddleware]:
    """Email (built-in detector) and phone (custom) on tool results (FR-22 AC2).

    Related: FR-22 AC1, FR-22 AC2
    """
    return [
        PIIMiddleware("email", strategy="redact", apply_to_tool_results=True),
        PIIMiddleware(
            "phone", detector=detect_phone_pii, strategy="redact", apply_to_tool_results=True
        ),
    ]
