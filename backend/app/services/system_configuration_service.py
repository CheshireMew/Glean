from __future__ import annotations


class SystemConfigurationService:
    def __init__(self, system_settings, automation_settings, delivery_settings, transaction):
        self._system_settings = system_settings
        self._automation_settings = automation_settings
        self._delivery_settings = delivery_settings
        self._transaction = transaction

    def save(self, timezone: str, automation: dict, news_time: str | None, article_time: str | None) -> dict:
        with self._transaction():
            self._system_settings.set_timezone(timezone)
            self._automation_settings.set_config(automation)
            self._delivery_settings.set_schedule(news_time, article_time)
        return {"message": "系统基础配置已原子保存"}
