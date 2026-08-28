"""SQLite storage for MONGDEE AI Booth OS.

Each call opens a short-lived connection — write volume from a single booth
is low (one row per recognized product / health transition / heartbeat), so
this keeps the module trivially thread-safe without a shared connection.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "mongdee.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    booth_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    camera_id TEXT,
    product_key TEXT NOT NULL,
    product_name TEXT NOT NULL,
    confidence REAL,
    question TEXT,
    answer TEXT
);

CREATE TABLE IF NOT EXISTS health_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    booth_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    camera_id TEXT,
    component TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT
);

CREATE TABLE IF NOT EXISTS readiness_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    booth_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    overall_status TEXT NOT NULL,
    detail_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS heartbeats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    booth_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    status TEXT NOT NULL,
    active_cameras INTEGER
);

CREATE TABLE IF NOT EXISTS product_hold_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    booth_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    camera_id TEXT NOT NULL,
    product_key TEXT NOT NULL,
    product_name TEXT NOT NULL,
    holder_track_id INTEGER NOT NULL,
    hold_start_ts REAL NOT NULL,
    hold_end_ts REAL NOT NULL,
    duration_sec REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS presence_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    booth_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    camera_id TEXT NOT NULL,
    track_id INTEGER NOT NULL,
    start_ts REAL NOT NULL,
    end_ts REAL NOT NULL,
    duration_sec REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_ts REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS booths (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    event_id TEXT,
    created_ts REAL NOT NULL,
    FOREIGN KEY (event_id) REFERENCES events(id)
);
"""


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)


def _connect(db_path: Path):
    return sqlite3.connect(db_path, timeout=5)


def log_interaction(db_path, booth_id, event_id, camera_id, product_key,
                     product_name, confidence, question=None, answer=None):
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO interactions "
            "(ts, booth_id, event_id, camera_id, product_key, product_name, "
            "confidence, question, answer) VALUES (?,?,?,?,?,?,?,?,?)",
            (time.time(), booth_id, event_id, camera_id, product_key,
             product_name, confidence, question, answer),
        )


def log_health_event(db_path, booth_id, event_id, camera_id, component, status, message=None):
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO health_events "
            "(ts, booth_id, event_id, camera_id, component, status, message) "
            "VALUES (?,?,?,?,?,?,?)",
            (time.time(), booth_id, event_id, camera_id, component, status, message),
        )


def log_readiness_check(db_path, booth_id, event_id, overall_status, detail_json):
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO readiness_checks "
            "(ts, booth_id, event_id, overall_status, detail_json) VALUES (?,?,?,?,?)",
            (time.time(), booth_id, event_id, overall_status, detail_json),
        )


def log_heartbeat(db_path, booth_id, event_id, status, active_cameras):
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO heartbeats (ts, booth_id, event_id, status, active_cameras) "
            "VALUES (?,?,?,?,?)",
            (time.time(), booth_id, event_id, status, active_cameras),
        )


def log_product_hold_event(db_path, booth_id, event_id, camera_id, product_key, product_name,
                            holder_track_id, hold_start_ts, hold_end_ts, duration_sec):
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO product_hold_events "
            "(ts, booth_id, event_id, camera_id, product_key, product_name, "
            "holder_track_id, hold_start_ts, hold_end_ts, duration_sec) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (time.time(), booth_id, event_id, camera_id, product_key, product_name,
             holder_track_id, hold_start_ts, hold_end_ts, duration_sec),
        )


def log_presence_session(db_path, booth_id, event_id, camera_id, track_id,
                          start_ts, end_ts, duration_sec):
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO presence_sessions "
            "(ts, booth_id, event_id, camera_id, track_id, start_ts, end_ts, duration_sec) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (time.time(), booth_id, event_id, camera_id, track_id, start_ts, end_ts, duration_sec),
        )


def _rows_as_dicts(cursor):
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def query_interactions(db_path, event_id=None, booth_id=None, limit=200):
    sql = "SELECT * FROM interactions WHERE 1=1"
    params = []
    if event_id:
        sql += " AND event_id = ?"
        params.append(event_id)
    if booth_id:
        sql += " AND booth_id = ?"
        params.append(booth_id)
    sql += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    with _connect(db_path) as conn:
        return _rows_as_dicts(conn.execute(sql, params))


def query_top_products(db_path, event_id=None, booth_id=None, limit=10):
    sql = (
        "SELECT product_name, COUNT(*) as views "
        "FROM interactions WHERE 1=1"
    )
    params = []
    if event_id:
        sql += " AND event_id = ?"
        params.append(event_id)
    if booth_id:
        sql += " AND booth_id = ?"
        params.append(booth_id)
    sql += " GROUP BY product_name ORDER BY views DESC LIMIT ?"
    params.append(limit)
    with _connect(db_path) as conn:
        return _rows_as_dicts(conn.execute(sql, params))


