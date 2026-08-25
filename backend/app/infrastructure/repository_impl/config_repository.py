
from datetime import datetime
from typing import Optional
import zoneinfo

from shared.content_contract import SYSTEM_TIMEZONE_KEY
from .base_repository import BaseRepository


class ConfigRepository(BaseRepository):
    def get_by_prefix(self, prefix: str) -> dict[str, str]:
        rows = self.execute("SELECT key, value FROM system_config WHERE key LIKE ?", (f"{prefix}%",)).fetchall()
        return {row["key"]: row["value"] for row in rows}

    def get_config(self, key: str) -> Optional[str]:
        cursor = self.execute("SELECT value FROM system_config WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row['value'] if row else None

    def set_config(self, key: str, value: str):
        self.execute(
            """
            INSERT INTO system_config (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (key, value),
        )

    def delete_config(self, key: str) -> None:
        self.execute("DELETE FROM system_config WHERE key = ?", (key,))

    def get_system_time(self) -> datetime:
        tz_str = self.get_config(SYSTEM_TIMEZONE_KEY) or 'Asia/Shanghai'
        try:
            tz = zoneinfo.ZoneInfo(tz_str)
        except Exception:
            tz = zoneinfo.ZoneInfo('Asia/Shanghai')
        return datetime.now(tz)
