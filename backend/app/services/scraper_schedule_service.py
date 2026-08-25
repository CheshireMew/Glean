from __future__ import annotations

import asyncio
import random
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
                if not is_working_hours():
                    await asyncio.sleep(1800)
                    continue

                if self._operation_leases.is_active("content-pipeline"):
                    await asyncio.sleep(60)
                    continue

                now = datetime.now(timezone.utc)
                command_repo = self._scraper_command_repository()
                names = self._scraper_registry.names()
                if self._source_operations is not None:
                    enabled = {
                        source["source_key"]
                        for source in self._source_operations.list_sources()
                        if source.get("enabled")
                    }
                    names = [name for name in names if name in enabled]
                for name in names:
                    if self._scraper_runs.available_launch_slots() <= 0:
                        break
                    config = self._runtime_state.get_scraper_config(name)
                    interval = config.get("interval")
                    if not interval:
                        continue

                    status = self._runtime_state.get_scraper_state(name)
                    if status.get("status") in {"queued", "running"} or command_repo.has_pending_command(name, "run"):
                        continue

                    last_run_str = status.get("last_run")
                    should_run = False
                    if not last_run_str:
                        should_run = True
                    else:
                        last_run = datetime.fromisoformat(last_run_str.replace("Z", "+00:00"))
                        if last_run.tzinfo is None:
                            last_run = last_run.replace(tzinfo=timezone.utc)
                        diff = (now - last_run).total_seconds() / 60
                        adjusted_interval = interval + interval * random.uniform(-0.2, 0.2)
                        if diff >= adjusted_interval:
                            should_run = True

                    if should_run:
                        definition = self._scraper_registry.get(name)
                        limit = config.get("limit", definition.default_limit if definition else 5)
                        self._scraper_runs.launch_scraper(name, limit)

                await asyncio.sleep(60)
            except Exception as exc:
                logger.error(f"Scheduler Error: {exc}", exc_info=True)
                await asyncio.sleep(60)
