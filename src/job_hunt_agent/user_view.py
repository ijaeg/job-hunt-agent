"""Pure helpers for user selection and thread titles (FR-13 AC2, D-15, D-16).

Like ``ui_view.py`` and ``tracker_view.py``, this module has no Streamlit,
LLM or network calls (CLAUDE.md "Architecture and dependency direction") -
``ui_shared.py`` and ``app.py`` call these functions with plain strings
already read from a widget or the checkpointer.

Related: FR-13 AC2, FR-14, D-15, D-16
"""

from __future__ import annotations

import re

#: D-15: a thread's title is its first user message, cut to this length.
MAX_THREAD_TITLE_LENGTH = 60

#: D-16: a display name's maximum length.
MAX_USER_NAME_LENGTH = 40

_VALID_NAME_RE = re.compile(r"^[A-Za-z0-9 \-]+$")
_SLUG_COLLAPSE_RE = re.compile(r"[^a-z0-9]+")


def thread_title(first_message: str) -> str:
    """Cuts a thread's title to :data:`MAX_THREAD_TITLE_LENGTH` characters (D-15).

    Args:
        first_message: The thread's first user message, as typed.

    Related: D-15
    """
    text = first_message.strip()
    if len(text) <= MAX_THREAD_TITLE_LENGTH:
        return text
    return text[:MAX_THREAD_TITLE_LENGTH].rstrip()


def validate_user_name(name: str) -> str | None:
    """Validates a new user's display name (D-16).

    Args:
        name: The name as typed in the sidebar's "add new user" field.

    Returns:
        A friendly error message, or ``None`` if the name is valid:
        1-40 characters of letters, digits, spaces and hyphens only.

    Related: D-16
    """
    stripped = name.strip()
    if not stripped:
        return "Enter a name."
    if len(stripped) > MAX_USER_NAME_LENGTH:
        return f"Name must be at most {MAX_USER_NAME_LENGTH} characters."
    if not _VALID_NAME_RE.match(stripped):
        return "Name may only contain letters, digits, spaces and hyphens."
    return None


def slugify_user_id(name: str) -> str:
    """Derives a lowercase user id from a display name (D-16).

    Args:
        name: A name already checked by :func:`validate_user_name`; runs
            of anything other than letters/digits collapse to one hyphen
            (so "Jane  Doe" and "jane-doe" both become ``"jane-doe"``).

    Related: D-16
    """
    return _SLUG_COLLAPSE_RE.sub("-", name.strip().lower()).strip("-")


def order_users(user_ids: list[str]) -> list[str]:
    """Orders user ids alphabetically, case-insensitively, for the sidebar picker."""
    return sorted(user_ids, key=str.lower)
