from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict

from ..core.exceptions import NotFoundError


class SourceOperationsService:
    def __init__(self, repository, scraper_registry, transaction, config_repository=None):
        self._repository = repository
        self._scraper_registry = scraper_registry
        self._transaction = transaction
        self._config_repository = config_repository

    def sync_catalog(self) -> Dict:
        definitions = [
            {
                "name": item.name,
                "display_name": item.display_name,
                "source_site": item.source_site,
                "content_kind": item.content_kind,
                "source_type": item.source_type,
                "transport_kind": item.transport_kind,
                "default_limit": item.default_limit,
                "default_interval": item.default_interval,
                "homepage_url": item.homepage_url,
                "authority_type": item.authority_type,
                "is_official": item.is_official,
            }
            for item in self._scraper_registry.list_definitions()
        ]
        with self._transaction() as repos:
            changed = repos.source_operations.sync_catalog(definitions)
        return {"registered": len(definitions), "changed": changed, "sources": self.list_sources(sync=False)}

    def list_sources(self, sync: bool = True) -> list[Dict]:
        if sync:
            self.sync_catalog()
        return self._repository().list_sources()

    def update_source(self, source_key: str, values: Dict) -> Dict:
        if not self._repository().update_source(source_key, values):
            raise NotFoundError("来源不存在")
        return self._repository().get_source(source_key)

    @staticmethod
    def _is_stale(last_run: str | None, hours: int) -> bool:
        if not last_run:
            return True
        try:
            parsed = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed < datetime.now(timezone.utc) - timedelta(hours=hours)
        except ValueError:
            return True

    @staticmethod
    def _parser_drift(previous: Dict | None, current: Dict) -> Dict | None:
        if not previous:
            return None
        reasons = []
        previous_items = int(previous.get("item_count") or 0)
        current_items = int(current.get("item_count") or 0)
        if previous_items >= 5 and current_items <= max(1, int(previous_items * 0.25)):
            reasons.append(
                f"窗口内容量从 {previous_items} 降至 {current_items}"
            )
        previous_completeness = previous.get("content_completeness")
        current_completeness = current.get("content_completeness")
        if (
            previous_completeness is not None
            and current_completeness is not None
            and float(previous_completeness) >= 0.8
            and float(previous_completeness) - float(current_completeness) >= 0.35
        ):
            reasons.append(
                "正文完整率从 "
                f"{float(previous_completeness):.0%} 降至 {float(current_completeness):.0%}"
            )
        if not reasons:
            return None
        return {"reasons": reasons, "baseline": previous, "current": current}

    def snapshot(self, source_key: str | None, hours: int) -> Dict:
        self.sync_catalog()
        sources = self._repository().list_sources()
        if source_key:
            sources = [source for source in sources if source["source_key"] == source_key]
            if not sources:
                raise NotFoundError("来源不存在")
        snapshots = []
        incident_count = 0
        with self._transaction() as repos:
            for source in sources:
                health = repos.source_operations.calculate_health(source["source_key"], hours)
                if not health:
                    continue
                previous = repos.source_operations.latest_health_snapshot(source["source_key"])
                drift = self._parser_drift(previous, health)
                health["id"] = repos.source_operations.save_health_snapshot(health)
                snapshots.append(health)
                incident_specs = []
                if health["error_count"]:
                    incident_specs.append(("fetch_error", health.get("last_error") or "最近一次采集失败"))
                if health["zero_result_count"]:
                    incident_specs.append(("zero_results", "最近一次采集未返回内容"))
                if health["content_completeness"] is not None and health["content_completeness"] < 0.6:
                    incident_specs.append(("content_missing", "正文完整率低于 60%"))
                if drift:
                    incident_specs.append(
                        (
                            "parser_drift",
                            "疑似解析结构漂移：" + "；".join(drift["reasons"]),
                        )
                    )
                interval_hours = max(6, int(source.get("metadata", {}).get("default_interval") or 60) * 3 // 60)
                if source.get("enabled") and self._is_stale(health.get("last_run"), interval_hours):
                    incident_specs.append(("stale_source", f"超过 {interval_hours} 小时没有成功运行记录"))
                for incident_type, summary in incident_specs:
                    details = {**health, "drift": drift} if incident_type == "parser_drift" else health
                    if repos.source_operations.open_incident(source["source_key"], incident_type, summary, details):
                        incident_count += 1
        return {"sources": len(sources), "snapshots": snapshots, "new_incidents": incident_count}

    def list_health(self, source_key: str | None, limit: int) -> list[Dict]:
        return self._repository().list_health(source_key, limit)

    def list_incidents(self, status: str | None, limit: int) -> list[Dict]:
        return self._repository().list_incidents(status, limit)

    def update_incident(self, incident_id: int, status: str) -> Dict:
        if not self._repository().update_incident(incident_id, status):
            raise NotFoundError("来源异常不存在")
        return next(item for item in self._repository().list_incidents(None, 1000) if int(item["id"]) == incident_id)

    def snapshot_if_due(self) -> Dict:
        if self._config_repository is None:
            return {"status": "skipped", "reason": "config repository unavailable"}
        config = self._config_repository()
        today = config.get_system_time().strftime("%Y-%m-%d")
        if config.get_config("source_health.last_snapshot_date") == today:
            return {"status": "skipped", "reason": "already captured", "date": today}
        result = self.snapshot(None, 24)
        config.set_config("source_health.last_snapshot_date", today)
        return {"status": "captured", "date": today, **result}
