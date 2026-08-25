from __future__ import annotations

from contextlib import contextmanager

from .sqlite.db_sqlite import Database
from .lease_fencing import assert_current_operation_lease


database = Database()


def init_database() -> None:
    database.init_db()


def assert_database_ready() -> None:
    database.assert_schema_current()


@contextmanager
def db_connection():
    conn = database.connect()
    try:
        yield conn
    finally:
        conn.close()

@contextmanager
def transaction():
    with db_connection() as conn:
        try:
            conn.execute("BEGIN")
            yield conn
            assert_current_operation_lease(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
