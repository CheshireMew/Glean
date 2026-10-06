from __future__ import annotations

import asyncio
import io
import logging
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from backend.app.composition import app_services
from backend.app.core.exceptions import ConflictError
from backend.app.core.exceptions import ConfigurationError
from backend.app.core.config import settings
from backend.app.infrastructure.scraper_impl.source_access import source_access
from backend.app.infrastructure.database import database, db_connection, init_database
from backend.app.infrastructure.repositories import repositories
from backend.app.infrastructure.scraper_impl.base import BaseScraper, CANDIDATE_ACCEPT, CANDIDATE_SKIP
from backend.app.infrastructure.scraper_impl.blockbeats import BlockBeatsScraper
from backend.app.models.responses import ScraperConfigData, ScraperRuntimeData
from backend.app.services.scraper_run_service import ScraperRunService
from backend.app.services.scraper_schedule_service import ScraperScheduleService


class ScraperAutomationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=r"D:\Tools")
        self.previous_path = database.db_path
        database.db_path = str(Path(self.temp.name) / "scraper-tests.db")
        init_database()
        self.runtime = app_services.scraper_runtime_state
        self.runtime.ensure_runtime_initialized()
        self.runs = ScraperRunService(
            lambda: repositories().news, lambda: repositories().news_runtime,
            lambda: repositories().scraper_state, self.runtime,
            app_services.automation_settings, source_operations=app_services.source_operations,
        )
        self.runs.configure_worker("automation-test")

    async def asyncTearDown(self):
        tasks = list(self.runs._running_tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(0)
        database.db_path = self.previous_path
        self.temp.cleanup()

    def test_new_install_is_off_and_explicit_enable_survives_reinitialization(self):
        self.assertFalse(app_services.automation_runtime.is_working_hours())
        launcher = Mock()
        scheduler = self.scheduler(launcher)
        scheduler.run_due_scrapers(app_services.automation_runtime.is_working_hours)
        launcher.launch_scraper.assert_not_called()
        app_services.automation_settings.set_config({"runtime": {"enabled": True}})
        init_database()
        self.assertTrue(app_services.automation_settings.get_runtime()["enabled"])
        app_services.automation_settings.set_config({"runtime": {"enabled": False}})
        self.assertFalse(app_services.automation_runtime.is_working_hours())

    def test_manual_mode_round_trip_including_legacy_and_invalid_values(self):
        for raw in ('', '{"limit": 5}', '{"interval": null}', 'broken', '[]', '{"interval": "60"}', '{"interval": -1}'):
            repositories().config.set_config("scraper.odaily.runtime", raw)
            self.runtime.ensure_runtime_initialized()
            self.assertIsNone(self.runtime.get_scraper_config("odaily")["interval"], raw)
        saved = self.runtime.update_scraper_config("odaily", "manual", None)
        ScraperConfigData.model_validate(saved)
        self.runtime.ensure_runtime_initialized()
        self.assertIsNone(self.runtime.get_spider_status()["odaily"]["interval"])
        self.runtime.update_scraper_config("odaily", None, 10)
        self.assertIsNone(self.runtime.get_scraper_config("odaily")["interval"])
        self.runtime.update_scraper_config("odaily", "60", None)
        self.assertEqual(self.runtime.get_scraper_config("odaily")["interval"], 60)

    def scheduler(self, launcher, names=("odaily",)):
        registry = SimpleNamespace(names=lambda: list(names), get=lambda name: self.runtime.require_scraper(name))
        return ScraperScheduleService(
            lambda: repositories().scraper_commands, registry, launcher,
            self.runtime, SimpleNamespace(is_active=lambda _: False), app_services.source_operations,
        )

    def test_schedule_respects_interval_manual_disabled_and_pending_commands(self):
        launcher = Mock()
        launcher.available_launch_slots.return_value = 2
        scheduler = self.scheduler(launcher)
        now = datetime.now(timezone.utc)
        self.runtime.set_scraper_state("odaily", {"last_run": (now - timedelta(minutes=59)).isoformat()})
        scheduler.run_due_scrapers(lambda: True, now)
        launcher.launch_scraper.assert_not_called()
        scheduler.run_due_scrapers(lambda: True, now + timedelta(minutes=1))
        self.assertEqual(launcher.launch_scraper.call_count, 1)
        self.assertTrue(launcher.launch_scraper.call_args.kwargs["should_continue"]())
        launcher.reset_mock()
        self.runtime.update_scraper_config("odaily", "manual", None)
        scheduler.run_due_scrapers(lambda: True, now + timedelta(hours=2))
        launcher.launch_scraper.assert_not_called()
        self.runtime.update_scraper_config("odaily", "60", None)
        app_services.source_operations.sync_catalog()
        app_services.source_operations.update_source("odaily", {"enabled": False})
        scheduler.run_due_scrapers(lambda: True, now + timedelta(hours=2))
        launcher.launch_scraper.assert_not_called()
        app_services.source_operations.update_source("odaily", {"enabled": True})
        repositories().scraper_commands.enqueue_command("odaily", "run", {"items": 5})
        scheduler.run_due_scrapers(lambda: True, now + timedelta(hours=2))
        launcher.launch_scraper.assert_not_called()

    def test_corrupt_source_timestamp_does_not_block_other_sources(self):
        launcher = Mock()
        launcher.available_launch_slots.return_value = 2
        self.runtime.set_scraper_state("techflow", {"last_run": "invalid"})
        self.scheduler(launcher, ("techflow", "odaily")).run_due_scrapers(lambda: True)
        self.assertEqual(launcher.launch_scraper.call_args.args[0], "odaily")

    def test_ai_sources_use_admin_schedule_and_respect_manual_mode(self):
        launcher = Mock()
        launcher.available_launch_slots.return_value = 2
        names = ("hacker_news", "lobsters", "rss__hn-chinese-digest", "rss__v2ex-main", "rss__acquired-video", "rss__baochipianjian", "odaily")
        scheduler = self.scheduler(launcher, names)
        scheduler.run_due_scrapers(lambda: True)
        self.assertEqual([call.args[0] for call in launcher.launch_scraper.call_args_list], [name for name in names if name != 'rss__acquired-video'])
        launcher.reset_mock()
        scheduler.run_due_scrapers(lambda: False)
        launcher.launch_scraper.assert_not_called()
        self.runtime.update_scraper_config('hacker_news', 'manual', None)
        scheduler.run_due_scrapers(lambda: True)
        self.assertNotIn('hacker_news', [call.args[0] for call in launcher.launch_scraper.call_args_list])

    async def test_cooldown_blocks_scheduler_manual_queue_and_direct_launch(self):
        scraper = self.runtime.require_scraper("odaily").build_scraper()
        error = source_access.defer(scraper.base_url, "HTTP 429", "7200")
        launcher = Mock()
        launcher.available_launch_slots.return_value = 2
        self.scheduler(launcher).run_due_scrapers(lambda: True)
        launcher.launch_scraper.assert_not_called()
        self.assertFalse(self.runs.launch_scraper("odaily", 5))
        commands = app_services.scraper_commands
        repositories().runtime_leases.acquire("worker", "cooldown-test", 60,
            owner_version=commands._expected_worker_version, runtime_status="ready")
        with self.assertRaisesRegex(ConflictError, "HTTP 429"):
            await commands.request_run("odaily", 5)
        self.assertFalse(repositories().scraper_commands.has_pending_command("odaily", "run"))
        status = self.runtime.get_spider_status()["odaily"]
        status = ScraperRuntimeData.model_validate(status).model_dump()
        self.assertEqual(status["cooldown_until"], error.until)
        self.assertIn("HTTP 429", status["cooldown_reason"])

    async def test_missing_media_key_blocks_api_mode_but_not_http_articles(self):
        commands = app_services.scraper_commands
        repositories().runtime_leases.acquire("worker", "media-key-test", 60,
            owner_version=commands._expected_worker_version, runtime_status="ready")
        with patch.object(BlockBeatsScraper, 'transport_kind', 'api'), patch.object(settings, 'BLOCKBEATS_API_KEY', ''):
            status = ScraperRuntimeData.model_validate(self.runtime.get_spider_status()['blockbeats']).model_dump()
            self.assertIn('BLOCKBEATS_API_KEY', status['configuration_error'])
            self.assertIsNone(self.runtime.get_spider_status()['blockbeats_article']['configuration_error'])
            launcher = Mock()
            launcher.available_launch_slots.return_value = 2
            self.scheduler(launcher, ('blockbeats', 'blockbeats_article')).run_due_scrapers(lambda: True)
            self.assertEqual([call.args[0] for call in launcher.launch_scraper.call_args_list], ['blockbeats_article'])
            with self.assertRaisesRegex(ConfigurationError, 'BLOCKBEATS_API_KEY'):
                await commands.request_run('blockbeats', 5)
            with self.assertRaisesRegex(ConfigurationError, 'BLOCKBEATS_API_KEY'):
                self.runs.launch_scraper('blockbeats', 5)
            self.assertFalse(repositories().scraper_commands.has_pending_command('blockbeats', 'run'))
            self.assertEqual(self.runtime.get_scraper_state('blockbeats')['status'], 'idle')
        with patch.object(settings, 'BLOCKBEATS_API_KEY', 'test-only-key'):
            self.assertIsNone(self.runtime.get_spider_status()['blockbeats']['configuration_error'])
            accepted = await commands.request_run('blockbeats', 5)
            self.assertEqual(accepted['status'], 'accepted')

    async def test_blockbeats_http_without_key_is_ready_for_scheduler_and_manual_queue(self):
        commands = app_services.scraper_commands
        repositories().runtime_leases.acquire('worker', 'media-http-test', 60,
            owner_version=commands._expected_worker_version, runtime_status='ready')
        with patch.object(BlockBeatsScraper, 'transport_kind', 'http'), patch.object(settings, 'BLOCKBEATS_API_KEY', ''):
            self.assertIsNone(self.runtime.get_spider_status()['blockbeats']['configuration_error'])
            launcher = Mock()
            launcher.available_launch_slots.return_value = 2
            self.scheduler(launcher, ('blockbeats', 'blockbeats_article')).run_due_scrapers(lambda: True)
            self.assertEqual([call.args[0] for call in launcher.launch_scraper.call_args_list], ['blockbeats', 'blockbeats_article'])
            self.assertEqual((await commands.request_run('blockbeats', 5))['status'], 'accepted')

    def fake_scraper(self):
        started, finish, closed = asyncio.Event(), asyncio.Event(), asyncio.Event()

        class Scraper:
            site_name = "test-source"

            async def run(inner):
                try:
                    inner.item_callback({"title": "Buffered item", "content": "Body", "url": "https://example.test/one", "published_at": "2026-09-27 00:00:00"})
                    started.set()
                    await finish.wait()
                    return []
                finally:
                    closed.set()

        scraper = Scraper()
        return scraper, started, finish, closed

    def row_count(self):
        with database.connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM news").fetchone()[0]

    async def test_auto_stop_cancels_network_before_idle_and_does_not_flush_buffer(self):
        scraper, started, _, closed = self.fake_scraper()
        app_services.automation_settings.set_config({"runtime": {"enabled": True}})
        scheduler = self.scheduler(self.runs)
        with patch.object(self.runtime, "require_scraper", return_value=SimpleNamespace(build_scraper=lambda: scraper)):
            self.assertTrue(self.runs.launch_scraper("odaily", 30, should_continue=lambda: scheduler.can_collect(
                "odaily", lambda: app_services.automation_settings.get_runtime()["enabled"])))
            await asyncio.wait_for(started.wait(), 1)
            task = self.runs._running_tasks["odaily"]
            for index in range(20):
                scraper.item_callback({"title": "Collected", "url": f"https://example.test/{index}", "published_at": "2026-09-27 00:00:00"})
            self.assertEqual(self.row_count(), 20)
            app_services.automation_settings.set_config({"runtime": {"enabled": False}})
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, 3)
        self.assertTrue(closed.is_set())
        state = repositories().scraper_state.get_state("odaily")
        self.assertEqual(state["status"], "idle")
        self.assertIn("自动采集已关闭", state["last_result"])
        self.assertEqual(self.row_count(), 20)
        self.assertEqual(state["items_scraped"], 20)
        self.assertFalse(self.runs.is_running("odaily"))

    async def test_manual_run_still_works_with_auto_off_and_duplicates_insert_once(self):
        scraper, started, finish, _ = self.fake_scraper()
        with patch.object(self.runtime, "require_scraper", return_value=SimpleNamespace(build_scraper=lambda: scraper)):
            self.assertFalse(app_services.automation_settings.get_runtime()["enabled"])
            self.assertTrue(self.runs.launch_scraper("odaily", 5))
            await started.wait()
            task = self.runs._running_tasks["odaily"]
            scraper.item_callback({"title": "Duplicate", "url": "https://example.test/one", "published_at": "2026-09-27 00:00:00"})
            finish.set()
            await task
        self.assertEqual(self.row_count(), 1)
        state = repositories().scraper_state.get_state("odaily")
        self.assertIn("Saved 1", state["last_result"])
        self.assertTrue(any("手动采集" in line for line in state["logs"]))

    async def test_media_rss_and_api_run_through_worker_persistence_and_incremental_history(self):
        for name in ('odaily', 'panews'):
            with self.subTest(source=name):
                definition = self.runtime.require_scraper(name)
                url = f'https://example.test/{name}/1'
                created = []

                def build_scraper():
                    scraper = definition.build_scraper()
                    scraper.transport.start = AsyncMock()
                    scraper.transport.close = AsyncMock()
                    scraper.transport.fetch_json = AsyncMock(return_value={
                        'code': 200, 'success': True, 'data': {'hasMore': False, 'list': [{
                            'title': '真实快讯', 'content': '<p>真实正文</p>', 'link': url,
                            'isImportant': True, 'publishTimestamp': 1791191803000,
                        }]}})
                    scraper.transport.fetch_text = AsyncMock(return_value=(
                        '<rss version="2.0"><channel><item><title>真实快讯</title>'
                        f'<link>{url}</link><description><![CDATA[<p>真实正文</p>]]></description>'
                        '<pubDate>Mon, 05 Oct 2026 09:16:43 GMT</pubDate></item></channel></rss>'
                    ))
                    created.append(scraper)
                    return scraper

                with patch.object(self.runtime, 'require_scraper', return_value=SimpleNamespace(build_scraper=build_scraper)):
                    for expected_count in (1, 0):
                        self.assertTrue(self.runs.launch_scraper(name, 1))
                        await self.runs._running_tasks[name]
                        state = repositories().scraper_state.get_state(name)
                        self.assertEqual(state['status'], 'idle')
                        self.assertEqual(state['items_scraped'], expected_count)
                        created[-1].transport.start.assert_awaited_once()
                        created[-1].transport.close.assert_awaited_once()
                with db_connection() as conn:
                    stored = [tuple(row) for row in conn.execute(
                        'SELECT source_site, type, content, published_at, is_marked_important FROM news WHERE source_url = ?',
                        (url,),
                    ).fetchall()]
                self.assertEqual(stored, [(name, 'news', '真实正文', '2026-10-05 09:16:43', 1)])
                self.assertTrue(created[-1].encountered_existing_items)

    async def test_stop_before_coroutine_starts_releases_claim(self):
        scraper, started, _, _ = self.fake_scraper()
        with patch.object(self.runtime, "require_scraper", return_value=SimpleNamespace(build_scraper=lambda: scraper)):
            self.assertTrue(self.runs.launch_scraper("odaily", 5, should_continue=lambda: True))
            task = self.runs._running_tasks["odaily"]
            self.assertTrue(self.runs.cancel_running_scraper("odaily"))
            await asyncio.gather(task, return_exceptions=True)
            await asyncio.sleep(0)
        self.assertFalse(started.is_set())
        self.assertEqual(repositories().scraper_state.get_state("odaily")["status"], "idle")
        self.assertEqual(self.runs._continuation_checks, {})

    async def test_failed_persistence_is_not_retried_in_finally_or_reported_success(self):
        scraper, started, finish, _ = self.fake_scraper()
        news_repo = Mock()
        news_repo.insert_news_batch.side_effect = RuntimeError("disk full")
        self.runs._news_repository = lambda: news_repo
        with patch.object(self.runtime, "require_scraper", return_value=SimpleNamespace(build_scraper=lambda: scraper)):
            self.runs.launch_scraper("odaily", 5)
            await started.wait()
            task = self.runs._running_tasks["odaily"]
            finish.set()
            await task
        state = repositories().scraper_state.get_state("odaily")
        self.assertEqual(state["status"], "error")
        self.assertIn("disk full", state["last_error"])
        self.assertEqual(news_repo.insert_news_batch.call_count, 1)

    async def test_disabled_source_rejects_manual_launch(self):
        app_services.source_operations.sync_catalog()
        app_services.source_operations.update_source("odaily", {"enabled": False})
        self.assertFalse(self.runs.launch_scraper("odaily", 5))
        self.assertEqual(self.row_count(), 0)

    async def test_switching_to_manual_stops_automatic_run(self):
        scraper, started, _, closed = self.fake_scraper()
        scheduler = self.scheduler(self.runs)
        with patch.object(self.runtime, "require_scraper", return_value=SimpleNamespace(build_scraper=lambda: scraper)):
            self.runs.launch_scraper("odaily", 5, should_continue=lambda: scheduler.can_collect("odaily", lambda: True))
            await started.wait()
            task = self.runs._running_tasks["odaily"]
            self.runtime.update_scraper_config("odaily", "manual", None)
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, 3)
        self.assertTrue(closed.is_set())
        self.assertEqual(self.row_count(), 0)

    async def test_disabled_queued_source_is_not_left_in_queued_state(self):
        app_services.source_operations.sync_catalog()
        command_id = repositories().scraper_commands.enqueue_command("odaily", "run", {"items": 5})
        self.runtime.set_scraper_state("odaily", {"status": "queued"})
        app_services.source_operations.update_source("odaily", {"enabled": False})
        command = repositories().scraper_commands.get_command(command_id)
        with patch.object(app_services.scraper_commands, "_scraper_runs", self.runs):
            await app_services.scraper_commands._handle_command(command)
        self.assertEqual(repositories().scraper_commands.get_command(command_id)["status"], "failed")
        self.assertEqual(repositories().scraper_state.get_state("odaily")["status"], "idle")


