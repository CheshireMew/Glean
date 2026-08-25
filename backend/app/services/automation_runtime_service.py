from __future__ import annotations

import asyncio
from logging import getLogger
import os
import sqlite3
import socket
import uuid

from backend.app.core.runtime_keys import (
    WORKER_LEASE_NAME,
    WORKER_STATUS_DEGRADED,
    WORKER_STATUS_READY,
    WORKER_STATUS_RUNNING,
    WORKER_STATUS_STARTING,
)

logger = getLogger("uvicorn")


class AutomationRuntimeService:
    WORKER_LEASE_TTL_SECONDS = 30

    def __init__(
        self,
        automation_settings,
        system_settings,
        scraper_schedule,
        pipeline_orchestrator,
        runtime_lease_repository,
        app_version: str,
        data_maintenance=None,
    ):
        self._automation_settings = automation_settings
        self._system_settings = system_settings
        self._scraper_schedule = scraper_schedule
        self._pipeline_orchestrator = pipeline_orchestrator
        self._runtime_lease_repository = runtime_lease_repository
        self._data_maintenance = data_maintenance
        self._app_version = app_version
        self._runtime_status = WORKER_STATUS_STARTING
        self._status_details: str | None = None
        self.instance_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"

    def is_working_hours(self) -> bool:
        schedule = self._automation_settings.get_runtime()
        if not schedule["enabled"]:
            return False
        now = self._system_settings.get_system_time()
        current = now.hour * 60 + now.minute
        start_hour, start_minute = map(int, schedule["start_time"].split(":"))
        end_hour, end_minute = map(int, schedule["end_time"].split(":"))
        start = start_hour * 60 + start_minute
        end = end_hour * 60 + end_minute
        if start <= end:
            return start <= current <= end
        return current >= start or current <= end

    def _seconds_to_next_cycle(self) -> int:
        interval = max(5, self._automation_settings.get_runtime()["interval_minutes"])
        now = self._system_settings.get_system_time()
        elapsed_minutes = now.hour * 60 + now.minute
        next_minute = ((elapsed_minutes // interval) + 1) * interval
        delta_minutes = next_minute - elapsed_minutes
        return max(30, delta_minutes * 60 - now.second)

    def _seconds_after_pipeline(self, result: dict | None) -> int:
        if result and (
            result.get("backlog_pending")
            or result.get("backlog_unknown")
            or result.get("failures")
        ):
            return self._automation_settings.get_runtime()["backlog_retry_seconds"]
        return self._seconds_to_next_cycle()

    async def scheduler_loop(self):
        await self._scraper_schedule.scheduler_loop(self.is_working_hours)

    async def maintenance_loop(self):
        if self._data_maintenance is None:
            return
        await self._data_maintenance.loop()

    async def auto_pipeline_loop(self):
        logger.info("[Auto-Pipeline] Automated pipeline system started")
        await asyncio.sleep(10)
        while True:
            result = None
            try:
                if not self.is_working_hours():
                    await asyncio.sleep(min(300, self._seconds_to_next_cycle()))
                    continue
                await self.set_worker_status(WORKER_STATUS_RUNNING)
                result = await self._pipeline_orchestrator.run_automation_cycle()
                if result.get("failures"):
                    await self.set_worker_status(
                        WORKER_STATUS_DEGRADED,
                        self._format_failure_details(result["failures"]),
                    )
                else:
                    await self.set_worker_status(WORKER_STATUS_READY)
            except Exception as exc:
                logger.error(f"[Auto-Pipeline] Error in pipeline: {exc}", exc_info=True)
                await self.set_worker_status(WORKER_STATUS_DEGRADED, str(exc))
            await asyncio.sleep(self._seconds_after_pipeline(result))

    async def heartbeat_loop(self):
        logger.info("Worker heartbeat started for %s", self.instance_id)
        while True:
            try:
                renewed = await asyncio.to_thread(
                    self._runtime_lease_repository().renew,
                    WORKER_LEASE_NAME,
                    self.instance_id,
                    self.WORKER_LEASE_TTL_SECONDS,
                    owner_version=self._app_version,
                    runtime_status=self._runtime_status,
                    status_details=self._status_details,
                )
            except Exception as exc:
                if self._is_transient_database_lock(exc):
                    logger.warning("Worker heartbeat delayed by SQLite writer lock")
                    await asyncio.sleep(1)
                    continue
                raise
            if not renewed:
                raise RuntimeError("worker 运行租约已丢失，进程必须退出以避免重复调度")
            await asyncio.sleep(10)

    @staticmethod
    def _is_transient_database_lock(exc: Exception) -> bool:
        return isinstance(exc, sqlite3.OperationalError) and any(
            marker in str(exc).lower() for marker in ("locked", "busy")
        )

    @staticmethod
    def _format_failure_details(failures: list[dict]) -> str:
        return "; ".join(
            f"{failure.get('stage', 'unknown')}: {failure.get('error', 'unknown error')}"
            for failure in failures
        )[:2000]

    async def set_worker_status(self, status: str, details: str | None = None) -> None:
        self._runtime_status = status
        self._status_details = details
        updated = await asyncio.to_thread(
            self._runtime_lease_repository().update_status,
            WORKER_LEASE_NAME,
            self.instance_id,
            status,
            details,
        )
        if not updated:
            raise RuntimeError("worker 运行租约已丢失，无法更新运行状态")

    async def mark_ready(self) -> None:
        await self.set_worker_status(WORKER_STATUS_READY)

    async def acquire_worker_lease(self) -> bool:
        return await asyncio.to_thread(
            self._runtime_lease_repository().acquire,
            WORKER_LEASE_NAME,
            self.instance_id,
            self.WORKER_LEASE_TTL_SECONDS,
            owner_version=self._app_version,
            runtime_status=WORKER_STATUS_STARTING,
        )

    async def release_worker_lease(self) -> None:
        await asyncio.to_thread(
            self._runtime_lease_repository().release, WORKER_LEASE_NAME, self.instance_id
        )
