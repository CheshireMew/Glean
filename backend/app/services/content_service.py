from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional
import zoneinfo

from shared.content_contract import (
    ARCHIVE_STATUS_BLOCKED,
    ARCHIVE_STATUS_READY,
    EXPORT_SCOPE_ARCHIVE,
    EXPORT_SCOPE_BLOCKED,
    EXPORT_SCOPE_DISCARDED,
    EXPORT_SCOPE_INCOMING,
    EXPORT_SCOPE_REVIEW,
    EXPORT_SCOPE_SELECTED,
    REVIEW_STATUS_DISCARDED,
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_SELECTED,
    SYSTEM_TIMEZONE_KEY,
    CONTENT_KINDS,
)
from ..core.exceptions import BusinessError, DatabaseError, ValidationError


class ContentService:
    def __init__(
        self,
        news_admin_repository,
        content_query_repository,
        event_query_repository,
        archive_query_repository,
        review_admin_repository,
        config_repository,
    ):
        self._news_admin_repository = news_admin_repository
        self._content_query_repository = content_query_repository
        self._event_query_repository = event_query_repository
        self._archive_query_repository = archive_query_repository
        self._review_admin_repository = review_admin_repository
        self._config_repository = config_repository

    def get_source_stats(self, content_kind: str = "news") -> Dict:
        try:
            return self._news_admin_repository().get_stats(content_kind)
        except Exception as exc:
            raise DatabaseError(f"查询统计失败: {str(exc)}") from exc

    def get_dashboard_overview(self, content_kind: str = "news") -> Dict:
        return self._content_query_repository().get_dashboard_overview(content_kind)

    def list_source_groups(self, page: int, limit: int, source: Optional[str], keyword: Optional[str], content_kind: str) -> Dict:
        return self._event_query_repository().list_groups(page, limit, source, keyword, content_kind)

    def list_incoming(self, page: int, limit: int, source: Optional[str], keyword: Optional[str], content_kind: str) -> Dict:
        return self._news_admin_repository().get_incoming_news(page, limit, source, keyword, content_kind)

    def list_archive(self, page: int, limit: int, source: Optional[str], keyword: Optional[str], content_kind: str) -> Dict:
        return self._archive_query_repository().list_entries(page, limit, source, keyword, content_kind, ARCHIVE_STATUS_READY)

    def list_blocked(self, page: int, limit: int, keyword: Optional[str], content_kind: str) -> Dict:
        return self._archive_query_repository().list_entries(page, limit, None, keyword, content_kind, ARCHIVE_STATUS_BLOCKED)

    def list_review_queue(self, page: int, limit: int, source: Optional[str], keyword: Optional[str], content_kind: str) -> Dict:
        return self._review_admin_repository().list_entries(page, limit, source, keyword, content_kind, REVIEW_STATUS_PENDING)

    def list_review_decisions(self, decision: str, page: int, limit: int, source: Optional[str], keyword: Optional[str], content_kind: str) -> Dict:
        if decision not in (REVIEW_STATUS_SELECTED, REVIEW_STATUS_DISCARDED):
            raise BusinessError("无效的审核决策类型")
        return self._review_admin_repository().list_entries(page, limit, source, keyword, content_kind, decision)

    def stream_export_content(
        self,
        scope: str,
        start_date: Optional[str],
        end_date: Optional[str],
        keyword: Optional[str],
        source: Optional[str],
        content_kind: Optional[str],
        fields: Optional[str],
    ):
        scopes = {
            EXPORT_SCOPE_INCOMING,
            EXPORT_SCOPE_ARCHIVE,
            EXPORT_SCOPE_BLOCKED,
            EXPORT_SCOPE_REVIEW,
            EXPORT_SCOPE_SELECTED,
            EXPORT_SCOPE_DISCARDED,
        }
        if scope not in scopes:
            raise BusinessError("无效的导出范围")
        if content_kind and content_kind not in CONTENT_KINDS:
            raise ValidationError("内容类型无效")
        for label, value in (("开始日期", start_date), ("结束日期", end_date)):
            if value:
                try:
                    datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError as exc:
                    raise ValidationError(f"{label}格式无效，请使用 ISO 日期或时间") from exc
        timezone_name = self._config_repository().get_config(SYSTEM_TIMEZONE_KEY) or "Asia/Shanghai"
        try:
            local_timezone = zoneinfo.ZoneInfo(timezone_name)
        except Exception:
            local_timezone = zoneinfo.ZoneInfo("Asia/Shanghai")

        def normalize_boundary(value: str | None) -> str | None:
            if not value:
                return None
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=local_timezone)
            return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        start_date = normalize_boundary(start_date)
        end_date = normalize_boundary(end_date)
        if start_date and end_date and start_date > end_date:
            raise ValidationError("开始日期不能晚于结束日期")

        field_list = [field.strip() for field in fields.split(",") if field.strip()] if fields else []
        return self._content_query_repository().stream_export(
            scope, start_date, end_date, keyword, source, content_kind, field_list
        )

    def get_export_filename(self) -> str:
        return f"glean_export_{datetime.now().strftime('%Y%m%d%H%M')}.json"
