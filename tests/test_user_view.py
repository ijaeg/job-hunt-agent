"""Tests for :mod:`job_hunt_agent.user_view` (FR-13 AC2, D-15, D-16).

Related: FR-13 AC2, D-15, D-16
"""

from __future__ import annotations

from job_hunt_agent.user_view import (
    MAX_THREAD_TITLE_LENGTH,
    MAX_USER_NAME_LENGTH,
    order_users,
    slugify_user_id,
    thread_title,
    validate_user_name,
)

# ---------------------------------------------------------------------------
# thread_title (D-15): first user message, cut to 60 characters
# ---------------------------------------------------------------------------


def test_thread_title_keeps_a_short_message_unchanged() -> None:
    assert thread_title("Python jobs in Hamburg") == "Python jobs in Hamburg"


def test_thread_title_strips_surrounding_whitespace() -> None:
    assert thread_title("  Python jobs  ") == "Python jobs"


def test_thread_title_cuts_a_long_message_to_the_max_length() -> None:
    long_message = "x" * 100
    title = thread_title(long_message)
    assert len(title) == MAX_THREAD_TITLE_LENGTH
    assert title == "x" * MAX_THREAD_TITLE_LENGTH


def test_thread_title_does_not_leave_trailing_whitespace_at_the_cut() -> None:
    message = ("word " * 20) + "lastword"
    title = thread_title(message)
    assert title == title.rstrip()
    assert len(title) <= MAX_THREAD_TITLE_LENGTH


# ---------------------------------------------------------------------------
# validate_user_name (D-16)
# ---------------------------------------------------------------------------


def test_validate_user_name_accepts_letters_digits_spaces_and_hyphens() -> None:
    assert validate_user_name("Jane Doe 2") is None
    assert validate_user_name("sam-2") is None


def test_validate_user_name_rejects_empty_or_whitespace_only() -> None:
    assert validate_user_name("") is not None
    assert validate_user_name("   ") is not None


def test_validate_user_name_rejects_names_over_the_max_length() -> None:
    assert validate_user_name("x" * (MAX_USER_NAME_LENGTH + 1)) is not None
    assert validate_user_name("x" * MAX_USER_NAME_LENGTH) is None


def test_validate_user_name_rejects_disallowed_characters() -> None:
    assert validate_user_name("sam@example.com") is not None
    assert validate_user_name("sam_2") is not None
    assert validate_user_name("sam!") is not None


# ---------------------------------------------------------------------------
# slugify_user_id (D-16)
# ---------------------------------------------------------------------------


def test_slugify_user_id_lowercases_and_joins_with_hyphens() -> None:
    assert slugify_user_id("Jane Doe") == "jane-doe"


def test_slugify_user_id_collapses_repeated_separators() -> None:
    assert slugify_user_id("Jane   Doe") == "jane-doe"
    assert slugify_user_id("jane--doe") == "jane-doe"


def test_slugify_user_id_strips_leading_and_trailing_separators() -> None:
    assert slugify_user_id("  Sam  ") == "sam"


def test_slugify_user_id_keeps_digits() -> None:
    assert slugify_user_id("Sam 2") == "sam-2"


# ---------------------------------------------------------------------------
# order_users: alphabetical, case-insensitive
# ---------------------------------------------------------------------------


def test_order_users_sorts_alphabetically_case_insensitively() -> None:
    assert order_users(["sam", "Alex", "bob"]) == ["Alex", "bob", "sam"]


def test_order_users_on_an_empty_list() -> None:
    assert order_users([]) == []
