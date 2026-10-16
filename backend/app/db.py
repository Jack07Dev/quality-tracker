"""SQLite connection handling and schema. Stdlib only, no ORM (see README)."""
import os
import sqlite3
from pathlib import Path

DEFECT_TYPES = ("Weave Defect", "Shade Variation", "Hole/Tear", "Count Deviation", "Other")
SEVERITIES = ("Critical", "Major", "Minor")
STATUSES = ("Open", "Resolved")


def _in(values):
    return ", ".join(f"'{v}'" for v in values)


SCHEMA = f"""
CREATE TABLE IF NOT EXISTS inspections (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    inspection_date TEXT NOT NULL,
    machine_id      TEXT NOT NULL,
    defect_type     TEXT NOT NULL CHECK (defect_type IN ({_in(DEFECT_TYPES)})),
    severity        TEXT NOT NULL CHECK (severity IN ({_in(SEVERITIES)})),
    remarks         TEXT,
    status          TEXT NOT NULL DEFAULT 'Open' CHECK (status IN ({_in(STATUSES)})),
    resolution_note TEXT,
    resolved_at     TEXT,
    external_ref    TEXT UNIQUE,  -- idempotency key: 'client:<uuid>' or 'sap:<notification_id>'
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    CHECK ((status = 'Resolved') = (resolution_note IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_insp_filters ON inspections (status, severity, inspection_date);
"""


def db_path() -> str:
    # Read at call time so tests can point to a temp file.
    return os.getenv("DB_PATH", "data/tracker.db")


def connect() -> sqlite3.Connection:
    # check_same_thread=False: FastAPI resolves dependencies and runs sync
    # endpoints on different worker threads; each request still gets its own connection.
    conn = sqlite3.connect(db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    Path(db_path()).parent.mkdir(parents=True, exist_ok=True)
    conn = connect()
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
