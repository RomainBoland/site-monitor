import os
import sqlite3

DEFAULT_DATABASE_PATH = "site-monitor.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS targets (
    id         INTEGER PRIMARY KEY,
    url        TEXT    NOT NULL UNIQUE,
    created_at TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


def get_database_path() -> str:
    return os.environ.get("DATABASE_PATH", DEFAULT_DATABASE_PATH)


def connect(path: str) -> sqlite3.Connection:
    # FastAPI may open, use and close a connection on different threads of its pool.
    # Safe here because each connection belongs to a single request and is never shared.
    conn = sqlite3.connect(path, check_same_thread=False)
    # Rows behave like dicts (row["url"]) instead of plain tuples.
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    # Idempotent: safe to run at every startup. No migrations yet (see decision 004).
    with conn:
        conn.execute(SCHEMA)


def add_target(conn: sqlite3.Connection, url: str) -> dict:
    # `with conn` commits on success and rolls back on error.
    # A duplicate URL raises sqlite3.IntegrityError (UNIQUE constraint).
    with conn:
        cursor = conn.execute("INSERT INTO targets (url) VALUES (?)", (url,))
    row = conn.execute(
        "SELECT id, url, created_at FROM targets WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return dict(row)


def list_targets(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, url, created_at FROM targets ORDER BY id"
    ).fetchall()
    return [dict(row) for row in rows]


def delete_target(conn: sqlite3.Connection, target_id: int) -> bool:
    """Return True if a target was deleted, False if the id did not exist."""
    with conn:
        cursor = conn.execute("DELETE FROM targets WHERE id = ?", (target_id,))
    return cursor.rowcount == 1
