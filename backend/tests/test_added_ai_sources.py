from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import AsyncMock, patch

import httpx

from backend.app.composition import AppServices
from backend.app.domain.ai_sources import AI_SOURCES, ai_source_sql
from backend.app.infrastructure.database import database, init_database
from backend.app.infrastructure.repositories import repositories
from backend.app.infrastructure.scraper_impl.source_access import source_access
from backend.app.infrastructure.scraper_impl.waytoagi import WaytoAGIScraper
from backend.app.infrastructure.sqlite.sqlite_migration_plan import V2EX_VERSION, JUEJIN_WEEKLY_VERSION, resolve_migration_plan
from backend.tests.test_ai_news_sources import source_http


def document(intro="原文档的介绍。", date="9 月 26 日"):
    mention = {"type": "mention_doc", "data": {"title": "原文标题", "raw_url": "https://waytoagi.feishu.cn/wiki/article?from=copy"}}
    text = "《 》" + intro
    def block(kind, text="", children=()):
        return {"data": {"type": kind, "children": list(children), "text": {"initialAttributedTexts": {"text": {"0": text}}}}}
    blocks = {"root": block("page", children=["start", "day", "end", "not_loaded"]),
              "start": block("heading1", "🎏 近 7 日更新日志"),
              "day": block("heading3", date, ["entry", "image"]),
              "end": block("heading1", "社区活动"), "image": block("image"),
              "entry": block("bullet", text)}
    value = blocks["entry"]["data"]["text"]
    value["apool"] = {"numToAttrib": {"0": ["inline-component", json.dumps(mention, ensure_ascii=False)]}}
    # Leave the unformatted remainder untouched, including non-BMP emoji.
    value["initialAttributedTexts"]["attribs"] = {"0": "+1*0+1"}
    return {"data": {"id": "root", "has_more": True, "block_map": blocks}}


def page(payload):
    return '<script>window.DATA = {clientVars: Object(' + json.dumps(payload, ensure_ascii=False) + ')};</script>'


def feed(*entries):
    return '<feed xmlns="http://www.w3.org/2005/Atom">' + ''.join(
        f'<entry><title>{title}</title><link href="{url}"/><published>2026-09-27T10:00:00Z</published>'
        f'<content type="html">&lt;p&gt;{content}&lt;/p&gt;</content></entry>' for title, url, content in entries) + '</feed>'


class WaytoAGIParserTest(unittest.TestCase):
    def test_public_embedded_data_extracts_only_log_preserving_source_text_and_links(self):
        scraper = WaytoAGIScraper()
        items = scraper.parse_updates(page(document("原文😀介绍。")), datetime(2026, 9, 27))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "原文标题")
        self.assertEqual(items[0]["content"], "原文😀介绍。")
        self.assertEqual(items[0]["source_link"], "https://waytoagi.feishu.cn/wiki/article")
        self.assertEqual(items[0]["url"], scraper.base_url + "#entry")
        self.assertEqual(items[0]["published_at"], "2026-09-26T00:00:00+08:00")
        items = scraper.parse_updates(page(document(date="12 月 31 日")), datetime(2027, 1, 1))
        self.assertTrue(items[0]["published_at"].startswith("2026-12-31"))

    def test_partial_log_login_and_missing_data_fail_instead_of_publishing_empty_list(self):
        partial = document()
        partial["data"]["block_map"]["day"]["data"]["children"].append("missing")
        for html in ("<html>登录</html>", page(partial), page({"data": {"block_map": {}}})):
            with self.subTest(html=html[:80]), self.assertRaisesRegex(RuntimeError, "WaytoAGI"):
                WaytoAGIScraper().parse_updates(html)


class AddedSourceIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=r"D:\Tools")
        self.original = database.db_path
        database.db_path = str(Path(self.folder.name) / "sources.db")
        init_database()
        self.services = AppServices()
        self.services.scraper_runtime_state.ensure_runtime_initialized()
        self.runs = self.services.scraper_runs
        self.runs.configure_worker("sources-test")
        self.runs._ai_translation = SimpleNamespace(translate_pending=AsyncMock(return_value={"translated": 0, "failed": 0, "batches": 0}))
        self.spacing = patch.object(source_access, "spacing", lambda: 0)
        self.spacing.start()

    async def asyncTearDown(self):
        self.spacing.stop()
        database.db_path = self.original
        self.folder.cleanup()

    async def collect(self, key, body, status=200):
        requests = []
        def respond(request):
            requests.append(str(request.url))
            return httpx.Response(status, text=body)
        run_id = uuid.uuid4().hex
        repositories().scraper_state.claim_run(key, run_id, "sources-test")
        with source_http(respond):
            await self.runs.run_scraper_task(key, 100, run_id, trigger="ai-view")
        return requests

    def content(self, key):
        return self.services.ai_content.get_content(key, "", 100, 0)

    async def test_v2ex_fragments_reordering_edits_and_failure_keep_correct_snapshot(self):
        key = "rss__v2ex-tech"
        first = ("一个标题", "https://www.v2ex.com/t/1#reply2", "原内容")
        second = ("另一个标题", "https://www.v2ex.com/t/2#reply0", "")
        self.assertEqual(await self.collect(key, feed(first, second)), ["https://www.v2ex.com/feed/tab/tech.xml"])
        result = self.content(key)
        ids = [item["id"] for item in result["items"]]
        self.assertEqual([item["source_url"] for item in result["items"]], ["https://www.v2ex.com/t/1", "https://www.v2ex.com/t/2"])
        await self.collect(key, feed(second, ("已修订标题", "https://www.v2ex.com/t/1#reply99", "新内容")))
        result = self.content(key)
        self.assertEqual([item["id"] for item in result["items"]], ids[::-1])
        self.assertEqual(result["items"][1]["source_excerpt"], "新内容")
        await self.collect(key, feed(second))
        self.assertEqual(self.content(key)["total"], 1)
        await self.collect(key, "<html>Not a feed</html>")
        self.assertEqual(self.content(key)["total"], 1)
        self.assertEqual(repositories().news.execute("SELECT count(*) n FROM news WHERE source_site='V2EX · 技术'").fetchone()["n"], 2)
        self.runs._ai_translation.translate_pending.assert_awaited_with(key, 100)

    async def test_waytoagi_single_request_persists_log_and_updates_existing_block(self):
        self.assertEqual(await self.collect("waytoagi", page(document())), [WaytoAGIScraper().base_url])
        result = self.content("waytoagi")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["source_excerpt"], "原文档的介绍。")
        self.assertEqual(result["items"][0]["source_url"], "https://waytoagi.feishu.cn/wiki/article")
        await self.collect("waytoagi", page(document("修改后的真实介绍。")))
        updated = self.content("waytoagi")
        self.assertEqual(updated["items"][0]["id"], result["items"][0]["id"])
        self.assertEqual(updated["items"][0]["source_excerpt"], "修改后的真实介绍。")
        await self.collect("waytoagi", "<html>Missing document</html>")
        self.assertEqual(self.content("waytoagi")["items"], updated["items"])

    async def test_weekly_rss_preserves_hidden_recommendations_and_refreshes_ranked_membership(self):
        key = "rss__juejin-weekly"
        news = repositories().news
        old = []
        for number in (1, 9):
            old.append(news.insert_news({"title": "旧推荐", "content": "旧摘要", "type": "article",
                "source_site": "掘金 · AI 推荐", "url": f"https://juejin.cn/post/{number}",
                "published_at": "2026-05-01 12:00:00"}))
        first = ("周榜第一", "https://juejin.cn/post/1", "RSS 真实正文")
        second = ("周榜第二", "https://juejin.cn/post/2", "RSS 真实摘要")
        self.assertEqual(await self.collect(key, feed(first, second)),
                         ["https://rsshub.bestblogs.dev/juejin/trending/all/weekly"])
        items = self.content(key)["items"]
        self.assertEqual([item["title"] for item in items], ["周榜第一", "周榜第二"])
        self.assertNotEqual(items[0]["id"], old[0])
        self.assertEqual(items[0]["source_url"], "https://juejin.cn/post/1")
        self.assertEqual(news.execute("SELECT title, content, source_site FROM news WHERE id=?", (old[0],)).fetchone()["title"], "旧推荐")
        self.assertEqual(items[0]["source_excerpt"], "RSS 真实正文")
        self.assertEqual(items[0]["source_site"], "掘金本周最热")
        self.assertNotIn(old[1], [item["id"] for item in self.content(None)["items"]])
        self.assertEqual(news.execute(f"SELECT COUNT(*) n FROM news WHERE NOT {ai_source_sql('source_site')}").fetchone()["n"], 0)
        await self.collect(key, feed(second, first))
        self.assertEqual([item["title"] for item in self.content(key)["items"]], ["周榜第二", "周榜第一"])
        await self.collect(key, feed(second))
        self.assertEqual(self.content(key)["total"], 1)
        await self.collect(key, "<html>Not a feed</html>")
        self.assertEqual(self.content(key)["total"], 1)
        self.assertEqual(news.execute("SELECT count(*) n FROM news").fetchone()["n"], 4)
        self.assertIn("juejin_ai", self.services.scraper_registry.names())
        self.assertNotIn("juejin_ai", [s["key"] for s in self.content(None)["sources"]])
        self.assertFalse(any("reddit" in json.dumps(s).lower() for s in AI_SOURCES))
        self.assertFalse(any("reddit" in s["feed_url"].lower() for s in repositories().rss_sources.list_sources()))

    async def test_rss_snapshot_resolves_a_configured_source_name(self):
        source = repositories().rss_sources.get_source_by_slug("v2ex-tech")
        repositories().rss_sources.update_source(source["id"], {**source, "display_name": "我的技术订阅"})
        await self.collect("rss__v2ex-tech", feed(("原帖", "https://www.v2ex.com/t/9", "正文")))
        self.assertEqual(self.content("rss__v2ex-tech")["items"][0]["source_site"], "我的技术订阅")

    async def test_v2ex_homepage_and_tech_can_share_a_topic_without_overwriting_each_other(self):
        topic = "https://www.v2ex.com/t/42"
        await self.collect("rss__v2ex-tech", feed(("技术栏标题", topic + "#reply1", "技术栏正文")))
        await self.collect("rss__v2ex-main", feed(("首页标题", topic + "#reply20", "首页正文")))
        tech = self.content("rss__v2ex-tech")["items"][0]
        home = self.content("rss__v2ex-main")["items"][0]
        self.assertNotEqual(tech["id"], home["id"])
        self.assertEqual(tech["source_url"], home["source_url"])
        self.assertEqual(home["source_url"], topic)
        await self.collect("rss__v2ex-main", feed(("首页修订", topic + "#reply99", "首页新正文")))
        self.assertEqual(self.content("rss__v2ex-main")["items"][0]["id"], home["id"])
        self.assertEqual(self.content("rss__v2ex-tech")["items"][0]["source_excerpt"], "技术栏正文")
        self.assertEqual(self.content("rss__v2ex-main")["items"][0]["source_excerpt"], "首页新正文")

    async def test_selected_digest_video_and_podcast_reach_public_feed_and_translation(self):
        for key, url in (
            ("rss__hn-chinese-digest", "https://supertechfans.com/cn/post/test/"),
            ("rss__acquired-video", "https://www.youtube.com/watch?v=test"),
            ("rss__baochipianjian", "https://www.xiaoyuzhoufm.com/episode/test"),
        ):
            with self.subTest(source=key):
                await self.collect(key, feed(("来源实际标题", url, "来源实际摘要")))
                content = self.content(key)
                self.assertEqual(content["total"], 1)
                self.assertEqual(content["items"][0]["source_key"], key)
                self.assertEqual(content["items"][0]["source_url"], url)
                self.assertEqual(content["items"][0]["source_excerpt"], "来源实际摘要")
                self.runs._ai_translation.translate_pending.assert_awaited_with(key, 100)
        source_keys = {s["key"] for s in self.content(None)["sources"]}
        self.assertNotIn("rss__qbitai", source_keys)
        self.assertTrue({"rss__v2ex-main", "rss__v2ex-tech", "rss__hn-chinese-digest",
                         "rss__acquired-video", "rss__baochipianjian"} <= source_keys)

    def test_upgrade_adds_feeds_once_and_preserves_existing_configuration(self):
        source = repositories().rss_sources.get_source_by_slug("v2ex-tech")
        repositories().rss_sources.update_source(source["id"], {**source, "enabled": False, "display_name": "我的订阅"})
        conn = sqlite3.connect(database.db_path)
        try:
            conn.execute("INSERT INTO source_catalog (source_key, display_name, source_type) VALUES ('juejin_ai', '掘金 · AI 推荐', 'api')")
            conn.execute("INSERT INTO scraper_runtime_commands (scraper_name, command_type) VALUES ('juejin_ai', 'run')")
            conn.execute("UPDATE scraper_runtime_state SET status='queued' WHERE scraper_name='juejin_ai'")
            plan = resolve_migration_plan(V2EX_VERSION)
            self.assertEqual(plan[0].to_version, JUEJIN_WEEKLY_VERSION)
            for _ in range(2):
                plan[0].apply(conn.cursor())
            conn.commit()
            self.assertEqual(conn.execute("SELECT enabled FROM source_catalog WHERE source_key='juejin_ai'").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT status FROM scraper_runtime_commands WHERE scraper_name='juejin_ai'").fetchone()[0], "pending")
            self.assertEqual(conn.execute("SELECT status FROM scraper_runtime_state WHERE scraper_name='juejin_ai'").fetchone()[0], "queued")
        finally:
            conn.close()
        feeds = repositories().rss_sources.list_sources()
        self.assertEqual(len(feeds), 15)
        kept = next(s for s in feeds if s["slug"] == "v2ex-tech")
        self.assertFalse(kept["enabled"])
        self.assertEqual(kept["display_name"], "我的订阅")
