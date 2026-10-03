import sqlite3


def create_auth_schema(cursor: sqlite3.Cursor) -> None:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin_sessions (
            session_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            expires_at INTEGER NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_admin_sessions_expiry ON admin_sessions(expires_at)")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS auth_attempts (
            bucket TEXT PRIMARY KEY,
            attempts INTEGER NOT NULL,
            expires_at INTEGER NOT NULL
        )
    """)
