from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

import httpx

from backend.app.composition import AppServices
from backend.app.domain.ai_sources import PUBLIC_AI_SOURCES
from backend.app.infrastructure.database import database, init_database
from backend.app.infrastructure.repositories import repositories
from backend.app.infrastructure.scraper_impl.source_access import source_access
from backend.main import app


class AIRefreshTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=r"D:\Tools")
        self.original_path = database.db_path
        database.db_path = str(Path(self.folder.name) / "refresh.db")
        init_database()
        self.services = AppServices()
        self.services.scraper_runtime_state.ensure_runtime_initialized()
        repositories().runtime_leases.acquire("worker", "refresh-test", 120,
            owner_version=self.services.scraper_commands._expected_worker_version, runtime_status="ready")

    async def asyncTearDown(self):
        database.db_path = self.original_path
        self.folder.cleanup()

    def commands(self):
        return [dict(row) for row in repositories().scraper_commands.execute("SELECT * FROM scraper_runtime_commands").fetchall()]

    async def test_public_reads_status_without_enqueuing_and_refresh_requires_admin(self):
        self.assertFalse(self.services.automation_settings.get_runtime()["enabled"])
        self.services.scraper_runtime_state.update_scraper_config("lobsters", "manual", None)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            await client.get("/api/public/ai/content")
            self.assertEqual(self.commands(), [])
            response = await client.post("/api/public/ai/refresh")
            self.assertEqual(response.status_code, 401)
            status = await client.get('/api/public/ai/status')
            self.assertEqual(status.status_code, 200)
            self.assertEqual(self.commands(), [])
        await AppServices().ai_refresh.refresh()
        rows = self.commands()
        self.assertEqual({row["scraper_name"] for row in rows}, {source["key"] for source in PUBLIC_AI_SOURCES})
        self.assertEqual(len(rows), len(PUBLIC_AI_SOURCES))
        self.assertTrue(all('admin' in row['payload'] for row in rows))
        self.assertEqual(json.loads(next(row['payload'] for row in rows if row['scraper_name'] == 'hacker_news'))['items'], 30)

    async def test_completed_and_failed_attempts_are_cached_even_after_restart(self):
        await self.services.ai_refresh.refresh()
        for row in self.commands():
            repositories().scraper_commands.complete_command(row["id"], "test finished")
            self.services.scraper_runtime_state.set_scraper_state(row["scraper_name"],
                {"status": "error" if row["scraper_name"] == "lobsters" else "idle", "last_error": "模拟失败" if row["scraper_name"] == "lobsters" else None})
        result = await AppServices().ai_refresh.refresh()
        self.assertFalse(result["updating"])
        self.assertEqual(next(s for s in result["sources"] if s["key"] == "lobsters")["status"], "error")
        self.assertEqual(len(self.commands()), len(PUBLIC_AI_SOURCES))
        old = (datetime.now(timezone.utc) - timedelta(minutes=31)).isoformat()
        for source in PUBLIC_AI_SOURCES:
            repositories().config.set_config(f"ai.refresh.{source['key']}", old)
        self.assertTrue((await self.services.ai_refresh.refresh())["updating"])
        self.assertEqual(len(self.commands()), 2 * len(PUBLIC_AI_SOURCES))

    async def test_cooldown_disabled_sources_and_offline_worker_are_reported(self):
        source_access.defer("https://lobste.rs/recent", "HTTP 429")
        self.services.source_operations.sync_catalog()
        self.services.source_operations.update_source("hacker_news", {"enabled": False})
        result = await self.services.ai_refresh.refresh()
        statuses = {row["key"]: row for row in result["sources"]}
        self.assertEqual(statuses["lobsters"]["status"], "paused")
        self.assertIn("HTTP 429", statuses["lobsters"]["message"])
        self.assertEqual(len(self.commands()), len(PUBLIC_AI_SOURCES) - 2)
        repositories().runtime_leases.update_status("worker", "refresh-test", "stopped")
        self.assertIn("暂未运行", (await self.services.ai_refresh.refresh())["message"])
        self.assertEqual(len(self.commands()), len(PUBLIC_AI_SOURCES) - 2)

    async def test_concurrent_tabs_enqueue_each_source_only_once(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: asyncio.run(AppServices().ai_refresh.refresh()), range(2)))
        self.assertTrue(all(row["updating"] for row in results))
        self.assertEqual(len(self.commands()), len(PUBLIC_AI_SOURCES))

    async def test_disabled_wechat_is_hidden_but_its_subscription_is_preserved(self):
        account = repositories().wechat.add_source({"fake_id": "test", "name": "失败的公众号"})
        repositories().wechat.update_source(account["id"], False, 10, 240)
        result = self.services.ai_content.get_content(None, "", 20, 0)
        self.assertTrue(all(not source["key"].startswith("wechat__") for source in result["sources"]))
        self.assertIsNotNone(repositories().wechat.get_source(account["id"]))
