from __future__ import annotations

import asyncio
from logging import getLogger

from backend.app.composition import app_services
from backend.app.core.config import settings
from backend.app.core.logging_config import configure_logging
from backend.app.infrastructure.database import assert_database_ready

logger = getLogger("ainews.worker")


async def main():
    configure_logging()
    settings.validate()
    assert_database_ready()
    runtime = app_services.automation_runtime
    if not await runtime.acquire_worker_lease():
        raise RuntimeError("已有 AINEWS worker 持有有效租约，拒绝启动第二个 worker")
    tasks = [asyncio.create_task(runtime.heartbeat_loop(), name="worker_heartbeat_loop")]
    try:
        app_services.scraper_runs.configure_worker(runtime.instance_id)
        await asyncio.to_thread(app_services.scraper_commands.prepare_worker, runtime.instance_id)
        await asyncio.to_thread(app_services.scraper_runtime_state.ensure_runtime_initialized)
        if tasks[0].done():
            await tasks[0]
        await runtime.mark_ready()
        logger.info("Database initialized worker_id=%s version=%s", runtime.instance_id, settings.APP_VERSION)
        tasks.extend([
            asyncio.create_task(app_services.scraper_commands.command_loop(), name="scraper_command_loop"),
            asyncio.create_task(runtime.scheduler_loop(), name="scheduler_loop"),
            asyncio.create_task(runtime.auto_pipeline_loop(), name="auto_pipeline_loop"),
            asyncio.create_task(runtime.maintenance_loop(), name="maintenance_loop"),
        ])
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await runtime.release_worker_lease()


if __name__ == "__main__":
    asyncio.run(main())
