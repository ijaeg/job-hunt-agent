"""SQLite persistence: profiles, tracker, checkpointer and memory store.

One shared SQLite file (``config.DB_PATH``), one shared ``sqlite3.Connection``
(``check_same_thread=False``, D-5) used by this module's own `profiles`/
`tracker` tables *and* handed to :class:`SqliteSaver` (FR-13) and
:class:`SqliteStore` (FR-15, D-6) - all three coexist safely on one
connection the same way the D-5 spike proved for the checkpointer alone.
:func:`get_connection` is cached per path so repeated calls in the same
process reuse the same connection instead of opening a new one each time
(the Streamlit app wraps this in ``st.cache_resource`` for the rerun case;
this module has no Streamlit dependency itself, per the architecture's
downward-only dependency rule, CLAUDE.md).

Tracker writes use ``INSERT ... ON CONFLICT ... DO UPDATE`` so a second
``save_to_tracker`` call for the same ``(user_id, referenznummer)`` updates
the existing row instead of creating a duplicate (FR-09 AC1) and never
touches the original ``created_at``. Every write runs inside the
connection's own transaction (``with conn:``), so a failure leaves no
partial write (spec §8).

Related: FR-09 AC1, FR-13 AC1, FR-14 AC1, FR-15 AC1, spec §5, §8, D-5, D-6
"""

from __future__ import annotations

import json
import sqlite3
from functools import cache
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.sqlite import SqliteStore

from job_hunt_agent.models import Profile, TrackerEntry

_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS profiles (
    user_id TEXT PRIMARY KEY,
    skills TEXT NOT NULL,
    seniority TEXT NOT NULL,
    location TEXT NOT NULL,
    radius_km INTEGER NOT NULL,
    remote_preference TEXT NOT NULL,
    wants_full_time INTEGER NOT NULL,
    wants_permanent INTEGER NOT NULL,
    exclude_temp_agency INTEGER NOT NULL,
    german_level TEXT NOT NULL,
    english_level TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tracker (
    user_id TEXT NOT NULL,
    referenznummer TEXT NOT NULL,
    title TEXT NOT NULL,
    employer TEXT,
    url TEXT,
    status TEXT NOT NULL,
    follow_up_date TEXT,
    note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, referenznummer)
);
"""


@cache
def get_connection(db_path: str = "") -> sqlite3.Connection:
    """One shared connection per path, cached for the life of the process (D-5).

    Args:
        db_path: Path to the SQLite file; defaults to ``config.DB_PATH``.
            Passed explicitly (rather than read from ``config`` here) so
            tests can point at an isolated temp file without needing to
            reload ``config``.

    Returns:
        A connection with ``check_same_thread=False`` (safe: every writer
        in this module uses ``with conn:`` for its own transaction) whose
        `profiles`/`tracker` tables already exist.

    Related: D-5, spec §8
    """
    from job_hunt_agent import config

    path = db_path or config.DB_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None (autocommit): SqliteStore.setup() issues a bare
    # INSERT on the raw connection outside any transaction wrapper, which
    # under the default deferred-transaction mode leaves an implicit
    # transaction open forever - its own later `BEGIN` (in `put`/`get`)
    # then fails with "cannot start a transaction within a transaction".
    # Autocommit is what `SqliteStore.from_conn_string` itself uses; this
    # module's own writes only ever run one statement per `with conn:`
    # block, so autocommit changes nothing for them.
    conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    conn.executescript(_CREATE_TABLES_SQL)
    return conn


def get_checkpointer(conn: sqlite3.Connection) -> SqliteSaver:
    """Short-term memory checkpointer on the shared connection (FR-13 AC1)."""
    return SqliteSaver(conn)


def get_store(conn: sqlite3.Connection) -> SqliteStore:
    """Long-term memory store on the shared connection, namespaced per user (FR-15 AC1, D-6)."""
    store = SqliteStore(conn)
    store.setup()
    return store


def save_profile(conn: sqlite3.Connection, user_id: str, profile: Profile) -> None:
    """Upserts the user's profile (FR-14 AC1)."""
    with conn:
        conn.execute(
            """
            INSERT INTO profiles (
                user_id, skills, seniority, location, radius_km, remote_preference,
                wants_full_time, wants_permanent, exclude_temp_agency, german_level,
                english_level
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                skills = excluded.skills,
                seniority = excluded.seniority,
                location = excluded.location,
                radius_km = excluded.radius_km,
                remote_preference = excluded.remote_preference,
                wants_full_time = excluded.wants_full_time,
                wants_permanent = excluded.wants_permanent,
                exclude_temp_agency = excluded.exclude_temp_agency,
                german_level = excluded.german_level,
                english_level = excluded.english_level
            """,
            (
                user_id,
                json.dumps(profile.skills, ensure_ascii=False),
                profile.seniority,
                profile.location,
                profile.radius_km,
                profile.remote_preference,
                int(profile.wants_full_time),
                int(profile.wants_permanent),
                int(profile.exclude_temp_agency),
                profile.german_level,
                profile.english_level,
            ),
        )


