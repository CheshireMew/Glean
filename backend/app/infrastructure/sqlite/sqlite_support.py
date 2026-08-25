from __future__ import annotations

import sqlite3
import re


def table_exists(cursor: sqlite3.Cursor, table_name: str) -> bool:
    cursor.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table_name,))
    return cursor.fetchone() is not None


def column_exists(cursor: sqlite3.Cursor, table_name: str, column_name: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table_name})")
    return any(row[1] == column_name for row in cursor.fetchall())


def ensure_column(cursor: sqlite3.Cursor, table_name: str, column_name: str, definition: str) -> None:
    if not column_exists(cursor, table_name, column_name):
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def version_key(value: str) -> tuple[int, ...]:
    numbers = tuple(int(part) for part in re.findall(r"\d+", value))
    return numbers or (0,)


def sql_string_list(values) -> str:
    """Render trusted contract literals for SQLite DDL and trigger definitions."""
    return ",".join("'" + str(value).replace("'", "''") + "'" for value in values)
