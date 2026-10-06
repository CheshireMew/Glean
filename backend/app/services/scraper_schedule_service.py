from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from logging import getLogger

logger = getLogger("uvicorn")


class ScraperScheduleService:
    def __init__(
        self,
        scraper_command_repository,
        scraper_registry,
        scraper_runs,
        runtime_state,
        operation_leases,
        source_operations=None,
    ):
        self._scraper_command_repository = scraper_command_repository
        self._scraper_registry = scraper_registry
        self._scraper_runs = scraper_runs
        self._runtime_state = runtime_state
        self._operation_leases = operation_leases
        self._source_operations = source_operations

    async def scheduler_loop(self, is_working_hours) -> None:
        self._runtime_state.ensure_runtime_initialized()
        logger.info("Starting Scheduler Loop")
        while True:
            try:
                self.run_due_scrapers(is_working_hours)
            except Exception as exc:
                logger.error(f"Scheduler Error: {exc}", exc_info=True)
            # Settings are shared through SQLite with the API process. Re-read
            # them promptly instead of sleeping for 30 minutes while disabled.
            await asyncio.sleep(5)

    def can_collect(self, name: str, is_working_hours) -> bool:
        return bool(
            is_working_hours()
            and self._scraper_registry.get(name)
            and self._runtime_state.get_scraper_config(name).get("interval")
            and not self._runtime_state.get_configuration_error(name)
            and (self._source_operations is None or self._source_operations.is_source_enabled(name))
        )

    def run_due_scrapers(self, is_working_hours, now=None) -> None:
        if not is_working_hours() or self._operation_leases.is_active("content-pipeline"):
            return
        now = now or datetime.now(timezone.utc)
        command_repo = self._scraper_command_repository()
        for name in self._scraper_registry.names():
            if self._scraper_runs.available_launch_slots() <= 0 or not is_working_hours():
                break
            try:
                if not self.can_collect(name, is_working_hours):
                    continue
                if self._runtime_state.get_source_cooldown(name):
                    continue
                config = self._runtime_state.get_scraper_config(name)
                status = self._runtime_state.get_scraper_state(name)
                if status.get("status") in {"queued", "running"} or command_repo.has_pending_command(name, "run"):
                    continue
                if status.get("last_run"):
                    last_run = datetime.fromisoformat(status["last_run"].replace("Z", "+00:00"))
                    if last_run.tzinfo is None:
                        last_run = last_run.replace(tzinfo=timezone.utc)
                    if (now - last_run).total_seconds() < config["interval"] * 60:
                        continue
                self._scraper_runs.launch_scraper(
                    name, config["limit"],
                    should_continue=lambda name=name: self.can_collect(name, is_working_hours),
                )
            except Exception:
                # A broken source must not block scheduling all later sources.
                logger.exception("Could not schedule scraper %s", name)