def query_product_movers(db_path, event_id=None, booth_id=None, limit=10):
    """Which products have been picked up/moved by the most (ephemeral)
    people, ranked — each product_hold_events row is one person's one
    continuous hold, so COUNT(*) is the mover count."""
    sql = (
        "SELECT product_name, COUNT(*) as mover_count, SUM(duration_sec) as total_interest_sec "
        "FROM product_hold_events WHERE 1=1"
    )
    params = []
    if event_id:
        sql += " AND event_id = ?"
        params.append(event_id)
    if booth_id:
        sql += " AND booth_id = ?"
        params.append(booth_id)
    sql += " GROUP BY product_name ORDER BY mover_count DESC LIMIT ?"
    params.append(limit)
    with _connect(db_path) as conn:
        return _rows_as_dicts(conn.execute(sql, params))


def query_product_hold_events(db_path, event_id=None, booth_id=None, limit=200):
    """Raw history of every pick-up/hold, newest first — the underlying
    events behind query_product_movers()'s aggregate counts, kept queryable
    on their own for later analysis (not just the summarized totals)."""
    sql = "SELECT * FROM product_hold_events WHERE 1=1"
    params = []
    if event_id:
        sql += " AND event_id = ?"
        params.append(event_id)
    if booth_id:
        sql += " AND booth_id = ?"
        params.append(booth_id)
    sql += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    with _connect(db_path) as conn:
        return _rows_as_dicts(conn.execute(sql, params))


def query_presence_sessions(db_path, event_id=None, booth_id=None, limit=200):
    sql = "SELECT * FROM presence_sessions WHERE 1=1"
    params = []
    if event_id:
        sql += " AND event_id = ?"
        params.append(event_id)
    if booth_id:
        sql += " AND booth_id = ?"
        params.append(booth_id)
    sql += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    with _connect(db_path) as conn:
        return _rows_as_dicts(conn.execute(sql, params))


def query_presence_stats(db_path, event_id=None, booth_id=None):
    sessions = query_presence_sessions(db_path, event_id, booth_id, limit=100000)
    durations = [row["duration_sec"] for row in sessions]
    if not durations:
        return {"count": 0, "avg_sec": 0.0, "min_sec": 0.0, "max_sec": 0.0}
    return {
        "count": len(durations),
        "avg_sec": sum(durations) / len(durations),
        "min_sec": min(durations),
        "max_sec": max(durations),
    }


def query_health_events(db_path, event_id=None, booth_id=None, limit=100):
    sql = "SELECT * FROM health_events WHERE 1=1"
    params = []
    if event_id:
        sql += " AND event_id = ?"
        params.append(event_id)
    if booth_id:
        sql += " AND booth_id = ?"
        params.append(booth_id)
    sql += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    with _connect(db_path) as conn:
        return _rows_as_dicts(conn.execute(sql, params))


SCOPED_TABLES = ("interactions", "health_events", "readiness_checks", "heartbeats",
                 "product_hold_events", "presence_sessions")


def delete_scope_data(db_path, booth_id=None, event_id=None):
    """Wipe every logged row matching booth_id and/or event_id — used by the
    booth settings page's "reset this booth's data" action, and by the
    Dashboard's per Booth ID / per Event ID cleanup. Destructive and
    irreversible; the caller is responsible for confirming with the user
    first. Requires at least one of booth_id/event_id (refuses to wipe
    everything by accident)."""
    if not booth_id and not event_id:
        raise ValueError("ต้องระบุ booth_id หรือ event_id อย่างน้อยหนึ่งอย่าง")
    where = []
    params = []
    if booth_id:
        where.append("booth_id = ?")
        params.append(booth_id)
    if event_id:
        where.append("event_id = ?")
        params.append(event_id)
    clause = " AND ".join(where)
    with _connect(db_path) as conn:
        for table in SCOPED_TABLES:
            conn.execute(f"DELETE FROM {table} WHERE {clause}", params)


def query_readiness_checks(db_path, event_id=None, booth_id=None, limit=100):
    sql = "SELECT * FROM readiness_checks WHERE 1=1"
    params = []
    if event_id:
        sql += " AND event_id = ?"
        params.append(event_id)
    if booth_id:
        sql += " AND booth_id = ?"
        params.append(booth_id)
    sql += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    with _connect(db_path) as conn:
        return _rows_as_dicts(conn.execute(sql, params))


def query_heartbeats(db_path, event_id=None, booth_id=None, limit=500):
    sql = "SELECT * FROM heartbeats WHERE 1=1"
    params = []
    if event_id:
        sql += " AND event_id = ?"
        params.append(event_id)
    if booth_id:
        sql += " AND booth_id = ?"
        params.append(booth_id)
    sql += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    with _connect(db_path) as conn:
        return _rows_as_dicts(conn.execute(sql, params))


