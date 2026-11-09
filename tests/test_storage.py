"""Tests for :mod:`job_hunt_agent.storage`.

Each test uses its own temp SQLite file (unique path -> unique
``get_connection`` cache entry, no cross-test interference despite the
module-level ``lru_cache``).

Related: FR-09 AC1, FR-13 AC1, FR-14 AC1, FR-15 AC1, spec §8, D-5, D-6
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from job_hunt_agent import storage
from job_hunt_agent.models import Profile, TrackerEntry


def _db_path(tmp_path: Path, name: str = "test.sqlite") -> str:
    return str(tmp_path / name)


def test_get_connection_is_cached_per_path(tmp_path: Path) -> None:
    """The same path returns the same connection object (D-5)."""
    path = _db_path(tmp_path)
    conn1 = storage.get_connection(path)
    conn2 = storage.get_connection(path)
    assert conn1 is conn2


def test_get_connection_creates_tables(tmp_path: Path) -> None:
    """``profiles`` and `tracker` exist immediately after connecting."""
    conn = storage.get_connection(_db_path(tmp_path))
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert {"profiles", "tracker"} <= tables


def test_profile_round_trip(tmp_path: Path) -> None:
    """A saved profile loads back with the same values (FR-14 AC1)."""
    conn = storage.get_connection(_db_path(tmp_path))
    profile = Profile(
        skills=["Python", "Java"],
        seniority="senior",
        location="Hamburg",
        radius_km=25,
        remote_preference="hybrid",
        german_level="basic",
        english_level="native",
    )
    storage.save_profile(conn, "alex", profile)
    loaded = storage.load_profile(conn, "alex")
    assert loaded == profile


def test_load_profile_returns_none_when_missing(tmp_path: Path) -> None:
    """No stored profile yet -> ``None``, not an exception."""
    conn = storage.get_connection(_db_path(tmp_path))
    assert storage.load_profile(conn, "nobody") is None


def test_save_profile_upserts(tmp_path: Path) -> None:
    """Saving a second time for the same user replaces the profile, no duplicate row."""
    conn = storage.get_connection(_db_path(tmp_path))
    profile_v1 = Profile(
        skills=["Python"],
        seniority="mid",
        location="Berlin",
        radius_km=10,
        remote_preference="onsite",
        german_level="none",
        english_level="fluent",
    )
    profile_v2 = Profile(
        skills=["Python", "Go"],
        seniority="senior",
        location="Hamburg",
        radius_km=25,
        remote_preference="remote",
        german_level="basic",
        english_level="native",
    )
    storage.save_profile(conn, "alex", profile_v1)
    storage.save_profile(conn, "alex", profile_v2)
    assert storage.load_profile(conn, "alex") == profile_v2
    count = conn.execute("SELECT COUNT(*) FROM profiles WHERE user_id = 'alex'").fetchone()[0]
    assert count == 1


def test_profiles_are_independent_per_user(tmp_path: Path) -> None:
    """Two users' profiles do not overwrite each other."""
    conn = storage.get_connection(_db_path(tmp_path))
    alex = Profile(
        skills=["Python"],
        seniority="senior",
        location="Hamburg",
        radius_km=25,
        remote_preference="hybrid",
        german_level="basic",
        english_level="native",
    )
    sam = Profile(
        skills=["Java"],
        seniority="mid",
        location="Berlin",
        radius_km=15,
        remote_preference="onsite",
        german_level="fluent",
        english_level="fluent",
    )
    storage.save_profile(conn, "alex", alex)
    storage.save_profile(conn, "sam", sam)
    assert storage.load_profile(conn, "alex") == alex
    assert storage.load_profile(conn, "sam") == sam


