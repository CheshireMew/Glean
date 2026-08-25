from __future__ import annotations

from typing import Dict


class TelegramAutomationDeliveryService:
    """Coordinates the three independent Telegram automation delivery workflows."""

    def __init__(self, telegram_gateway, daily_delivery, automatic_entry_delivery):
        self._telegram_gateway = telegram_gateway
        self._daily_delivery = daily_delivery
        self._automatic_entry_delivery = automatic_entry_delivery

    async def run_cycle(self) -> Dict:
        if not self._telegram_gateway.has_bot_config():
            return {"status": "skipped", "message": "Telegram 未启用或配置不完整"}
        news_report = await self._daily_delivery.send_news()
        article_report = await self._daily_delivery.send_articles()
        await self._automatic_entry_delivery.send_pending()
        return {
            "status": "completed",
            "news_report": news_report,
            "article_report": article_report,
        }
