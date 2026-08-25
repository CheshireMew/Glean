from __future__ import annotations

from shared.content_contract import integration_key
from ..core.exceptions import ValidationError


class TelegramSettingsService:
    def __init__(self, config_repository, transaction):
        self._config_repository = config_repository
        self._transaction = transaction

    def get_config(self) -> dict:
        repo = self._config_repository()
        token = repo.get_config(integration_key("telegram", "bot_token")) or ""
        return {
            "bot_token": "••••••••" if token else "",
            "has_bot_token": bool(token),
            "chat_id": repo.get_config(integration_key("telegram", "chat_id")) or "",
            "enabled": repo.get_config(integration_key("telegram", "enabled")) == "true",
        }

    def set_config(self, config: dict) -> dict:
        with self._transaction() as repos:
            repo = repos.config
            existing_token = repo.get_config(integration_key("telegram", "bot_token")) or ""
            supplied_token = (config.get("bot_token") or "").strip()
            token = existing_token if supplied_token == "••••••••" else supplied_token or existing_token
            chat_id = (config.get("chat_id") or "").strip()
            if config.get("enabled") and (not token or not chat_id):
                raise ValidationError("启用 Telegram 前必须配置 Bot Token 和 Chat ID")
            if supplied_token and supplied_token != "••••••••":
                repo.set_config(integration_key("telegram", "bot_token"), supplied_token)
            repo.set_config(integration_key("telegram", "chat_id"), chat_id)
            repo.set_config(integration_key("telegram", "enabled"), "true" if config["enabled"] else "false")
        return {"message": "配置已保存"}
