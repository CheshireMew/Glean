from __future__ import annotations

import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx

from backend.app.composition import AppServices
from backend.app.infrastructure.database import database, init_database
from backend.app.infrastructure.repositories import repositories
from backend.main import app
from backend.tests.test_ai_news_sources import hn_page, hn_row, source_http


class AIContentTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=r"D:\Tools")
        self.original_db = database.db_path
        database.db_path = str(Path(self.folder.name) / "ai-content.db")
        init_database()
        self.services = AppServices()
        now = datetime.now(timezone.utc).isoformat()
        self.ids = []
        for index, (site, title, content) in enumerate([
            ("Hacker News", "No Blind Trust", "No Blind Trust\nHacker News 讨论：https://news.ycombinator.com/item?id=123"),
            ("量子位", "机器人研究", "来源实际提供的节选。"),
            ("InfoQ 中文", "技术架构实践", "点击查看原文>"),
            ("Hugging Face Blog", "Tokenizer release", ""),
            ("Original Wire", "市场交易数据", "原资讯内容。"),
        ]):
            self.ids.append(repositories().news.insert_news({
                "source_site": site, "title": title, "content": content, "url": f"https://example.test/{index}",
                "published_at": now, "type": "article",
            }))
        repositories().ai_content.save_hacker_news_front_page([
            {"story_url": "https://example.test/0", "source_url": "https://example.test/0"}])

    async def asyncTearDown(self):
        database.db_path = self.original_db
        self.folder.cleanup()

    async def test_raw_api_provenance_search_and_pagination(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/public/ai/content", params={"limit": 2})
            self.assertEqual(response.status_code, 200)
            first = response.json()["data"]
            second = (await client.get("/api/public/ai/content", params={"limit": 2, "offset": 2})).json()["data"]
            self.assertEqual(first["total"], 3)
            self.assertEqual(len({i["id"] for i in first["items"] + second["items"]}), 3)
            totals = {s["key"]: s["total"] for s in first["sources"]}
            self.assertNotIn("rss__qbitai", totals)
            self.assertEqual({key for key, count in totals.items() if count},
                             {"hacker_news", "rss__infoq-cn", "rss__huggingface-blog"})
            entries = {i["source_site"]: i for i in first["items"] + second["items"]}
            self.assertEqual(entries["Hacker News"]["source_excerpt"], "")
            self.assertEqual(entries["Hugging Face Blog"]["source_excerpt"], "")
            self.assertEqual(entries["InfoQ 中文"]["source_excerpt"], "")
            self.assertNotIn("量子位", entries)
            for item in entries.values():
                self.assertNotIn("review_summary", item)
            filtered = (await client.get("/api/public/ai/content", params={"source": "rss__infoq-cn", "query": "架构"})).json()["data"]
            self.assertEqual(filtered["total"], 1)
            self.assertEqual(filtered["items"][0]["source_url"], "https://example.test/2")
            self.assertEqual((await client.get("/api/public/ai/content", params={"source": "rss__qbitai"})).status_code, 400)
            self.assertEqual((await client.get("/api/public/ai/content", params={"source": "unknown"})).status_code, 400)

    async def test_ai_content_and_reports_stay_out_of_existing_public_feed(self):
        await self.services.pipeline.cluster_content(24, 0.99, "article")
        await self.services.pipeline.apply_blocklist(24, "article")
        rows = repositories().review.execute("SELECT id, source_site FROM review_entries ORDER BY id").fetchall()
        publication = next(p for p in self.services.publications.list_publications() if p["content_type"] == "article")
        draft_ids = []
        for row in rows:
            self.services.editorial_workbench.update_entry(row["id"], {
                "review_status": "selected", "review_summary": "这是一段不应泄露到 AI 页的编辑文字。", "review_reason": "测试",
            }, "test")
            draft = self.services.editorial_workbench.create_draft({
                "publication_id": publication["id"], "content_type": "article", "title": row["source_site"],
                "items": [{"review_entry_id": row["id"], "position": 0, "section": "测试", "included": True, "overrides": {}}],
            }, "test")
            await self.services.publication_workflow.publish_draft(draft["id"], website_only=True)
            draft_ids.append(draft["id"])
        feed = self.services.public_content.get_public_content("article", 20, 0)
        self.assertEqual([r["source_site"] for r in feed["items"]], ["Original Wire"])
        self.assertEqual(self.services.public_content.search_public_content("No Blind Trust", "article", 20, 0)["total"], 0)
        self.assertNotIn("No Blind Trust", self.services.public_content.build_public_rss("article", 20))
        reports = self.services.public_content.get_public_reports("article", 20, 0)
        self.assertEqual([r["title"] for r in reports["items"]], ["Original Wire"])
        ai = self.services.ai_content.get_content(None, "", 20, 0)
        self.assertNotIn("编辑文字", str(ai))
        self.assertEqual(ai["total"], 3)
        # Withdrawal hides a report but preserves its snapshot for audit.
        repositories().editorial_workbench.update_draft(draft_ids[-1], status="cancelled")
        self.assertEqual(self.services.public_content.get_public_reports("article", 20, 0)["total"], 0)
        self.assertEqual(repositories().daily_reports.list_reports("article", 20, 0)["total"], 5)

    async def test_configured_source_name_is_resolved(self):
        source = repositories().rss_sources.get_source_by_slug("infoq-cn")
        repositories().rss_sources.update_source(source["id"], {**source, "display_name": "我的技术资讯"})
        repositories().news.execute("UPDATE news SET source_site = ? WHERE source_site = ?", ("我的技术资讯", "InfoQ 中文"))
        result = self.services.ai_content.get_content("rss__infoq-cn", "", 20, 0)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["source_key"], "rss__infoq-cn")

    async def test_homepage_membership_order_links_and_failed_refresh_preserve_history(self):
        # An article already saved by another source must still appear on HN.
        repositories().news.insert_news({"source_site": "Lobsters", "title": "Shared article",
            "url": "https://example.org/shared", "type": "article", "content": "",
            "published_at": datetime.now(timezone.utc).isoformat()})
        runs = self.services.scraper_runs
        runs.configure_worker("home-test")
        runs._ai_translation = SimpleNamespace(translate_pending=AsyncMock(return_value={
            "translated": 0, "failed": 0, "batches": 0}))

        async def collect(html):
            run_id = uuid.uuid4().hex
            repositories().scraper_state.claim_run("hacker_news", run_id, "home-test")
            with source_http(lambda request: httpx.Response(200, text=html)):
                await runs.run_scraper_task("hacker_news", 30, run_id, trigger="ai-view")

        first = hn_row(11, "https://example.org/shared", "Front page first")
        second = hn_row(12, None, "Ask HN: Homepage discussion")
        await collect(hn_page(first, second))
        feed = self.services.ai_content.get_content("hacker_news", "", 20, 0)
        self.assertEqual([item['title'] for item in feed['items']], ['Front page first', 'Ask HN: Homepage discussion'])
        self.assertEqual([item['source_url'] for item in feed['items']],
                         ['https://example.org/shared', 'https://news.ycombinator.com/item?id=12'])
        self.assertEqual(feed['sources'][0]['total'], 2)
        self.assertEqual(self.services.ai_content.get_content(None, "No Blind Trust", 20, 0)['total'], 0)
        self.assertEqual(repositories().ai_content.translation_candidates(['Hacker News'])[0]['title'], 'Ask HN: Homepage discussion')

        # No new rows: rank changes still reach the public page and pagination.
        await collect(hn_page(second, first))
        reordered = self.services.ai_content.get_content("hacker_news", "", 1, 0)
        self.assertEqual(reordered['items'][0]['title'], 'Ask HN: Homepage discussion')
        self.assertEqual(self.services.ai_content.get_content("hacker_news", "", 1, 1)['items'][0]['title'], 'Front page first')

        await collect(hn_page(first))
        self.assertEqual(self.services.ai_content.get_content("hacker_news", "", 20, 0)['total'], 1)
        await collect('<html>Temporarily unavailable</html>')
        self.assertEqual(repositories().scraper_state.get_state('hacker_news')['status'], 'error')
        self.assertEqual(self.services.ai_content.get_content("hacker_news", "", 20, 0)['total'], 1)
        self.assertEqual(repositories().news.execute("SELECT count(*) AS n FROM news WHERE source_site='Hacker News'").fetchone()['n'], 3)
        self.assertEqual(self.services.ai_content.get_content("lobsters", "", 20, 0)['total'], 1)