def query_distinct(db_path, table, column):
    with _connect(db_path) as conn:
        try:
            rows = conn.execute(f"SELECT DISTINCT {column} FROM {table} ORDER BY {column}")
            return [r[0] for r in rows.fetchall()]
        except sqlite3.OperationalError:
            return []


def query_known_ids(db_path) -> dict:
    """Every booth_id / event_id that appears anywhere in the database — not
    just in interactions/health_events — so the Dashboard's filters and
    cleanup tools see booths/events that only ever produced, say, hold
    events or heartbeats."""
    booth_ids: set[str] = set()
    event_ids: set[str] = set()
    for table in SCOPED_TABLES:
        booth_ids.update(v for v in query_distinct(db_path, table, "booth_id") if v)
        event_ids.update(v for v in query_distinct(db_path, table, "event_id") if v)
    return {"booth_ids": sorted(booth_ids), "event_ids": sorted(event_ids)}


UNSET = object()  # distinguishes "leave event_id alone" from "set it to NULL" in update_booth()


def create_event(db_path, event_id: str, name: str) -> None:
    with _connect(db_path) as conn:
        conn.execute("INSERT INTO events (id, name, created_ts) VALUES (?,?,?)",
                     (event_id, name, time.time()))


def ensure_event(db_path, event_id: str, name: str | None = None) -> None:
    """create_event, but a no-op if the id is already registered — for
    startup bootstrapping, where the same --event-id may be reused across
    multiple CLI launches (e.g. simulating several booths at one event)."""
    try:
        create_event(db_path, event_id, name or event_id)
    except sqlite3.IntegrityError:
        pass


def rename_event(db_path, event_id: str, name: str) -> None:
    with _connect(db_path) as conn:
        conn.execute("UPDATE events SET name = ? WHERE id = ?", (name, event_id))


def delete_event(db_path, event_id: str) -> None:
    """Deleting an Event never deletes its member Booths — it's just a
    grouping label, so membership is dropped (booths become unassigned)
    before the event's own logged data is purged and its registry row
    removed."""
    with _connect(db_path) as conn:
        conn.execute("UPDATE booths SET event_id = NULL WHERE event_id = ?", (event_id,))
    delete_scope_data(db_path, event_id=event_id)
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM events WHERE id = ?", (event_id,))


def list_events(db_path) -> list[dict]:
    sql = """
        SELECT events.id, events.name, events.created_ts,
               (SELECT COUNT(*) FROM booths WHERE booths.event_id = events.id) AS booth_count
        FROM events ORDER BY events.name
    """
    with _connect(db_path) as conn:
        return _rows_as_dicts(conn.execute(sql))


def create_booth(db_path, booth_id: str, name: str, event_id: str | None = None) -> None:
    with _connect(db_path) as conn:
        conn.execute("INSERT INTO booths (id, name, event_id, created_ts) VALUES (?,?,?,?)",
                     (booth_id, name, event_id, time.time()))


def update_booth(db_path, booth_id: str, name: str | None = None, event_id=UNSET) -> None:
    sets = []
    params = []
    if name is not None:
        sets.append("name = ?")
        params.append(name)
    if event_id is not UNSET:
        sets.append("event_id = ?")
        params.append(event_id)  # None here means "unassign", written as NULL
    if not sets:
        return
    params.append(booth_id)
    with _connect(db_path) as conn:
        conn.execute(f"UPDATE booths SET {', '.join(sets)} WHERE id = ?", params)


def delete_booth(db_path, booth_id: str) -> None:
    delete_scope_data(db_path, booth_id=booth_id)
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM booths WHERE id = ?", (booth_id,))


def list_booths(db_path) -> list[dict]:
    sql = """
        SELECT booths.id, booths.name, booths.event_id, events.name AS event_name,
               booths.created_ts
        FROM booths LEFT JOIN events ON events.id = booths.event_id
        ORDER BY booths.name
    """
    with _connect(db_path) as conn:
        return _rows_as_dicts(conn.execute(sql))


def get_booth(db_path, booth_id: str) -> dict | None:
    with _connect(db_path) as conn:
        rows = _rows_as_dicts(conn.execute(
            "SELECT booths.id, booths.name, booths.event_id, events.name AS event_name "
            "FROM booths LEFT JOIN events ON events.id = booths.event_id WHERE booths.id = ?",
            (booth_id,),
        ))
    return rows[0] if rows else None


def count_booths(db_path) -> int:
    with _connect(db_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM booths").fetchone()[0]


def query_summary(db_path, event_id=None, booth_id=None):
    interactions = query_interactions(db_path, event_id, booth_id, limit=100000)
    health = query_health_events(db_path, event_id, booth_id, limit=100000)
    booths = {row["booth_id"] for row in interactions} | {row["booth_id"] for row in health}
    open_alerts = [h for h in health if h["status"] == "error"]
    return {
        "total_interactions": len(interactions),
        "unique_products": len({row["product_name"] for row in interactions}),
        "active_booths": len(booths),
        "open_alerts": len(open_alerts),
    }
