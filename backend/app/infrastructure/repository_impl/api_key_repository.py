from typing import Optional
import hashlib

from .base_repository import BaseRepository


class ApiKeyRepository(BaseRepository):
    def get_analyst_api_keys(self):
        cursor = self.execute('SELECT id, key_name, key_prefix, notes, enabled, created_at, last_used_at FROM api_keys ORDER BY id DESC')
        return [dict(row) for row in cursor.fetchall()]

    def create_analyst_api_key(self, key_name: str, raw_api_key: str, notes: Optional[str]):
        api_key_hash = hashlib.sha256(raw_api_key.encode("utf-8")).hexdigest()
        key_prefix = f"{raw_api_key[:12]}…"
        cursor = self.execute(
            'INSERT INTO api_keys (key_name, api_key, key_prefix, notes, created_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)',
            (key_name, api_key_hash, key_prefix, notes),
        )
        return cursor.lastrowid

    def authenticate(self, raw_api_key: str) -> Optional[dict]:
        api_key_hash = hashlib.sha256(raw_api_key.encode("utf-8")).hexdigest()
        row = self.execute(
            "SELECT id, key_name FROM api_keys WHERE api_key = ? AND enabled = 1",
            (api_key_hash,),
        ).fetchone()
        if not row:
            return None
        self.execute("UPDATE api_keys SET last_used_at = CURRENT_TIMESTAMP WHERE id = ?", (row["id"],))
        return dict(row)

    def set_enabled(self, key_id: int, enabled: bool) -> bool:
        return self.execute("UPDATE api_keys SET enabled = ? WHERE id = ?", (int(enabled), key_id)).rowcount > 0

    def delete_analyst_api_key(self, key_id: int) -> bool:
        cursor = self.execute('DELETE FROM api_keys WHERE id = ?', (key_id,))
        return cursor.rowcount > 0
