from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
from logging import getLogger

logger = getLogger("ainews.maintenance")


class DataMaintenanceService:
    BATCH_SIZE = 500

    def __init__(self, automation_settings, config_repository, maintenance_repository, operation_leases):
        self._automation_settings = automation_settings
        self._config_repository = config_repository
        self._maintenance_repository = maintenance_repository
        self._operation_leases = operation_leases

    def _is_due(self, interval_hours: int) -> bool:
        raw = self._config_repository().get_config("maintenance.last_run_at")
        if not raw:
            return True
        try:
            last_run = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if last_run.tzinfo is None:
                last_run = last_run.replace(tzinfo=timezone.utc)
        except ValueError:
            return True
        return datetime.now(timezone.utc) - last_run >= timedelta(hours=interval_hours)

    @staticmethod
    def _cutoff(days: int) -> str:
        return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

    def _drain(self, method, *args) -> dict[str, int]:
        totals: dict[str, int] = {}
        while True:
            result = method(*args, self.BATCH_SIZE)
            values = result if isinstance(result, dict) else {"events": int(result)}
            for key, value in values.items():
                totals[key] = totals.get(key, 0) + int(value)
            if all(int(value) < self.BATCH_SIZE for value in values.values()):
                return totals

    def _run(self, runtime: dict) -> dict:
        repository = self._maintenance_repository()
        operational = self._drain(
            repository.prune_operational_batch,
            self._cutoff(runtime["operational_retention_days"]),
        )
        events = self._drain(
            repository.prune_event_batch,
            self._cutoff(runtime["content_retention_days"]),
        )
        content = self._drain(
            repository.prune_content_batch,
            self._cutoff(runtime["content_retention_days"]),
        )
        storage = repository.optimize_storage()
        return {"operational": operational, "events": events, "content": content, "storage": storage}

    async def run_if_due(self, *, force: bool = False) -> dict:
        runtime = self._automation_settings.get_runtime()
        if not force and not self._is_due(runtime["maintenance_interval_hours"]):
            return {"status": "not_due"}
        async with self._operation_leases.hold("content-pipeline", ttl_seconds=600):
            result = await asyncio.to_thread(self._run, runtime)
            completed_at = datetime.now(timezone.utc).isoformat()
            repo = self._config_repository()
            await asyncio.to_thread(repo.set_config, "maintenance.last_run_at", completed_at)
            await asyncio.to_thread(
                repo.set_config,
                "maintenance.last_result",
                json.dumps(result, ensure_ascii=False, separators=(",", ":")),
            )
            logger.info("Database maintenance completed result=%s", result)
            return {"status": "completed", **result}

    async def loop(self) -> None:
        await asyncio.sleep(30)
        while True:
            try:
                await self.run_if_due()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Database maintenance attempt failed; it will retry later")
            await asyncio.sleep(3600)
