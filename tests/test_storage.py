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


def test_list_memories_returns_kind_value_and_created_at(tmp_path: Path) -> None:
    """FR-15 AC3: each item carries its key, kind, value and created date."""
    conn = storage.get_connection(_db_path(tmp_path))
    store = storage.get_store(conn)
    store.put(("memories", "alex"), "k1", {"kind": "preference", "value": "remote only"})
    memories = storage.list_memories(conn, "alex")
    assert len(memories) == 1
    assert memories[0]["key"] == "k1"
    assert memories[0]["kind"] == "preference"
    assert memories[0]["value"] == "remote only"
    assert memories[0]["created_at"] is not None


def test_list_memories_orders_most_recently_saved_first(tmp_path: Path) -> None:
    """Newest item first, mirroring list_tracker_entries' ordering."""
    conn = storage.get_connection(_db_path(tmp_path))
    store = storage.get_store(conn)
    store.put(("memories", "alex"), "k1", {"kind": "preference", "value": "first"})
    store.put(("memories", "alex"), "k2", {"kind": "preference", "value": "second"})
    # SqliteStore's own created_at column has one-second resolution, so two
    # puts in the same test can land in the same second; set them apart
    # explicitly so the ordering assertion is deterministic, not timing-dependent.
    conn.execute(
        "UPDATE store SET created_at = ? WHERE prefix = 'memories.alex' AND key = 'k1'",
        ("2026-11-01 00:00:00",),
    )
    conn.execute(
        "UPDATE store SET created_at = ? WHERE prefix = 'memories.alex' AND key = 'k2'",
        ("2026-11-02 00:00:00",),
    )
    memories = storage.list_memories(conn, "alex")
    assert [m["value"] for m in memories] == ["second", "first"]


def test_list_memories_returns_empty_list_when_none_stored(tmp_path: Path) -> None:
    conn = storage.get_connection(_db_path(tmp_path))
    assert storage.list_memories(conn, "alex") == []


def test_list_memories_isolates_per_user(tmp_path: Path) -> None:
    """Two users' memories do not leak into each other's list (D-6 namespacing)."""
    conn = storage.get_connection(_db_path(tmp_path))
    store = storage.get_store(conn)
    store.put(("memories", "alex"), "k1", {"kind": "preference", "value": "alex's pref"})
    store.put(("memories", "sam"), "k2", {"kind": "preference", "value": "sam's pref"})
    assert [m["value"] for m in storage.list_memories(conn, "alex")] == ["alex's pref"]
    assert [m["value"] for m in storage.list_memories(conn, "sam")] == ["sam's pref"]


def test_delete_memory_removes_the_item(tmp_path: Path) -> None:
    """FR-15 AC3: a deleted memory is gone from the store."""
    conn = storage.get_connection(_db_path(tmp_path))
    store = storage.get_store(conn)
    store.put(("memories", "alex"), "k1", {"kind": "preference", "value": "remote only"})
    storage.delete_memory(conn, "alex", "k1")
    assert storage.list_memories(conn, "alex") == []


def test_delete_memory_only_removes_the_given_user(tmp_path: Path) -> None:
    """Deleting alex's item never touches sam's item under the same key."""
    conn = storage.get_connection(_db_path(tmp_path))
    store = storage.get_store(conn)
    store.put(("memories", "alex"), "k1", {"kind": "preference", "value": "alex's pref"})
    store.put(("memories", "sam"), "k1", {"kind": "preference", "value": "sam's pref"})
    storage.delete_memory(conn, "alex", "k1")
    assert storage.list_memories(conn, "alex") == []
    assert len(storage.list_memories(conn, "sam")) == 1


def test_delete_memory_on_a_missing_key_does_not_raise(tmp_path: Path) -> None:
    conn = storage.get_connection(_db_path(tmp_path))
    storage.delete_memory(conn, "alex", "does-not-exist")


# ---------------------------------------------------------------------------
# list_users (D-16): every user id with a stored profile
# ---------------------------------------------------------------------------


