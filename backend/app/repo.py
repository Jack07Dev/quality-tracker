"""All SQL lives here so the HTTP layer stays thin."""
import sqlite3
from datetime import date
from typing import Optional

from .db import SEVERITIES, STATUSES

SORT_EXPRESSIONS = {
    "inspection_date": "inspection_date",
    "created_at": "created_at",
    "machine_id": "machine_id COLLATE NOCASE",
    "status": "status",
    # asc = most critical first
    "severity": "CASE severity WHEN 'Critical' THEN 0 WHEN 'Major' THEN 1 ELSE 2 END",
}


class AlreadyResolved(Exception):
    pass


def get(conn: sqlite3.Connection, inspection_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM inspections WHERE id = ?", (inspection_id,)).fetchone()
    return dict(row) if row else None


def _by_ref(conn, ref):
    row = conn.execute("SELECT * FROM inspections WHERE external_ref = ?", (ref,)).fetchone()
    return dict(row) if row else None


def create(conn: sqlite3.Connection, data: dict, external_ref: Optional[str] = None) -> tuple[dict, bool]:
    """Insert an inspection. Returns (row, created). Re-sending the same external_ref is a no-op."""
    if external_ref and (existing := _by_ref(conn, external_ref)):
        return existing, False
    try:
        cur = conn.execute(
            """INSERT INTO inspections
               (inspection_date, machine_id, defect_type, severity, remarks, external_ref)
               VALUES (:inspection_date, :machine_id, :defect_type, :severity, :remarks, :external_ref)""",
            {**data, "inspection_date": data["inspection_date"].isoformat(), "external_ref": external_ref},
        )
        conn.commit()
    except sqlite3.IntegrityError:  # lost a race on external_ref
        conn.rollback()
        return _by_ref(conn, external_ref), False
    return get(conn, cur.lastrowid), True


def list_all(conn, *, severity=None, status=None, date_from: Optional[date] = None,
             date_to: Optional[date] = None, sort="inspection_date", order="desc") -> list[dict]:
    where, params = [], []
    if severity:
        where.append("severity = ?"); params.append(severity)
    if status:
        where.append("status = ?"); params.append(status)
    if date_from:
        where.append("inspection_date >= ?"); params.append(date_from.isoformat())
    if date_to:
        where.append("inspection_date <= ?"); params.append(date_to.isoformat())
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    direction = "ASC" if order == "asc" else "DESC"
    # sort/order are validated against Literals upstream; the expression comes from a fixed map.
    sql = f"SELECT * FROM inspections {clause} ORDER BY {SORT_EXPRESSIONS[sort]} {direction}, id {direction}"
    return [dict(r) for r in conn.execute(sql, params)]


def resolve(conn, inspection_id: int, note: str) -> Optional[dict]:
    """Returns the updated row, None if not found. Raises AlreadyResolved."""
    if get(conn, inspection_id) is None:
        return None
    cur = conn.execute(
        """UPDATE inspections
           SET status = 'Resolved', resolution_note = ?, resolved_at = strftime('%Y-%m-%dT%H:%M:%SZ','now')
           WHERE id = ? AND status = 'Open'""",
        (note, inspection_id),
    )
    conn.commit()
    if cur.rowcount == 0:
        raise AlreadyResolved()
    return get(conn, inspection_id)


def summary(conn) -> dict:
    by_sev = {s: {"open": 0, "resolved": 0} for s in SEVERITIES}
    for r in conn.execute("SELECT severity, status, COUNT(*) AS n FROM inspections GROUP BY severity, status"):
        by_sev[r["severity"]][r["status"].lower()] = r["n"]
    totals = {st.lower(): sum(v[st.lower()] for v in by_sev.values()) for st in STATUSES}
    return {"by_severity": by_sev, "totals": totals}
