from __future__ import annotations

from shared.content_contract import CONTENT_KINDS, EVENT_CLUSTER_THRESHOLD_KEY, automation_key
from ..core.coercion import positive_int
from ..core.exceptions import ValidationError


AUTOMATION_DEFAULTS = {
    "news": {"cluster_hours": 2, "cluster_window_hours": 2, "filter_hours": 24, "ai_scoring_hours": 10, "push_hours": 12},
    "article": {"cluster_hours": 168, "cluster_window_hours": 72, "filter_hours": 168, "ai_scoring_hours": 168, "push_hours": 72},
}
AUTOMATION_FIELD_MAP = {
    "cluster_hours": "scan_hours",
    "cluster_window_hours": "window_hours",
    "filter_hours": "block_hours",
    "ai_scoring_hours": "review_hours",
    "push_hours": "delivery_hours",
}
RUNTIME_DEFAULTS = {
    "enabled": True,
    "start_time": "08:00",
    "end_time": "23:59",
    "interval_minutes": 60,
    "review_batch_size": 50,
    "enrichment_batch_size": 25,
    "max_review_batches_per_cycle": 10,
    "backlog_retry_seconds": 30,
    "scraper_concurrency": 2,
    "maintenance_interval_hours": 24,
    "operational_retention_days": 30,
    "content_retention_days": 365,
}


class AutomationSettingsService:
    def __init__(self, config_repository, transaction):
        self._config_repository = config_repository
        self._transaction = transaction

    def get_config(self) -> dict:
        return {
            **{content_kind: self.get_window(content_kind) for content_kind in CONTENT_KINDS},
            "runtime": self.get_runtime(),
        }

    def get_runtime(self) -> dict:
        repo = self._config_repository()
        enabled_raw = repo.get_config("automation.runtime.enabled")
        return {
            "enabled": (enabled_raw if enabled_raw is not None else "true").lower() == "true",
            "start_time": repo.get_config("automation.runtime.start_time") or RUNTIME_DEFAULTS["start_time"],
            "end_time": repo.get_config("automation.runtime.end_time") or RUNTIME_DEFAULTS["end_time"],
            "interval_minutes": positive_int(
                repo.get_config("automation.runtime.interval_minutes"), RUNTIME_DEFAULTS["interval_minutes"]
            ),
            "review_batch_size": positive_int(
                repo.get_config("automation.runtime.review_batch_size"), RUNTIME_DEFAULTS["review_batch_size"]
            ),
            "enrichment_batch_size": positive_int(
                repo.get_config("automation.runtime.enrichment_batch_size"), RUNTIME_DEFAULTS["enrichment_batch_size"]
            ),
            "max_review_batches_per_cycle": min(
                100,
                positive_int(
                    repo.get_config("automation.runtime.max_review_batches_per_cycle"),
                    RUNTIME_DEFAULTS["max_review_batches_per_cycle"],
                ),
            ),
            "backlog_retry_seconds": min(
                3600,
                max(
                    5,
                    positive_int(
                        repo.get_config("automation.runtime.backlog_retry_seconds"),
                        RUNTIME_DEFAULTS["backlog_retry_seconds"],
                    ),
                ),
            ),
            "scraper_concurrency": min(
                8,
                positive_int(
                    repo.get_config("automation.runtime.scraper_concurrency"),
                    RUNTIME_DEFAULTS["scraper_concurrency"],
                ),
            ),
            "maintenance_interval_hours": min(
                168,
                positive_int(
                    repo.get_config("automation.runtime.maintenance_interval_hours"),
                    RUNTIME_DEFAULTS["maintenance_interval_hours"],
                ),
            ),
            "operational_retention_days": min(
                365,
                max(
                    7,
                    positive_int(
                        repo.get_config("automation.runtime.operational_retention_days"),
                        RUNTIME_DEFAULTS["operational_retention_days"],
                    ),
                ),
            ),
            "content_retention_days": min(
                3650,
                max(
                    30,
                    positive_int(
                        repo.get_config("automation.runtime.content_retention_days"),
                        RUNTIME_DEFAULTS["content_retention_days"],
                    ),
                ),
            ),
        }

    def get_window(self, content_kind: str) -> dict:
        if content_kind not in CONTENT_KINDS:
            raise ValidationError("内容类型无效")
        defaults = AUTOMATION_DEFAULTS[content_kind]
        repo = self._config_repository()
        return {
            "cluster_hours": positive_int(repo.get_config(automation_key(content_kind, AUTOMATION_FIELD_MAP["cluster_hours"])), defaults["cluster_hours"]),
            "cluster_window_hours": positive_int(repo.get_config(automation_key(content_kind, AUTOMATION_FIELD_MAP["cluster_window_hours"])), defaults["cluster_window_hours"]),
            "filter_hours": positive_int(repo.get_config(automation_key(content_kind, AUTOMATION_FIELD_MAP["filter_hours"])), defaults["filter_hours"]),
            "ai_scoring_hours": positive_int(repo.get_config(automation_key(content_kind, AUTOMATION_FIELD_MAP["ai_scoring_hours"])), defaults["ai_scoring_hours"]),
            "push_hours": positive_int(repo.get_config(automation_key(content_kind, AUTOMATION_FIELD_MAP["push_hours"])), defaults["push_hours"]),
        }

    def set_config(self, config: dict) -> dict:
        with self._transaction() as repos:
            repo = repos.config
            runtime = config.get("runtime") or {}
            for key in RUNTIME_DEFAULTS:
                if key in runtime and runtime[key] is not None:
                    value = str(runtime[key]).lower() if key == "enabled" else str(runtime[key])
                    repo.set_config(f"automation.runtime.{key}", value)
            for content_kind, values in config.items():
                if content_kind not in CONTENT_KINDS or not values:
                    continue
                for key, value in values.items():
                    field = AUTOMATION_FIELD_MAP.get(key)
                    if field and value is not None:
                        repo.set_config(automation_key(content_kind, field), str(value))
        return {"status": "success", "message": "配置已保存"}

    def get_event_cluster_threshold(self) -> float:
        try:
            return float(self._config_repository().get_config(EVENT_CLUSTER_THRESHOLD_KEY) or 0.50)
        except Exception:
            return 0.50

    def set_event_cluster_threshold(self, threshold: float) -> None:
        self._config_repository().set_config(EVENT_CLUSTER_THRESHOLD_KEY, str(threshold))
