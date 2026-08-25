from __future__ import annotations

import re
from typing import Dict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..core.exceptions import NotFoundError, ValidationError


class PublicationService:
    MASKED_SECRET = "••••••••"
    SECRET_KEYS = {"bot_token", "password", "token", "api_key", "secret"}

    def __init__(self, repository, transaction):
        self._repository = repository
        self._transaction = transaction

    def list_publications(self, public_only: bool = False) -> list[Dict]:
        return self._repository().list_publications(public_only)

    def get_publication(self, publication_id: int) -> Dict:
        publication = self._repository().get_publication(publication_id)
        if not publication:
            raise NotFoundError("发布频道不存在")
        return publication

    def get_publication_by_slug(self, public_slug: str) -> Dict:
        publication = self._repository().get_publication_by_public_slug(public_slug)
        if not publication:
            raise NotFoundError("公开频道不存在")
        return publication

    def update_publication(self, publication_id: int, values: Dict) -> Dict:
        public_slug = values.get("public_slug")
        if public_slug is not None and not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", public_slug):
            raise ValidationError("公开频道标识只能包含小写字母、数字和连字符")
        digest_time = values.get("digest_time")
        if digest_time is not None and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", digest_time):
            raise ValidationError("摘要时间必须使用 HH:MM")
        timezone_name = values.get("timezone")
        if timezone_name:
            try:
                ZoneInfo(timezone_name)
            except ZoneInfoNotFoundError as exc:
                raise ValidationError("发布频道时区无效") from exc
        template = values.get("template")
        if template is not None:
            text_fields = ("title_prefix", "title_suffix", "intro", "footer")
            invalid_text = [key for key in text_fields if key in template and not isinstance(template[key], str)]
            if invalid_text:
                raise ValidationError(f"模板字段必须是文字：{', '.join(invalid_text)}")
            if "weekday" in template:
                weekday = template["weekday"]
                if isinstance(weekday, bool) or not isinstance(weekday, int) or not 0 <= weekday <= 6:
                    raise ValidationError("周报 weekday 必须是 0 到 6 的整数")
        with self._transaction() as tx:
            if not tx.publications.get_publication(publication_id):
                raise NotFoundError("发布频道不存在")
            tx.publications.update_publication(publication_id, values)
            if "targets" in values:
                channel_ids = {channel["id"] for channel in tx.publications.list_channels()}
                invalid = [target["channel_id"] for target in values["targets"] if target["channel_id"] not in channel_ids]
                if invalid:
                    raise ValidationError(f"发布目标引用了不存在的渠道：{invalid}")
                tx.publications.replace_targets(publication_id, values["targets"])
        return self.get_publication(publication_id)

    def list_channels(self) -> list[Dict]:
        return [self._public_channel(channel) for channel in self._repository().list_channels()]

    @classmethod
    def _public_channel(cls, channel: Dict) -> Dict:
        item = dict(channel)
        item["config"] = {
            key: cls.MASKED_SECRET if key.lower() in cls.SECRET_KEYS and value else value
            for key, value in (channel.get("config") or {}).items()
        }
        return item

    def save_channel(self, values: Dict, channel_id: int | None = None) -> Dict:
        slug = values["slug"].strip().lower()
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            raise ValidationError("渠道标识只能包含小写字母、数字和连字符")
        config = dict(values.get("config") or {})
        existing = self._repository().get_channel(channel_id) if channel_id else None
        if existing:
            for key, value in list(config.items()):
                if value == self.MASKED_SECRET:
                    if key in (existing.get("config") or {}):
                        config[key] = existing["config"][key]
                    else:
                        config.pop(key)
        normalized = {**values, "slug": slug, "name": values["name"].strip(), "config": config}
        if not normalized["name"]:
            raise ValidationError("渠道名称不能为空")
        saved_id = self._repository().save_channel(normalized, channel_id)
        if not saved_id:
            raise NotFoundError("投递渠道不存在")
        return self._public_channel(self._repository().get_channel(saved_id))