def test_list_users_returns_every_user_with_a_profile(tmp_path: Path) -> None:
    conn = storage.get_connection(_db_path(tmp_path))
    storage.save_profile(
        conn,
        "sam",
        Profile(
            skills=["Java"],
            seniority="mid",
            location="Berlin",
            radius_km=15,
            remote_preference="onsite",
            german_level="fluent",
            english_level="fluent",
        ),
    )
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
    assert storage.list_users(conn) == ["alex", "sam"]


def test_list_users_is_empty_when_no_profile_is_stored(tmp_path: Path) -> None:
    conn = storage.get_connection(_db_path(tmp_path))
    assert storage.list_users(conn) == []


# ---------------------------------------------------------------------------
# threads (FR-13 AC2, D-15): register, touch, list, isolate, delete
# ---------------------------------------------------------------------------


def test_touch_thread_registers_a_new_thread_with_its_title(tmp_path: Path) -> None:
    conn = storage.get_connection(_db_path(tmp_path))
    now = datetime(2026, 11, 9, 9, 0, 0)
    storage.touch_thread(conn, "alex", "t1", "Python jobs in Hamburg", now)
    threads = storage.list_threads(conn, "alex")
    assert len(threads) == 1
    assert threads[0].thread_id == "t1"
    assert threads[0].title == "Python jobs in Hamburg"
    assert threads[0].created_at == now
    assert threads[0].updated_at == now


def test_touch_thread_on_an_existing_thread_only_moves_updated_at(tmp_path: Path) -> None:
    """A later turn's title argument is ignored - D-15's "title = first user message"."""
    conn = storage.get_connection(_db_path(tmp_path))
    first = datetime(2026, 11, 9, 9, 0, 0)
    second = datetime(2026, 11, 9, 9, 30, 0)
    storage.touch_thread(conn, "alex", "t1", "Python jobs in Hamburg", first)
    storage.touch_thread(conn, "alex", "t1", "a later, different message", second)
    threads = storage.list_threads(conn, "alex")
    assert len(threads) == 1
    assert threads[0].title == "Python jobs in Hamburg"
    assert threads[0].created_at == first
    assert threads[0].updated_at == second


def test_list_threads_orders_most_recently_updated_first(tmp_path: Path) -> None:
    conn = storage.get_connection(_db_path(tmp_path))
    storage.touch_thread(conn, "alex", "t1", "first thread", datetime(2026, 11, 1))
    storage.touch_thread(conn, "alex", "t2", "second thread", datetime(2026, 11, 5))
    threads = storage.list_threads(conn, "alex")
    assert [t.thread_id for t in threads] == ["t2", "t1"]


def test_threads_are_independent_per_user(tmp_path: Path) -> None:
    conn = storage.get_connection(_db_path(tmp_path))
    storage.touch_thread(conn, "alex", "t1", "alex's thread", datetime(2026, 11, 1))
    storage.touch_thread(conn, "sam", "t1", "sam's thread", datetime(2026, 11, 1))
    assert [t.title for t in storage.list_threads(conn, "alex")] == ["alex's thread"]
    assert [t.title for t in storage.list_threads(conn, "sam")] == ["sam's thread"]


def test_delete_thread_record_removes_the_row(tmp_path: Path) -> None:
    conn = storage.get_connection(_db_path(tmp_path))
    storage.touch_thread(conn, "alex", "t1", "a thread", datetime(2026, 11, 1))
    deleted = storage.delete_thread_record(conn, "alex", "t1")
    assert deleted is True
    assert storage.list_threads(conn, "alex") == []


def test_delete_thread_record_returns_false_when_missing(tmp_path: Path) -> None:
    conn = storage.get_connection(_db_path(tmp_path))
    assert storage.delete_thread_record(conn, "alex", "does-not-exist") is False


def test_delete_thread_record_only_removes_the_given_user(tmp_path: Path) -> None:
    conn = storage.get_connection(_db_path(tmp_path))
    storage.touch_thread(conn, "alex", "t1", "alex's thread", datetime(2026, 11, 1))
    storage.touch_thread(conn, "sam", "t1", "sam's thread", datetime(2026, 11, 1))
    storage.delete_thread_record(conn, "alex", "t1")
    assert storage.list_threads(conn, "alex") == []
    assert len(storage.list_threads(conn, "sam")) == 1
