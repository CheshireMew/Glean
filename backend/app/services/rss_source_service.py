from __future__ import annotations

import re
from typing import Dict
from urllib.parse import urlparse

from shared.content_contract import CONTENT_KINDS
from ..core.exceptions import BusinessError, NotFoundError, ValidationError


RSS_RUNTIME_PREFIX = "rss__"


def rss_runtime_name(slug: str) -> str:
    return f"{RSS_RUNTIME_PREFIX}{slug}"


def rss_slug_from_runtime_name(name: str) -> str | None:
    if not name.startswith(RSS_RUNTIME_PREFIX):
        return None
    return name[len(RSS_RUNTIME_PREFIX):]


class RssSourceService:
    def __init__(self, rss_source_repository, transaction):
        self._rss_source_repository = rss_source_repository
        self._transaction = transaction

    def list_sources(self) -> Dict:
        return {"sources": self._rss_source_repository().list_sources()}

    def list_enabled_sources(self) -> list[Dict]:
        return self._rss_source_repository().list_sources(enabled_only=True)

    def get_source_by_runtime_name(self, name: str) -> Dict | None:
        slug = rss_slug_from_runtime_name(name)
        if not slug:
            return None
        return self._rss_source_repository().get_source_by_slug(slug)

    def create_source(self, payload: Dict) -> Dict:
        with self._transaction() as tx_repos:
            normalized = self._normalize_payload(payload)
            self._ensure_unique(tx_repos, None, normalized)
            return tx_repos.rss_sources.create_source(normalized)

    def update_source(self, source_id: int, payload: Dict) -> Dict:
        with self._transaction() as tx_repos:
            existing = tx_repos.rss_sources.get_source(source_id)
            if not existing:
                raise NotFoundError("RSS 源不存在")
            old_runtime_name = rss_runtime_name(existing["slug"])
            if tx_repos.scraper_state.is_active(old_runtime_name):
                raise BusinessError("RSS 源正在采集，停止任务后才能修改")
            normalized = self._normalize_payload(payload)
            self._ensure_unique(tx_repos, source_id, normalized)
            updated = tx_repos.rss_sources.update_source(source_id, normalized)
            if not updated:
                raise NotFoundError("RSS 源不存在")
            new_runtime_name = rss_runtime_name(normalized["slug"])
            if new_runtime_name != old_runtime_name:
                old_key = f"scraper.{old_runtime_name}.runtime"
                new_key = f"scraper.{new_runtime_name}.runtime"
                old_config = tx_repos.config.get_config(old_key)
                if old_config and not tx_repos.config.get_config(new_key):
                    tx_repos.config.set_config(new_key, old_config)
                tx_repos.config.delete_config(old_key)
                tx_repos.scraper_state.rename_state(old_runtime_name, new_runtime_name)
                tx_repos.scraper_commands.rename_commands_for_scraper(old_runtime_name, new_runtime_name)
            return updated

    def delete_source(self, source_id: int) -> Dict:
        with self._transaction() as tx_repos:
            source = tx_repos.rss_sources.get_source(source_id)
            if not source:
                raise NotFoundError("RSS 源不存在")
            runtime_name = rss_runtime_name(source["slug"])
            if tx_repos.scraper_state.is_active(runtime_name):
                raise BusinessError("RSS 源正在采集，停止任务后才能删除")
            deleted = tx_repos.rss_sources.delete_source(source_id)
            if not deleted:
                raise NotFoundError("RSS 源不存在")
            tx_repos.config.delete_config(f"scraper.{runtime_name}.runtime")
            tx_repos.scraper_state.delete_state(runtime_name)
            tx_repos.scraper_commands.delete_commands_for_scraper(runtime_name)
            return {"message": "RSS 源已删除"}

    def _normalize_payload(self, payload: Dict) -> Dict:
        slug = self._resolve_slug(payload.get("slug"), payload.get("display_name"), payload.get("feed_url"))
        display_name = (payload.get("display_name") or "").strip()
        feed_url = self._normalize_url(payload.get("feed_url") or "")
        site_url = self._normalize_url(payload.get("site_url") or "")
        content_kind = payload.get("content_kind") or "article"
        parser_type = payload.get("parser_type") or "generic"
        default_limit = int(payload.get("default_limit") or 20)
        default_interval = int(payload.get("default_interval") or 240)
        enabled = bool(payload.get("enabled", True))

        if not display_name:
            raise ValidationError("RSS 名称不能为空")
        if content_kind not in CONTENT_KINDS:
            raise ValidationError("内容类型无效")
        if parser_type not in {"generic", "summary_source_link"}:
            raise ValidationError("RSS 解析方式无效")
        if default_limit < 1 or default_limit > 100:
            raise ValidationError("抓取条数必须在 1 到 100 之间")
        if default_interval < 5 or default_interval > 10080:
            raise ValidationError("抓取频率必须在 5 到 10080 分钟之间")

        return {
            "slug": slug,
            "display_name": display_name,
            "feed_url": feed_url,
            "site_url": site_url,
            "content_kind": content_kind,
            "parser_type": parser_type,
            "default_limit": default_limit,
            "default_interval": default_interval,
            "enabled": enabled,
        }

    def _ensure_unique(self, repo_set, current_id: int | None, payload: Dict) -> None:
        slug_match = repo_set.rss_sources.get_source_by_slug(payload["slug"])
        if slug_match and slug_match["id"] != current_id:
            raise BusinessError("RSS 标识已存在")

        for source in repo_set.rss_sources.list_sources():
            if source["id"] == current_id:
                continue
            if source["feed_url"] == payload["feed_url"]:
                raise BusinessError("RSS 地址已存在")
            if source["display_name"].strip().lower() == payload["display_name"].strip().lower():
                raise BusinessError("RSS 名称已存在")

    @staticmethod
    def _normalize_slug(value: str) -> str:
        candidate = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
        candidate = candidate.strip("-")
        if not candidate:
            raise ValidationError("RSS 标识不能为空")
        return candidate

    def _resolve_slug(self, explicit_slug: str | None, display_name: str | None, feed_url: str | None) -> str:
        if explicit_slug:
            return self._normalize_slug(explicit_slug)
        for candidate in (display_name or "", feed_url or ""):
            try:
                return self._normalize_slug(candidate)
            except ValidationError:
                continue
        raise ValidationError("RSS 标识不能为空")

    @staticmethod
    def _normalize_url(value: str) -> str:
        parsed = urlparse(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValidationError("URL 无效")
        return value.strip()
