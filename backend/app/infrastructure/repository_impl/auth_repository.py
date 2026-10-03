from .base_repository import BaseRepository


class AuthRepository(BaseRepository):
    def create_session(self, session_id: str, username: str, expires_at: int, now: int):
        self.execute("DELETE FROM admin_sessions WHERE expires_at <= ?", (now,))
        self.execute(
            "INSERT INTO admin_sessions(session_id, username, expires_at) VALUES (?, ?, ?)",
            (session_id, username, expires_at),
        )

    def session_active(self, session_id: str, username: str, now: int) -> bool:
        return self.execute(
            "SELECT 1 FROM admin_sessions WHERE session_id = ? AND username = ? AND expires_at > ?",
            (session_id, username, now),
        ).fetchone() is not None

    def revoke_session(self, session_id: str):
        self.execute("DELETE FROM admin_sessions WHERE session_id = ?", (session_id,))

    def revoke_all_sessions(self):
        self.execute("DELETE FROM admin_sessions")

    def reserve_attempt(self, scope: str, client: str, now: int) -> int:
        # The caller holds BEGIN IMMEDIATE, including the check and both increments.
        self.execute("DELETE FROM auth_attempts WHERE expires_at <= ?", (now,))
        buckets = [(f"{scope}:all", 30), (f"{scope}:client:{client}", 5)]
        waits = []
        for bucket, limit in buckets:
            row = self.execute("SELECT * FROM auth_attempts WHERE bucket = ?", (bucket,)).fetchone()
            if row and row["attempts"] >= limit:
                waits.append(row["expires_at"] - now)
        if waits:
            return max(waits)
        for bucket, _ in buckets:
            self.execute("""
                INSERT INTO auth_attempts(bucket, attempts, expires_at) VALUES (?, 1, ?)
                ON CONFLICT(bucket) DO UPDATE SET attempts = attempts + 1
            """, (bucket, now + 600))
        return 0

    def finish_successful_attempt(self, scope: str, client: str):
        self.execute("DELETE FROM auth_attempts WHERE bucket = ?", (f"{scope}:client:{client}",))
        self.execute(
            "UPDATE auth_attempts SET attempts = MAX(0, attempts - 1) WHERE bucket = ?",
            (f"{scope}:all",),
        )