class TaskOutputTest(unittest.TestCase):
    def test_sink_logging_does_not_capture_itself_or_leak_context(self):
        from backend.app.core.task_output import _ContextOutput, capture_task_output
        original = io.StringIO()
        captured = []
        logger = logging.Logger("task-output-test")
        with patch.object(sys, "stderr", _ContextOutput(original)), patch.object(sys, "stdout", _ContextOutput(io.StringIO())):
            logger.addHandler(logging.StreamHandler(sys.stderr))

            def sink(line):
                captured.append(line)
                logger.warning("captured: %s", line)

            with capture_task_output(sink):
                logger.warning("source output")
                sys.stderr.write("trailing")
            logger.warning("outside")
        self.assertEqual(captured, ["source output", "trailing"])
        self.assertLess(len(original.getvalue()), 200)


class IncrementalCollectionTest(unittest.IsolatedAsyncioTestCase):
    async def test_existing_items_do_not_consume_new_item_limit_or_raise_false_error(self):
        class Scraper(BaseScraper):
            async def scrape_important_news(self):
                collector = self.create_candidate_collector()
                self.outcomes = [collector.consider("old", "https://example.test/old")]
                return collector.results

        class Transport:
            async def start(self, owner):
                pass

            async def close(self, owner):
                pass

        scraper = Scraper("test", "https://example.test", max_items=1)
        scraper.transport = Transport()
        scraper.last_news_url = "https://example.test/old"
        scraper.existing_urls = {scraper.last_news_url}
        self.assertEqual(await scraper.run(), [])
        self.assertEqual(scraper.outcomes, [CANDIDATE_SKIP])
        collector = scraper.create_candidate_collector()
        self.assertEqual(collector.consider("old", scraper.last_news_url), CANDIDATE_SKIP)
        self.assertEqual(collector.consider("new", "https://example.test/new"), CANDIDATE_ACCEPT)

    async def test_empty_parser_without_known_items_still_reports_failure(self):
        class Scraper(BaseScraper):
            async def scrape_important_news(self):
                return []

        transport = SimpleNamespace(start=Mock(), close=Mock())
        from unittest.mock import AsyncMock
        transport.start = AsyncMock()
        transport.close = AsyncMock()
        scraper = Scraper("test", "https://example.test")
        scraper.transport = transport
        with self.assertRaisesRegex(RuntimeError, "没有解析出任何内容"):
            await scraper.run()
