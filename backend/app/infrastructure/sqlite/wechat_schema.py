import sqlite3


def create_wechat_schema(cursor: sqlite3.Cursor) -> None:
    cursor.execute("""CREATE TABLE IF NOT EXISTS wechat_sources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fake_id TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        alias TEXT NOT NULL DEFAULT '',
        introduction TEXT NOT NULL DEFAULT '',
        enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
        default_limit INTEGER NOT NULL DEFAULT 10 CHECK(default_limit BETWEEN 1 AND 100),
        default_interval INTEGER NOT NULL DEFAULT 240 CHECK(default_interval BETWEEN 30 AND 10080),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
