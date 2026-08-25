from __future__ import annotations

from typing import Iterable

from backend.app.core.config import settings
from shared.content_contract import integration_key
from ..core.exceptions import BusinessError, ValidationError
from .telegram_bot import TelegramBot


class TelegramGatewayService:
    MASKED_SECRET = "••••••••"

    def __init__(self, config_repository):
        self._config_repository = config_repository

    def _resolve_bot_config(self) -> tuple[str | None, str | None]:
        config_repo = self._config_repository()
        token = settings.TELEGRAM_BOT_TOKEN or config_repo.get_config(integration_key("telegram", "bot_token"))
        chat_id = settings.TELEGRAM_CHAT_ID or config_repo.get_config(integration_key("telegram", "chat_id"))
        return token, chat_id

    def has_bot_config(self) -> bool:
        token, chat_id = self._resolve_bot_config()
        enabled = self._config_repository().get_config(integration_key("telegram", "enabled"))
        return enabled != "false" and bool(token and chat_id)

    def require_bot(self, config: dict | None = None) -> TelegramBot:
        if config is None:
            token, chat_id = self._resolve_bot_config()
        else:
            token = config.get("bot_token")
            chat_id = config.get("chat_id")
            if token == self.MASKED_SECRET:
                token, _ = self._resolve_bot_config()
        if not token or not chat_id:
            raise ValidationError("请先在配置中设置 Telegram Bot Token 和 Chat ID")
        return TelegramBot(token, chat_id)

    async def send_or_raise(self, text: str, error_message: str, parse_mode: str = "HTML") -> None:
        bot = self.require_bot()
        success = await bot.send_message(text, parse_mode=parse_mode)
        if not success:
            raise BusinessError(error_message)

    async def send_message_result(self, text: str, parse_mode: str = "HTML") -> dict:
        return await self.require_bot().send_message_result(text, parse_mode=parse_mode)

    async def send_many_or_raise(self, messages: Iterable[str], error_message: str, parse_mode: str = "HTML") -> None:
        bot = self.require_bot()
        for message in messages:
            success = await bot.send_message(message, parse_mode=parse_mode)
            if not success:
                raise BusinessError(error_message)

    async def send_test_message(self, config: dict | None = None) -> dict:
        bot = self.require_bot(config)
        success = await bot.send_message(
            "🔔 <b>AINews</b>\n这是一条测试消息。",
            parse_mode="HTML",
        )
        if not success:
            raise BusinessError("发送失败，请检查 Bot 配置和网络连接")
        return {"message": "测试消息发送成功"}
