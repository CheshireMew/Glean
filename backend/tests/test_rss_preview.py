import asyncio
import io
import json
import sqlite3
import unittest
from contextlib import redirect_stdout
from unittest.mock import AsyncMock, Mock, patch

from backend.app.infrastructure.scraper_impl.rss_feed import RssFeedScraper
from backend.app.services.rss_source_service import RssSourceService
from backend.app.core.exceptions import BusinessError


SOURCE = {"display_name": "Writer", "site_url": "https://example.com", "feed_url": "https://example.com/feed",
          "content_kind": "article", "default_limit": 3, "parser_type": "generic"}
BODY = "<p>开篇 " + "完整内容 " * 220 + "</p><p>最后一段提供结论。</p>"
XML = f'''<rss version="2.0"><channel><item><title>Long article</title>
<link>https://example.com/article</link><author>Writer</author>
<pubDate>Fri, 04 Sep 2026 08:00:00 GMT</pubDate>
<description><![CDATA[{BODY}]]></description></item></channel></rss>'''


class RssPreviewTest(unittest.TestCase):
    def test_long_content_reaches_database(self):
        from backend.app.infrastructure.sqlite.sqlite_schema import create_news_table
        from backend.app.infrastructure.repository_impl.news_repository import NewsRepository
        conn = sqlite3.connect(":memory:")
        try:
            create_news_table(conn.cursor())
            repo = NewsRepository(conn)
            scraper = RssFeedScraper(SOURCE)
            scraper.fetch_text = AsyncMock(return_value=XML)
            scraper.item_callback = repo.insert_news
            asyncio.run(scraper.scrape_important_news())
            content = conn.execute("SELECT content FROM news").fetchone()[0]
            self.assertGreater(len(content), 500)
            self.assertTrue(content.endswith("\n最后一段提供结论。"))
        finally:
            conn.close()

    def test_api_contract_and_validation(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.app.routers.config import router
        from backend.app.routers.auth import get_current_user
        from backend.app.composition import app_services
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: "tester"
        result = {"feed_url": SOURCE["feed_url"], "notice": "preview", "items": [
            {**RssFeedScraper(SOURCE).parse_entries(XML)[0], "content_origin": "feed", "completeness": "unknown"}
        ]}
        with patch.object(app_services.rss_sources, "preview", AsyncMock(return_value=result)) as preview:
            with TestClient(app) as client:
                response = client.post("/rss/preview", json={"feed_url": SOURCE["feed_url"]})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json()["data"]["items"][0]["content"].endswith("最后一段提供结论。"))
                self.assertEqual(client.post("/rss/preview", json={"feed_url": SOURCE["feed_url"], "limit": 6}).status_code, 422)
                self.assertEqual(preview.await_count, 1)

    def test_long_content_and_paragraphs_survive_normal_collection(self):
        scraper = RssFeedScraper(SOURCE)
        scraper.fetch_text = AsyncMock(return_value=XML)
        saved = []
        scraper.item_callback = saved.append
        items = asyncio.run(scraper.scrape_important_news())
        self.assertGreater(len(items[0]["content"]), 500)
        self.assertTrue(items[0]["content"].endswith("\n\n最后一段提供结论。"))
        self.assertEqual(saved, items)

    def test_preview_same_content_without_state_or_persistence(self):
        scraper = RssFeedScraper(SOURCE)
        scraper.transport.start = AsyncMock()
        scraper.transport.close = AsyncMock()
        scraper.fetch_text = AsyncMock(return_value=XML)
        scraper.item_callback = Mock(side_effect=AssertionError("must not persist"))
        scraper.should_stop_scraping = Mock(side_effect=AssertionError("must not check incremental state"))
        preview = asyncio.run(scraper.preview(3))
        self.assertEqual(preview, scraper.parse_entries(XML))
        self.assertFalse(scraper.used_result_buffer)
        scraper.transport.close.assert_awaited_once()

    def test_atom_xhtml_and_alternate_link(self):
        xml = '''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Essay</title>
        <link rel="self" href="https://example.com/api/1"/>
        <link rel="alternate" href="https://example.com/essay"/>
        <content type="xhtml"><div xmlns="http://www.w3.org/1999/xhtml"><p>First <b>bold</b>.</p><p>End.</p></div></content>
        </entry></feed>'''
        item = RssFeedScraper(SOURCE).parse_entries(xml)[0]
        self.assertEqual(item["url"], "https://example.com/essay")
        self.assertEqual(item["content"], "First bold.\n\nEnd.")

    def test_source_link_parser_and_preview_limit(self):
        xml = '''<rss><channel><item><title>Report</title><link>https://example.com/roundup</link>
        <description><![CDATA[<p>导读</p><a href="https://original.com/story">原文</a>]]></description>
        </item><item><title>Second</title><link>https://example.com/2</link></item></channel></rss>'''
        items = RssFeedScraper({**SOURCE, "parser_type": "summary_source_link"}).parse_entries(xml, limit=1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["url"], "https://original.com/story")

    def test_service_does_not_use_repositories_and_explains_failures(self):
        forbidden = Mock(side_effect=AssertionError("database accessed"))
        scraper = Mock()
        scraper.preview = AsyncMock(return_value=RssFeedScraper(SOURCE).parse_entries(XML))
        service = RssSourceService(forbidden, forbidden, Mock(return_value=scraper))
        result = asyncio.run(service.preview({"feed_url": SOURCE["feed_url"]}))
        self.assertEqual(result["items"][0]["completeness"], "unknown")
        forbidden.assert_not_called()
        scraper.preview.side_effect = RuntimeError("响应不是支持的 RSS/Atom 格式")
        with self.assertRaisesRegex(BusinessError, "RSS/Atom"):
            asyncio.run(service.preview({"feed_url": SOURCE["feed_url"]}))

    def test_invalid_feed_closes_transport(self):
        scraper = RssFeedScraper(SOURCE)
        scraper.transport.start = AsyncMock()
        scraper.transport.close = AsyncMock()
        scraper.fetch_text = AsyncMock(return_value="<html>Login required</html>")
        with self.assertRaisesRegex(RuntimeError, "RSS/Atom"):
            asyncio.run(scraper.preview(3))
        scraper.transport.close.assert_awaited_once()

    def test_cli_preview_without_database(self):
        from backend.cli.app import main
        from backend.app.composition import app_services
        result = {"feed_url": SOURCE["feed_url"], "items": [], "notice": "preview"}
        stdout = io.StringIO()
        with patch.object(app_services.rss_sources, "preview", AsyncMock(return_value=result)), \
                patch("backend.cli.models.CommandContext.database", new_callable=unittest.mock.PropertyMock, side_effect=AssertionError("database accessed")), \
                patch("sys.stdin", io.StringIO(json.dumps({"feed_url": SOURCE["feed_url"]}))), redirect_stdout(stdout):
            code = main(["rss", "preview", "--input", "-"])
        self.assertEqual(code, 0, stdout.getvalue())
        self.assertEqual(json.loads(stdout.getvalue())["data"], result)
