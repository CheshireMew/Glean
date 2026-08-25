from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Dict

from ..core.exceptions import NotFoundError
from ..infrastructure.deduplication import build_local_deduplicator
from ..infrastructure.repositories import repositories
from .automation_settings_service import automation_settings_service
from .content_transition_service import content_transition_service


class DeduplicationService:
    @staticmethod
    def _repos():
        return repositories()

    async def deduplicate_news(self, time_window_hours: int, action: str, threshold: float, content_kind: str) -> Dict:
        return await asyncio.to_thread(self._deduplicate_news_sync, time_window_hours, action, threshold, content_kind)

    def _deduplicate_news_sync(self, time_window_hours: int, action: str, threshold: float, content_kind: str) -> Dict:
        news_list = self._repos().news_runtime.get_news_by_time_range(time_window_hours, type_filter=content_kind)
        if not news_list:
            return {"status": "success", "message": "未找到符合条件的内容", "stats": {"total_scanned": 0, "duplicates_found": 0, "duplicates_processed": 0}}

        automation_settings_service.set_dedup_threshold(threshold)
        deduplicator = build_local_deduplicator(threshold, time_window_hours)
        marked_news = deduplicator.mark_duplicates(news_list)
        duplicates = [item for item in marked_news if item.get("is_local_duplicate", False)]
        duplicate_groups = {}

        for duplicate in duplicates:
            master_id = duplicate.get("duplicate_of")
            master = next((item for item in marked_news if item["id"] == master_id), None)
            if not master:
                continue
            duplicate_groups.setdefault(
                master_id,
                {
                    "master": {"id": master["id"], "title": master["title"], "source": master["source_site"]},
                    "duplicates": [],
                },
            )["duplicates"].append({"id": duplicate["id"], "title": duplicate["title"], "source": duplicate["source_site"]})

        marked_news = content_transition_service.persist_deduplication_results(
            marked_news,
            delete_duplicates=action == "delete",
        )

        archived_count = len([item for item in marked_news if not item.get("is_local_duplicate", False)])
        return {
            "status": "success",
            "message": "归档去重完成",
            "stats": {
                "total_scanned": len(marked_news),
                "duplicates_found": len(duplicates),
                "duplicates_processed": len(duplicates),
                "duplicate_groups": len(duplicate_groups),
                "archived_count": archived_count,
            },
            "duplicate_groups": list(duplicate_groups.values()),
        }

    async def check_news_similarity(self, news_id_1: int, news_id_2: int) -> Dict:
        return await asyncio.to_thread(self._check_news_similarity_sync, news_id_1, news_id_2)

    def _check_news_similarity_sync(self, news_id_1: int, news_id_2: int) -> Dict:
        news_rows = self._repos().news_runtime.get_news_by_ids([news_id_1, news_id_2])
        if len(news_rows) < 2:
            raise NotFoundError("找不到指定内容")

        news_1 = {"id": news_rows[0]["id"], "title": news_rows[0]["title"]}
        news_2 = {"id": news_rows[1]["id"], "title": news_rows[1]["title"]}
        deduplicator = build_local_deduplicator(0.50, 24)
        similarity = deduplicator.calculate_similarity(
            deduplicator.extract_features(news_1["title"]),
            deduplicator.extract_features(news_2["title"]),
        )
        return {
            "news_1": news_1,
            "news_2": news_2,
            "similarity": round(similarity, 4),
            "threshold": deduplicator.similarity_threshold,
            "is_duplicate": similarity >= deduplicator.similarity_threshold,
        }

    async def auto_deduplication(self, content_kind: str = "news"):
        await asyncio.to_thread(self._auto_deduplication_sync, content_kind)

    def _auto_deduplication_sync(self, content_kind: str = "news"):
        window = automation_settings_service.get_window(content_kind)
        scan_hours = window["dedup_hours"]
        dedup_window_hours = window["dedup_window_hours"]
        cutoff_time = (datetime.now() - timedelta(hours=scan_hours)).strftime("%Y-%m-%d %H:%M:%S")
        rows = self._repos().news_runtime.get_incoming_news_since(cutoff_time, content_kind)
        if not rows:
            return

        threshold = automation_settings_service.get_dedup_threshold()
        deduplicator = build_local_deduplicator(threshold, dedup_window_hours)
        marked_news = deduplicator.mark_duplicates(rows)
        content_transition_service.persist_deduplication_results(marked_news)


deduplication_service = DeduplicationService()
