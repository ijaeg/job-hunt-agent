"""Tests for ``scripts/build_fixtures.py``'s referenznummer recovery.

Related: D-1, D-10
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_fixtures import recover_referenznummer  # noqa: E402


def test_recover_referenznummer_passes_through_an_uncorrupted_exact_match() -> None:
    known = {"17338-C2DE5FF0CD55000215-S", "13545-DZTBHCDPFNHF7DSR-S"}
    assert recover_referenznummer("17338-c2de5ff0cd55000215-S", known) == (
        "17338-C2DE5FF0CD55000215-S"
    )


def test_recover_referenznummer_returns_none_for_an_uncorrupted_unknown_ref() -> None:
    """A ref never detail-fetched (not in listings.json) has nothing to recover to."""
    known = {"17338-C2DE5FF0CD55000215-S"}
    assert recover_referenznummer("99999-SOMETHING-ELSE-S", known) is None


def test_recover_referenznummer_recovers_the_d1_regression_case() -> None:
    """The exact corruption this bug report is about: 19522-0068291613-S."""
    known = {"19522-0068291613-S", "13545-DZTBHCDPFNHF7DSR-S"}
    assert recover_referenznummer("19522-[TELEFON]-S", known) == "19522-0068291613-S"


def test_recover_referenznummer_recovers_a_partial_corruption() -> None:
    """Only the middle of the digit group was replaced: 13509-000021100c7004-S."""
    known = {"13509-000021100C7004-S"}
    assert recover_referenznummer("13509-[TELEFON]c7004-S", known) == "13509-000021100C7004-S"


def test_recover_referenznummer_returns_none_when_ambiguous() -> None:
    """Two known refs share the same prefix/suffix around the corruption - can't tell which."""
    known = {"19522-0068291613-S", "19522-0099999999-S"}
    assert recover_referenznummer("19522-[TELEFON]-S", known) is None


def test_recover_referenznummer_returns_none_when_no_candidate_matches() -> None:
    known = {"17338-C2DE5FF0CD55000215-S"}
    assert recover_referenznummer("19522-[TELEFON]-S", known) is None