def load_profile(conn: sqlite3.Connection, user_id: str) -> Profile | None:
    """Loads the user's profile, or ``None`` if none is stored yet (FR-14 AC1)."""
    row = conn.execute(
        """
        SELECT skills, seniority, location, radius_km, remote_preference,
               wants_full_time, wants_permanent, exclude_temp_agency, german_level,
               english_level
        FROM profiles WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()
    if row is None:
        return None
    return Profile(
        skills=json.loads(row[0]),
        seniority=row[1],
        location=row[2],
        radius_km=row[3],
        remote_preference=row[4],
        wants_full_time=bool(row[5]),
        wants_permanent=bool(row[6]),
        exclude_temp_agency=bool(row[7]),
        german_level=row[8],
        english_level=row[9],
    )


def save_tracker_entry(conn: sqlite3.Connection, entry: TrackerEntry) -> TrackerEntry:
    """Upserts one tracker entry by ``(user_id, referenznummer)`` (FR-09 AC1).

    A second call for the same key updates the existing row - ``created_at``
    is never overwritten on conflict, so it still reflects the first save.

    Args:
        entry: The entry to save; ``created_at``/``updated_at`` are taken
            as given (the caller decides "now", keeping this function pure
            with respect to the system clock).

    Returns:
        The stored entry, with the original ``created_at`` if this was an
        update.

    Related: FR-09 AC1, spec §8
    """
    with conn:
        conn.execute(
            """
            INSERT INTO tracker (
                user_id, referenznummer, title, employer, url, status,
                follow_up_date, note, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, referenznummer) DO UPDATE SET
                title = excluded.title,
                employer = excluded.employer,
                url = excluded.url,
                status = excluded.status,
                follow_up_date = excluded.follow_up_date,
                note = excluded.note,
                updated_at = excluded.updated_at
            """,
            (
                entry.user_id,
                entry.referenznummer,
                entry.title,
                entry.employer,
                entry.url,
                entry.status,
                entry.follow_up_date.isoformat() if entry.follow_up_date else None,
                entry.note,
                entry.created_at.isoformat(),
                entry.updated_at.isoformat(),
            ),
        )
    stored = get_tracker_entry(conn, entry.user_id, entry.referenznummer)
    assert stored is not None  # noqa: S101 - just wrote it inside this transaction
    return stored


def get_tracker_entry(
    conn: sqlite3.Connection, user_id: str, referenznummer: str
) -> TrackerEntry | None:
    """Reads one tracker entry, or ``None`` if it does not exist."""
    row = conn.execute(
        """
        SELECT user_id, referenznummer, title, employer, url, status,
               follow_up_date, note, created_at, updated_at
        FROM tracker WHERE user_id = ? AND referenznummer = ?
        """,
        (user_id, referenznummer),
    ).fetchone()
    return _tracker_entry_from_row(row) if row else None


def list_tracker_entries(conn: sqlite3.Connection, user_id: str) -> list[TrackerEntry]:
    """Reads all tracker entries for one user, most recently updated first."""
    rows = conn.execute(
        """
        SELECT user_id, referenznummer, title, employer, url, status,
               follow_up_date, note, created_at, updated_at
        FROM tracker WHERE user_id = ? ORDER BY updated_at DESC
        """,
        (user_id,),
    ).fetchall()
    return [_tracker_entry_from_row(row) for row in rows]


def delete_tracker_entry(conn: sqlite3.Connection, user_id: str, referenznummer: str) -> bool:
    """Deletes one tracker entry (FR-11 AC2), a user action and not gated by approval.

    Args:
        user_id: The entry's owner.
        referenznummer: The listing to remove.

    Returns:
        ``True`` if a row was actually deleted, ``False`` if no such entry existed.

    Related: FR-11 AC2, spec §8
    """
    with conn:
        cursor = conn.execute(
            "DELETE FROM tracker WHERE user_id = ? AND referenznummer = ?",
            (user_id, referenznummer),
        )
    return cursor.rowcount > 0


def _tracker_entry_from_row(row: tuple[object, ...]) -> TrackerEntry:
    return TrackerEntry(
        user_id=row[0],  # type: ignore[arg-type]
        referenznummer=row[1],  # type: ignore[arg-type]
        title=row[2],  # type: ignore[arg-type]
        employer=row[3],  # type: ignore[arg-type]
        url=row[4],  # type: ignore[arg-type]
        status=row[5],  # type: ignore[arg-type]
        follow_up_date=row[6],  # type: ignore[arg-type]
        note=row[7],  # type: ignore[arg-type]
        created_at=row[8],  # type: ignore[arg-type]
        updated_at=row[9],  # type: ignore[arg-type]
    )
