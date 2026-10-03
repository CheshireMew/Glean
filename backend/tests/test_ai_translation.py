from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from backend.app.composition import AppServices
from backend.app.infrastructure.database import database, init_database
from backend.app.infrastructure.repositories import repositories
from backend.app.domain.ai_sources import needs_chinese_translation
from backend.app.services.ai_translation_service import AITranslationService


class AITranslationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=r"D:\Tools")
        self.old_path = database.db_path
        database.db_path = str(Path(self.folder.name) / "translations.db")
        init_database()
        self.services = AppServices()
        self.key_patch = patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})
        self.key_patch.start()
        self.calls = []

    async def asyncTearDown(self):
        self.key_patch.stop()
        database.db_path = self.old_path
        self.folder.cleanup()

    def add(self, title, content="", site="Hacker News"):
        url = f"https://example.test/{uuid.uuid4().hex}"
        news_id = repositories().news.insert_news({"title": title, "content": content, "source_site": site,
            "url": url, "type": "article",
            "published_at": datetime.now(timezone.utc).isoformat()})
        if site == "Hacker News":
            repo = repositories().ai_content
            repo.save_hacker_news_front_page([*repo.hacker_news_front_page(), {"story_url": url, "source_url": url}])
        return news_id

    def responder(self, request):
        self.assertEqual(request.url.host, "api.deepseek.com")
        payload = json.loads(request.content)
        self.assertEqual(payload["model"], "deepseek-flash")
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        inputs = json.loads(payload["messages"][1]["content"])["items"]
        self.calls.append(inputs)
        outputs = [{"id": item["id"], **{key: f"中文译文{item['id']}" for key in item if key != "id"}} for item in reversed(inputs)]
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"items": outputs})}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 60, "completion_tokens_details": {"reasoning_tokens": 0}}})

    def translator(self, handler=None):
        return AITranslationService(lambda: repositories().ai_content, lambda: repositories().rss_sources,
            self.services.operation_leases,
            client_factory=lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler or self.responder), **kwargs))

    async def test_batches_cache_and_chinese_search_preserve_originals(self):
        ids = [self.add(f"English news headline {i}", "This is existing source text. " * 80 if i == 0 else "") for i in range(12)]
        self.add("DeepSeek 发布新模型，支持更长上下文", "这是原本就有的中文摘要。", "量子位")
        service = self.translator()
        result = await service.translate_pending()
        self.assertEqual((result["translated"], result["batches"], result["reasoning_tokens"]), (12, 2, 0))
        self.assertEqual([len(items) for items in self.calls], [10, 2])
        sent = {item["id"]: item for items in self.calls for item in items}
        self.assertEqual(sent[ids[0]]["excerpt"], ("This is existing source text. " * 80)[:600].rstrip())
        self.assertNotIn("excerpt", sent[ids[1]])
        result = await service.translate_pending()
        self.assertEqual(result["batches"], 0)
        self.assertEqual(len(self.calls), 2)
        raw = repositories().news.execute("SELECT title,content FROM news WHERE id=?", (ids[0],)).fetchone()
        self.assertEqual(raw["title"], "English news headline 0")
        self.assertGreater(len(raw["content"]), 600)
        feed = self.services.ai_content.get_content(None, "中文译文", 100, 0)
        self.assertEqual(feed["total"], 12)
        for item in feed["items"]:
            self.assertEqual(item["title"], f"中文译文{item['id']}")
            self.assertTrue(item["translated"])
            self.assertTrue(item["original_title"].startswith("English"))
            if item["id"] != ids[0]:
                self.assertEqual(item["source_excerpt"], "")
        repositories().news.execute("UPDATE news SET title='Updated English title' WHERE id=?", (ids[0],))
        stale = self.services.ai_content.get_content(None, "Updated", 20, 0)["items"][0]
        self.assertFalse(stale["translated"])
        result = await service.translate_pending()
        self.assertEqual(result["translated"], 1)

    async def test_legacy_placeholder_is_not_sent_and_missing_fields_cannot_be_invented(self):
        self.add("Original title", "Original title\nHacker News 讨论：https://news.ycombinator.com/item?id=123")
        def invalid(request):
            payload = json.loads(request.content)
            item = json.loads(payload["messages"][1]["content"])["items"][0]
            self.assertNotIn("excerpt", item)
            return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"items": [{**item, "excerpt": "捏造的内容"}]})}}]})
        result = await self.translator(invalid).translate_pending()
        self.assertEqual(result["failed"], 1)
        item = self.services.ai_content.get_content(None, "", 20, 0)["items"][0]
        self.assertEqual((item["title"], item["source_excerpt"], item["translated"]), ("Original title", "", False))

    async def test_lobsters_batch_translation_is_visible_in_its_public_source(self):
        ids = [self.add(f"Lobsters technology headline {index}", site="Lobsters") for index in range(12)]
        result = await self.translator().translate_pending("lobsters")
        self.assertEqual((result["translated"], result["batches"]), (12, 2))
        self.assertTrue(all("excerpt" not in item for batch in self.calls for item in batch))
        feed = self.services.ai_content.get_content("lobsters", "", 20, 0)
        self.assertEqual({item["id"] for item in feed["items"]}, set(ids))
        self.assertTrue(all(item["translated"] and item["source_excerpt"] == "" for item in feed["items"]))
        self.assertEqual(next(s for s in feed["sources"] if s["key"] == "lobsters")["name"], "Lobsters")

    async def test_provider_failure_preserves_content_without_retries(self):
        self.add("English test title")
        attempts = []
        def fail(request):
            attempts.append(request)
            return httpx.Response(401, json={"error": "secret-error-must-not-be-logged"})
        result = await self.translator(fail).translate_pending()
        self.assertEqual((result["failed"], len(attempts)), (1, 1))
        self.assertEqual(result["errors"][0]["error"], "HTTP 401")
        self.assertEqual(self.services.ai_content.get_content(None, "", 20, 0)["items"][0]["title"], "English test title")

    async def test_cancellation_stops_translation_and_releases_lease(self):
        self.add("English test title")
        started = asyncio.Event()
        async def slow(request):
            started.set()
            await asyncio.Event().wait()
        task = asyncio.create_task(self.translator(slow).translate_pending("hacker_news"))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(self.services.operation_leases.is_active("ai-translation:hacker_news"))
        row = repositories().ai_content.execute("SELECT success,error FROM news_translation_batches").fetchone()
        self.assertEqual((row["success"], row["error"]), (0, "Cancelled"))

    async def test_scraper_automatically_translates_after_persistence(self):
        class FakeScraper:
            site_name = "Hacker News"
            front_page_entries = [{"story_url": "https://example.test/new", "source_url": "https://example.test/new"}]
            async def run(self):
                return [{"title": "Newly collected English headline", "content": "", "source_site": self.site_name,
                    "url": "https://example.test/new", "type": "article", "published_at": datetime.now(timezone.utc).isoformat()}]
        runs = self.services.scraper_runs
        runs._ai_translation = self.translator()
        runs.configure_worker("translation-test")
        run_id = uuid.uuid4().hex
        repositories().scraper_state.claim_run("hacker_news", run_id, "translation-test")
        with patch.object(self.services.scraper_runtime_state, "require_scraper", return_value=SimpleNamespace(build_scraper=FakeScraper)):
            await runs.run_scraper_task("hacker_news", 10, run_id)
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(self.services.ai_content.get_content(None, "", 20, 0)["items"][0]["translated"])
        self.assertEqual(repositories().scraper_state.get_state("hacker_news")["status"], "idle")
        # A translation outage must not turn successful ingestion into a scrape failure.
        runs._ai_translation = SimpleNamespace(translate_pending=AsyncMock(side_effect=RuntimeError("outage")))
        next_run = uuid.uuid4().hex
        repositories().scraper_state.claim_run("hacker_news", next_run, "translation-test")
        with patch.object(self.services.scraper_runtime_state, "require_scraper", return_value=SimpleNamespace(build_scraper=FakeScraper)):
            await runs.run_scraper_task("hacker_news", 10, next_run)
        self.assertEqual(repositories().scraper_state.get_state("hacker_news")["status"], "idle")

    def test_language_detection_and_batch_identity_validation(self):
        self.assertFalse(needs_chinese_translation("OpenAI 发布 GPT-5，新模型更快了"))
        self.assertFalse(needs_chinese_translation(""))
        self.assertTrue(needs_chinese_translation("A new open source model"))
        self.assertEqual(AITranslationService._validate_response(
            {"items": [{"id": 1, "title": "标题", "excerpt": ""}]}, [{"id": 1, "title": "Title"}]),
            {1: {"title": "标题"}})
        with self.assertRaises(ValueError):
            AITranslationService._validate_response({"items": [{"id": 1, "title": "甲"}, {"id": 1, "title": "乙"}]},
                [{"id": 1, "title": "A"}, {"id": 2, "title": "B"}])