def _entry(**overrides: object) -> TrackerEntry:
    now = datetime(2026, 11, 6, 12, 0, 0)
    defaults: dict[str, object] = {
        "user_id": "alex",
        "referenznummer": "19522-0068291613-S",
        "title": "Python-Entwickler",
        "employer": "Beispiel AG",
        "url": "https://example.invalid/19522-0068291613-S",
        "status": "saved",
        "follow_up_date": None,
        "note": None,
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    return TrackerEntry.model_validate(defaults)


def test_save_tracker_entry_round_trips(tmp_path: Path) -> None:
    """A saved tracker entry is returned as stored (FR-09 AC1)."""
    conn = storage.get_connection(_db_path(tmp_path))
    stored = storage.save_tracker_entry(conn, _entry())
    assert stored.status == "saved"
    assert storage.get_tracker_entry(conn, "alex", "19522-0068291613-S") == stored


def test_save_tracker_entry_is_idempotent_by_user_and_referenznummer(tmp_path: Path) -> None:
    """A second save for the same (user, referenznummer) updates, not duplicates (FR-09 AC1)."""
    conn = storage.get_connection(_db_path(tmp_path))
    storage.save_tracker_entry(conn, _entry(status="saved"))
    storage.save_tracker_entry(
        conn,
        _entry(status="applied", updated_at=datetime(2026, 11, 7, 9, 0, 0)),
    )
    entries = storage.list_tracker_entries(conn, "alex")
    assert len(entries) == 1
    assert entries[0].status == "applied"


def test_save_tracker_entry_preserves_original_created_at(tmp_path: Path) -> None:
    """``created_at`` is never overwritten by a later upsert."""
    conn = storage.get_connection(_db_path(tmp_path))
    first_created = datetime(2026, 11, 1, 8, 0, 0)
    storage.save_tracker_entry(conn, _entry(created_at=first_created, updated_at=first_created))
    second = storage.save_tracker_entry(
        conn,
        _entry(
            status="applied",
            created_at=datetime(2026, 11, 7, 8, 0, 0),  # a bug would use this instead
            updated_at=datetime(2026, 11, 7, 8, 0, 0),
        ),
    )
    assert second.created_at == first_created


def test_tracker_entries_are_independent_per_user(tmp_path: Path) -> None:
    """The same referenznummer for two users creates two independent rows."""
    conn = storage.get_connection(_db_path(tmp_path))
    storage.save_tracker_entry(conn, _entry(user_id="alex", status="saved"))
    storage.save_tracker_entry(conn, _entry(user_id="sam", status="rejected"))
    assert storage.get_tracker_entry(conn, "alex", "19522-0068291613-S").status == "saved"  # type: ignore[union-attr]
    assert storage.get_tracker_entry(conn, "sam", "19522-0068291613-S").status == "rejected"  # type: ignore[union-attr]


def test_list_tracker_entries_orders_by_most_recently_updated(tmp_path: Path) -> None:
    """Entries come back most-recently-updated first."""
    conn = storage.get_connection(_db_path(tmp_path))
    storage.save_tracker_entry(
        conn,
        _entry(
            referenznummer="A-1-S",
            created_at=datetime(2026, 11, 1),
            updated_at=datetime(2026, 11, 1),
        ),
    )
    storage.save_tracker_entry(
        conn,
        _entry(
            referenznummer="B-2-S",
            created_at=datetime(2026, 11, 2),
            updated_at=datetime(2026, 11, 5),
        ),
    )
    entries = storage.list_tracker_entries(conn, "alex")
    assert [e.referenznummer for e in entries] == ["B-2-S", "A-1-S"]


def test_get_tracker_entry_returns_none_when_missing(tmp_path: Path) -> None:
    conn = storage.get_connection(_db_path(tmp_path))
    assert storage.get_tracker_entry(conn, "alex", "does-not-exist-S") is None


def test_delete_tracker_entry_removes_the_row(tmp_path: Path) -> None:
    """FR-11 AC2: a deleted entry is gone from the tracker."""
    conn = storage.get_connection(_db_path(tmp_path))
    storage.save_tracker_entry(conn, _entry())
    deleted = storage.delete_tracker_entry(conn, "alex", "19522-0068291613-S")
    assert deleted is True
    assert storage.get_tracker_entry(conn, "alex", "19522-0068291613-S") is None


def test_delete_tracker_entry_returns_false_when_missing(tmp_path: Path) -> None:
    conn = storage.get_connection(_db_path(tmp_path))
    assert storage.delete_tracker_entry(conn, "alex", "does-not-exist-S") is False


def test_delete_tracker_entry_only_removes_the_given_user(tmp_path: Path) -> None:
    """Deleting alex's entry never touches sam's row for the same referenznummer."""
    conn = storage.get_connection(_db_path(tmp_path))
    storage.save_tracker_entry(conn, _entry(user_id="alex"))
    storage.save_tracker_entry(conn, _entry(user_id="sam"))
    storage.delete_tracker_entry(conn, "alex", "19522-0068291613-S")
    assert storage.get_tracker_entry(conn, "alex", "19522-0068291613-S") is None
    assert storage.get_tracker_entry(conn, "sam", "19522-0068291613-S") is not None


def test_checkpointer_persists_a_thread_across_get_connection_calls(tmp_path: Path) -> None:
    """The checkpointer on the shared connection actually saves a checkpoint (FR-13 AC1)."""
    path = _db_path(tmp_path)
    conn = storage.get_connection(path)
    checkpointer = storage.get_checkpointer(conn)
    cfg = {"configurable": {"thread_id": "t1", "checkpoint_ns": ""}}
    checkpoint = {
        "v": 1,
        "id": "c1",
        "ts": "2026-11-06T00:00:00+00:00",
        "channel_values": {},
        "channel_versions": {},
        "versions_seen": {},
    }
    checkpointer.put(cfg, checkpoint, {"source": "input", "step": 0, "parents": {}}, {})
    loaded = checkpointer.get(cfg)
    assert loaded is not None
    assert loaded["id"] == "c1"


def test_store_put_and_get_round_trips(tmp_path: Path) -> None:
    """The memory store on the shared connection saves and reads items (FR-15 AC1, D-6)."""
    conn = storage.get_connection(_db_path(tmp_path))
    store = storage.get_store(conn)
    namespace = ("memories", "alex")
    store.put(namespace, "pref1", {"kind": "preference", "value": "remote only"})
    item = store.get(namespace, "pref1")
    assert item is not None
    assert item.value == {"kind": "preference", "value": "remote only"}


def test_store_and_checkpointer_share_one_connection_without_conflict(tmp_path: Path) -> None:
    """Both subsystems work together on the one shared connection (D-5, D-6)."""
    conn = storage.get_connection(_db_path(tmp_path))
    checkpointer = storage.get_checkpointer(conn)
    store = storage.get_store(conn)
    store.put(("memories", "alex"), "pref1", {"kind": "preference", "value": "hybrid only"})
    storage.save_profile(
        conn,
        "alex",
        Profile(
            skills=["Python"],
            seniority="senior",
            location="Hamburg",
            radius_km=25,
            remote_preference="hybrid",
            german_level="basic",
            english_level="native",
        ),
    )
    assert checkpointer is not None
    assert store.get(("memories", "alex"), "pref1") is not None
    assert storage.load_profile(conn, "alex") is not None
