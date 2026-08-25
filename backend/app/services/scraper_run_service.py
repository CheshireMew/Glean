from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from logging import getLogger
from typing import Dict
import uuid

from ..core.task_output import capture_task_output

logger = getLogger("uvicorn")


class ScraperRunService:
    WRITE_BATCH_SIZE = 20

    def __init__(
        self,
        news_repository,
        news_runtime_repository,
        scraper_state_repository,
        runtime_state,
        automation_settings,
    ):
        self._news_repository = news_repository
        self._news_runtime_repository = news_runtime_repository
        self._scraper_state_repository = scraper_state_repository
        self._runtime_state = runtime_state
        self._automation_settings = automation_settings
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._completed_failures: Dict[str, str] = {}
        self.worker_id: str | None = None

    def configure_worker(self, worker_id: str) -> None:
        self.worker_id = worker_id

    def is_running(self, name: str) -> bool:
        task = self._running_tasks.get(name)
        return bool(task and not task.done())

    def concurrency_limit(self) -> int:
        return int(self._automation_settings.get_runtime()["scraper_concurrency"])

    def available_launch_slots(self) -> int:
        active = sum(not task.done() for task in self._running_tasks.values())
        return max(self.concurrency_limit() - active, 0)

    def launch_scraper(self, name: str, items: int) -> bool:
        if not self.worker_id:
            raise RuntimeError("scraper run service 尚未绑定 worker")
        self._runtime_state.ensure_runtime_initialized()
        self._runtime_state.require_scraper(name)
        if self.is_running(name):
            return False
        if self.available_launch_slots() <= 0:
            return False
        self._completed_failures.pop(name, None)
        run_id = uuid.uuid4().hex
        if not self._scraper_state_repository().claim_run(name, run_id, self.worker_id):
            return False
        self._running_tasks[name] = asyncio.create_task(self.run_scraper_task(name, items, run_id))
        return True

    def cancel_running_scraper(self, name: str) -> bool:
        task = self._running_tasks.get(name)
        if not task or task.done():
            return False
        task.cancel()
        return True

    async def run_scraper_task(self, name: str, max_items: int, run_id: str) -> None:
        logger.info("Starting scrape task name=%s run_id=%s", name, run_id)
        pending_logs: list[str] = []
        pending_news: list[dict] = []
        observed_urls: set[str] = set()
        saved_count = 0
        warning_count = [0]
        heartbeat_task = asyncio.create_task(self._heartbeat_run(name, run_id, pending_logs))
        scrape_task: asyncio.Task | None = None
        try:
            definition = self._runtime_state.require_scraper(name)
            scraper = definition.build_scraper()
            scraper.max_items = max_items
            self._runtime_state.append_log(name, f"Initialized scraper with limit {max_items}")

            recent_urls = self._news_runtime_repository().get_recent_news_urls(scraper.site_name, limit=2000)
            if recent_urls:
                scraper.existing_urls = set(recent_urls)
                scraper.last_news_url = recent_urls[0]
                scraper.incremental_mode = True
            else:
                latest_url = self._news_runtime_repository().get_latest_news_url(scraper.site_name)
                if latest_url:
                    scraper.last_news_url = latest_url
                    scraper.incremental_mode = True

            def persist_item(news):
                nonlocal saved_count
                if "source_site" not in news:
                    news["source_site"] = scraper.site_name
                source_url = news.get("url")
                if source_url:
                    observed_urls.add(source_url)
                pending_news.append(news)
                if len(pending_news) >= self.WRITE_BATCH_SIZE:
                    saved_count += self._flush_news(pending_news)

            scraper.item_callback = persist_item
            self._runtime_state.append_log(name, "Starting scrape...")
            with capture_task_output(
                lambda line: self._capture_log(name, run_id, pending_logs, warning_count, line)
            ):
                scrape_task = asyncio.create_task(scraper.run(), name=f"scrape:{name}:{run_id}")
                done, _ = await asyncio.wait(
                    {scrape_task, heartbeat_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if heartbeat_task in done:
                    if not scrape_task.done():
                        scrape_task.cancel()
                        await asyncio.gather(scrape_task, return_exceptions=True)
                    heartbeat_error = heartbeat_task.exception()
                    if heartbeat_error is not None:
                        raise heartbeat_error
                    raise RuntimeError(f"采集任务 {name} 的心跳意外结束")
                news_list = await scrape_task
            for news in news_list:
                if news.get("url") not in observed_urls:
                    persist_item(news)
            saved_count += self._flush_news(pending_news)

            self._flush_logs(name, pending_logs)
            self._scraper_state_repository().finish_run(
                name,
                run_id,
                {
                    "status": "idle",
                    "last_run": datetime.now(timezone.utc).isoformat(),
                    "last_result": (
                        f"Scraped {len(news_list)}, Saved {saved_count}, Warnings {warning_count[0]}"
                    ),
                    "last_error": None,
                    "items_scraped": len(news_list),
                },
            )
        except asyncio.CancelledError:
            self._flush_logs(name, pending_logs)
            self._scraper_state_repository().finish_run(
                name,
                run_id,
                {"status": "idle", "last_run": datetime.now(timezone.utc).isoformat(), "last_result": "Cancelled by user"},
            )
            raise
        except Exception as exc:
            logger.exception("Scrape task failed name=%s run_id=%s", name, run_id)
            self._completed_failures[name] = str(exc)
            pending_logs.append(f"ERROR: {exc}")
            self._flush_logs(name, pending_logs)
            self._scraper_state_repository().finish_run(
                name,
                run_id,
                {
                    "status": "error",
                    "last_run": datetime.now(timezone.utc).isoformat(),
                    "last_result": "Failed",
                    "last_error": str(exc),
                },
            )
        finally:
            if pending_news:
                try:
                    saved_count += self._flush_news(pending_news)
                except Exception:
                    logger.exception("Failed to flush final scrape batch name=%s run_id=%s", name, run_id)
            if scrape_task and not scrape_task.done():
                scrape_task.cancel()
                await asyncio.gather(scrape_task, return_exceptions=True)
            heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)
            self._running_tasks.pop(name, None)

    def _flush_news(self, pending_news: list[dict]) -> int:
        if not pending_news:
            return 0
        batch = pending_news[:]
        repository = self._news_repository()
        insert_batch = getattr(repository, "insert_news_batch", None)
        if insert_batch:
            inserted = int(insert_batch(batch))
        else:
            inserted = sum(1 for news in batch if repository.insert_news(news))
        del pending_news[: len(batch)]
        return inserted

    def _capture_log(
        self, name: str, run_id: str, pending_logs: list[str], warning_count: list[int], line: str
    ) -> None:
        logger.info("scraper_output name=%s run_id=%s message=%s", name, run_id, line)
        normalized = line.lower()
        if "失败" in line or "error" in normalized or "warning" in normalized or "⚠" in line:
            warning_count[0] += 1
        pending_logs.append(line)

    def _flush_logs(self, name: str, pending_logs: list[str]) -> None:
        if not pending_logs:
            return
        batch = pending_logs[:]
        pending_logs.clear()
        self._runtime_state.append_logs(name, batch)

    async def _heartbeat_run(self, name: str, run_id: str, pending_logs: list[str]) -> None:
        while True:
            await asyncio.sleep(2)
            if not self.worker_id or not self._scraper_state_repository().heartbeat(name, run_id, self.worker_id):
                raise RuntimeError(f"采集任务 {name} 已丢失运行所有权")
            self._flush_logs(name, pending_logs)

    async def wait_for_scrapers(self, timeout: int = 300) -> None:
        import time

        start_time = time.time()
        while True:
            running_scrapers = [
                name
                for name, status in self._runtime_state.get_spider_status().items()
                if status.get("status") in {"queued", "running"}
            ]
            if not running_scrapers:
                if self._completed_failures:
                    failures = self._completed_failures.copy()
                    self._completed_failures.clear()
                    details = "；".join(f"{name}: {error}" for name, error in failures.items())
                    raise RuntimeError(f"采集任务失败: {details}")
                return
            if time.time() - start_time > timeout:
                raise TimeoutError(f"等待采集任务超时: {', '.join(running_scrapers)}")
            await asyncio.sleep(10)
