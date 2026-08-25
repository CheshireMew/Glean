from __future__ import annotations

from typing import Dict
import uuid

from shared.content_contract import (
    CONTENT_KIND_ARTICLE,
    CONTENT_KIND_NEWS,
    DELIVERY_OPERATION_STATUS_SENT,
    delivery_key,
)

from ..core.exceptions import ValidationError
from .daily_report_service import PreparedDailyReport


class DailyDeliveryService:
    """Owns scheduling, preparation and durable finalization of daily reports."""

    def __init__(
        self,
        config_repository,
        delivery_settings,
        operation_repository,
        execution_repository,
        daily_reports,
        delivery_operations,
    ):
        self._config_repository = config_repository
        self._delivery_settings = delivery_settings
        self._operation_repository = operation_repository
        self._execution_repository = execution_repository
        self._daily_reports = daily_reports
        self._delivery_operations = delivery_operations

    def _target_time_reached(self, content_kind: str, now) -> tuple[bool, str]:
        hour, minute, value = self._delivery_settings.target_time(content_kind)
        return now.hour * 60 + now.minute >= hour * 60 + minute, value

    @staticmethod
    def _last_delivery_key(content_kind: str) -> str:
        return delivery_key(content_kind, "last_date")

    @staticmethod
    def _report_metadata(report: PreparedDailyReport, automatic: bool) -> Dict:
        return {
            "date": report.date,
            "content_kind": report.content_kind,
            "title": report.title,
            "entries": report.entries,
            "items": report.items,
            "content": report.content,
            "automatic": automatic,
        }

    def finalize_success(self, operation_key: str) -> tuple[int, int]:
        operation = self._operation_repository().get_operation(operation_key)
        metadata = (operation or {}).get("metadata") or {}
        required = {"date", "content_kind", "title", "entries", "items", "content"}
        if not operation or not required.issubset(metadata):
            raise ValidationError("日报交付记录缺少落库所需元数据")
        parts = [part["content"] for part in self._execution_repository().list_parts(operation["id"])]
        report = PreparedDailyReport(parts=parts, **{key: metadata[key] for key in required})
        report_id = self._daily_reports.persist_success(report, operation_key)
        if metadata.get("automatic"):
            self._config_repository().set_config(
                self._last_delivery_key(report.content_kind), report.date
            )
        return report_id, len(report.entries)

    async def send(
        self,
        content_kind: str,
        force: bool = False,
        operation_key: str | None = None,
    ) -> Dict:
        config_repo = self._config_repository()
        now = config_repo.get_system_time()
        if not force:
            reached, target_time = self._target_time_reached(content_kind, now)
            if not reached:
                return {
                    "status": "skipped",
                    "message": f"Not push time yet (Current: {now.strftime('%H:%M')}, Target: {target_time})",
                }
            today = now.strftime("%Y-%m-%d")
            if config_repo.get_config(self._last_delivery_key(content_kind)) == today:
                return {"status": "skipped", "message": "Already pushed today"}

        key = operation_key or (
            f"manual-daily:{content_kind}:{uuid.uuid4().hex}"
            if force
            else f"daily:{content_kind}:{now.strftime('%Y-%m-%d')}"
        )
        existing = self._operation_repository().get_operation(key)
        if not existing:
            report = self._daily_reports.prepare(content_kind, now)
            if not report:
                return {"status": "skipped", "message": "No content found"}
            self._delivery_operations.prepare(
                key,
                "daily_manual" if force else "daily_auto",
                content_kind,
                report.parts,
                [entry["id"] for entry in report.entries],
                self._report_metadata(report, automatic=not force),
            )

        delivery = await self._delivery_operations.send(key)
        if delivery["status"] != DELIVERY_OPERATION_STATUS_SENT:
            return {**delivery, "message": "日报尚未完整送达，未写入成功状态"}
        report_id, entry_count = self.finalize_success(key)
        return {
            **delivery,
            "status": "success",
            "count": entry_count,
            "report_id": report_id,
            "message": f"Pushed {entry_count} items",
        }

    async def send_news(self, force: bool = False, operation_key: str | None = None) -> Dict:
        return await self.send(CONTENT_KIND_NEWS, force, operation_key)

    async def send_articles(self, force: bool = False, operation_key: str | None = None) -> Dict:
        return await self.send(CONTENT_KIND_ARTICLE, force, operation_key)
