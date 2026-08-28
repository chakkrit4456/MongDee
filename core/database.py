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


def query_distinct(db_path, table, column):
    with _connect(db_path) as conn:
        try:
            rows = conn.execute(f"SELECT DISTINCT {column} FROM {table} ORDER BY {column}")
            return [r[0] for r in rows.fetchall()]
        except sqlite3.OperationalError:
            return []


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
