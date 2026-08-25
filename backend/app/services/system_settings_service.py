from __future__ import annotations

from datetime import datetime
import zoneinfo

from shared.content_contract import SYSTEM_TIMEZONE_KEY
from ..core.exceptions import ValidationError


class SystemSettingsService:
    def __init__(self, config_repository):
        self._config_repository = config_repository

    def get_timezone(self) -> dict:
        return {"timezone": self._config_repository().get_config(SYSTEM_TIMEZONE_KEY) or "Asia/Shanghai"}

    def get_system_time(self) -> datetime:
        return self._config_repository().get_system_time()

    def set_timezone(self, timezone: str) -> dict:
        try:
            zoneinfo.ZoneInfo(timezone)
            self._config_repository().set_config(SYSTEM_TIMEZONE_KEY, timezone)
            return {"status": "success", "message": f"Timezone set to {timezone}"}
        except Exception as exc:
            raise ValidationError("时区无效") from exc
