from __future__ import annotations

from datetime import datetime

from shared.content_contract import CONTENT_KIND_ARTICLE, CONTENT_KIND_NEWS, delivery_key
from ..core.exceptions import ValidationError


DEFAULT_DELIVERY_SCHEDULE = {
    CONTENT_KIND_NEWS: "20:00",
    CONTENT_KIND_ARTICLE: "21:00",
}


class DeliverySettingsService:
    def __init__(self, config_repository, transaction):
        self._config_repository = config_repository
        self._transaction = transaction

    def get_schedule(self) -> dict:
        repo = self._config_repository()
        return {
            "news_time": self._validated_time(
                repo.get_config(delivery_key(CONTENT_KIND_NEWS, "time")),
                DEFAULT_DELIVERY_SCHEDULE[CONTENT_KIND_NEWS],
            ),
            "article_time": self._validated_time(
                repo.get_config(delivery_key(CONTENT_KIND_ARTICLE, "time")),
                DEFAULT_DELIVERY_SCHEDULE[CONTENT_KIND_ARTICLE],
            ),
        }

    def target_time(self, content_kind: str) -> tuple[int, int, str]:
        field = "article_time" if content_kind == CONTENT_KIND_ARTICLE else "news_time"
        value = self.get_schedule()[field]
        hour, minute = map(int, value.split(":"))
        return hour, minute, value

    @staticmethod
    def _validated_time(value: str | None, default: str) -> str:
        candidate = value or default
        try:
            datetime.strptime(candidate, "%H:%M")
            return candidate
        except (TypeError, ValueError):
            return default

    def set_schedule(self, news_time: str | None, article_time: str | None) -> dict:
        try:
            with self._transaction() as repos:
                repo = repos.config
                if news_time:
                    datetime.strptime(news_time, "%H:%M")
                    repo.set_config(delivery_key(CONTENT_KIND_NEWS, "time"), news_time)
                if article_time:
                    datetime.strptime(article_time, "%H:%M")
                    repo.set_config(delivery_key(CONTENT_KIND_ARTICLE, "time"), article_time)
            return {"status": "success", "message": "Push time(s) updated successfully"}
        except ValueError as exc:
            raise ValidationError("时间格式无效，请使用 HH:MM") from exc
