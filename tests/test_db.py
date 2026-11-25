import sqlite3

import pytest

from site_monitor import db


@pytest.fixture
def conn(tmp_path):
    # A fresh database file per test, deleted automatically by pytest.
    conn = db.connect(str(tmp_path / "test.db"))
    db.init_db(conn)
    yield conn
    conn.close()


def test_init_db_is_idempotent(conn):
    db.init_db(conn)  # second call must not fail


def test_add_and_list_targets(conn):
    first = db.add_target(conn, "https://example.com")
    second = db.add_target(conn, "https://example.org")

    assert first["id"] != second["id"]
    assert first["created_at"]
    assert [t["url"] for t in db.list_targets(conn)] == [
        "https://example.com",
        "https://example.org",
    ]


def test_duplicate_url_is_rejected(conn):
    db.add_target(conn, "https://example.com")

    with pytest.raises(sqlite3.IntegrityError):
        db.add_target(conn, "https://example.com")


def test_delete_target(conn):
    target = db.add_target(conn, "https://example.com")

    assert db.delete_target(conn, target["id"]) is True
    assert db.list_targets(conn) == []


def test_delete_unknown_target_returns_false(conn):
    assert db.delete_target(conn, 999) is False


def test_data_survives_reconnect(tmp_path):
    path = str(tmp_path / "persist.db")
    conn = db.connect(path)
    db.init_db(conn)
    db.add_target(conn, "https://example.com")
    conn.close()

    conn = db.connect(path)
    assert [t["url"] for t in db.list_targets(conn)] == ["https://example.com"]
    conn.close()


def test_database_path_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", "/data/custom.db")
    assert db.get_database_path() == "/data/custom.db"

    monkeypatch.delenv("DATABASE_PATH")
    assert db.get_database_path() == db.DEFAULT_DATABASE_PATH
