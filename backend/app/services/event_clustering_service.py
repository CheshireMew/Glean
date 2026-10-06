from __future__ import annotations

import asyncio
from typing import Dict

from ..core.exceptions import NotFoundError
from ..core.time import utc_cutoff


class EventClusteringService:
    def __init__(self, news_runtime_repository, automation_settings, content_transitions, clusterer_factory):
        self._news_runtime_repository = news_runtime_repository
        self._automation_settings = automation_settings
        self._content_transitions = content_transitions
        self._clusterer_factory = clusterer_factory

    async def cluster_content(self, time_window_hours: int, threshold: float, content_kind: str) -> Dict:
        return await asyncio.to_thread(self._cluster_news_sync, time_window_hours, threshold, content_kind)

    def _cluster_news_sync(self, time_window_hours: int, threshold: float, content_kind: str) -> Dict:
        repository = self._news_runtime_repository()
        eligible = repository.count_news_by_time_range(time_window_hours, content_kind)
        news_list = repository.get_news_by_time_range(time_window_hours, type_filter=content_kind)
        if not news_list:
            return {
                "status": "success",
                "message": "没有待聚合的来源内容",
                "stats": {"sources_scanned": 0, "sources_eligible": eligible, "sources_remaining": 0, "events_created": 0},
            }

        clusterer = self._clusterer_factory(threshold)
        clusters = clusterer.cluster(news_list)
        stats = self._content_transitions.persist_event_clusters(clusters, clusterer, content_kind, time_window_hours)
        return {
            "status": "success",
            "message": "事件聚合完成",
            "stats": {
                "sources_scanned": len(news_list),
                "sources_eligible": eligible,
                "sources_remaining": max(eligible - len(news_list), 0),
                **stats,
            },
        }

    async def check_event_similarity(self, news_id_1: int, news_id_2: int) -> Dict:
        return await asyncio.to_thread(self._check_event_similarity_sync, news_id_1, news_id_2)

    def _check_event_similarity_sync(self, news_id_1: int, news_id_2: int) -> Dict:
        news_rows = self._news_runtime_repository().get_news_by_ids([news_id_1, news_id_2])
        if len(news_rows) < 2:
            raise NotFoundError("找不到指定内容")

        news_1 = {"id": news_rows[0]["id"], "title": news_rows[0]["title"]}
        news_2 = {"id": news_rows[1]["id"], "title": news_rows[1]["title"]}
        clusterer = self._clusterer_factory(self._automation_settings.get_event_cluster_threshold())
        similarity = clusterer.similarity(news_1["title"], news_2["title"])
        return {
            "news_1": news_1,
            "news_2": news_2,
            "similarity": round(similarity, 4),
            "threshold": clusterer.similarity_threshold,
            "is_same_event": clusterer.is_same_event(news_1["title"], news_2["title"]),
        }

    async def auto_cluster_content(self, content_kind: str = "news"):
        await asyncio.to_thread(self._auto_cluster_content_sync, content_kind)

    def _auto_cluster_content_sync(self, content_kind: str = "news"):
        window = self._automation_settings.get_window(content_kind)
        scan_hours = window["cluster_hours"]
        cluster_window_hours = window["cluster_window_hours"]
        cutoff_time = utc_cutoff(scan_hours)
        repository = self._news_runtime_repository()
        eligible = repository.count_incoming_news_since(cutoff_time, content_kind)
        rows = repository.get_incoming_news_since(cutoff_time, content_kind)
        if not rows:
            return {"sources_scanned": 0, "sources_eligible": eligible, "sources_remaining": 0}

        threshold = self._automation_settings.get_event_cluster_threshold()
        clusterer = self._clusterer_factory(threshold)
        clusters = clusterer.cluster(rows)
        stats = self._content_transitions.persist_event_clusters(clusters, clusterer, content_kind, cluster_window_hours)
        return {
            "sources_scanned": len(rows),
            "sources_eligible": eligible,
            "sources_remaining": max(eligible - len(rows), 0),
            **stats,
        }
