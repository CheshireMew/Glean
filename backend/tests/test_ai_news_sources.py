from __future__ import annotations

import asyncio
from contextlib import contextmanager
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from backend.app.infrastructure.repository_impl.news_repository import NewsRepository
from backend.app.infrastructure.repository_impl.rss_source_repository import RssSourceRepository
from backend.app.infrastructure.scraper_impl.hacker_news import HackerNewsScraper
from backend.app.infrastructure.scraper_impl.lobsters import LobstersScraper
from backend.app.infrastructure.scraper_impl.rss_feed import RssFeedScraper
from backend.app.infrastructure.scrapers import scraper_catalog
from backend.app.infrastructure.sqlite.db_sqlite import Database
from backend.app.infrastructure.scraper_impl.source_access import source_access
from backend.app.infrastructure.sqlite.source_presets import AI_RSS_SOURCES, CURATED_RSS_SOURCES, seed_ai_rss_sources
from backend.app.infrastructure.sqlite.sqlite_migration_plan import (
    AI_NEWS_SOURCES_VERSION,
    INTELLIGENCE_WORKFLOWS_VERSION,
    LEGACY_BASELINE_VERSION,
    LEGACY_COMPATIBILITY_STEP,
    SCHEMA_VERSION,
    create_current_schema,
    resolve_migration_plan,
)
from backend.app.services.rss_source_service import RssSourceService
from backend.app.services.scraper_registry_service import ScraperRegistryService


@contextmanager
def source_http(handler):
    """Replace only the external network, keeping real transport and parsing."""
    original_client = httpx.AsyncClient
    with patch(
        "backend.app.infrastructure.scraper_impl.source_transport.httpx.AsyncClient",
        side_effect=lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs),
    ):
        yield


def hn_row(story_id=1, url="https://example.org/article", title=None):
    return (f'<tr class="athing submission" id="{story_id}"><td><span class="titleline">'
            f'<a href="{url or "item?id=" + str(story_id)}">{title or "Story " + str(story_id)}</a></span></td></tr>'
            '<tr><td class="subtext"><span class="score">123 points</span>'
            '<a class="hnuser">writer</a><span class="age" title="2026-09-26T06:00:00 1790402400">2 hours ago</span></td></tr>')


def hn_page(*rows):
    return '<html><table>' + ''.join(rows) + '</table></html>'


class AiSourceCollectionTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=r"D:\Tools")
        self.access_db = Database(str(Path(self.folder.name) / "source-access.db"))
        self.access_db.init_db()
        self.db_patch = patch.object(source_access, "db", self.access_db)
        self.spacing_patch = patch.object(source_access, "spacing", lambda: 0)
        self.db_patch.start()
        self.spacing_patch.start()

    def tearDown(self):
        self.spacing_patch.stop()
        self.db_patch.stop()
        self.folder.cleanup()

    def test_hacker_news_request_and_persistence(self):
        requests = []

        def respond(request):
            requests.append(request)
            return httpx.Response(200, text=hn_page(hn_row(), hn_row(2, None)))

        conn = sqlite3.connect(":memory:")
        try:
            create_current_schema(conn.cursor())
            scraper = scraper_catalog.get("hacker_news").scraper_cls()
            scraper.item_callback = NewsRepository(conn).insert_news
            with source_http(respond):
                items = asyncio.run(scraper.run())
            rows = conn.execute("SELECT source_site, source_url, published_at, type FROM news ORDER BY id").fetchall()
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0], ("Hacker News", "https://news.ycombinator.com/item?id=1", "2026-09-26 06:00:00", "article"))
            self.assertEqual(rows[1][1], "https://news.ycombinator.com/item?id=2")
            self.assertEqual(items[0]["content"], "")
            self.assertEqual([str(request.url) for request in requests], ["https://news.ycombinator.com/"])
            self.assertEqual(scraper.front_page_entries[0]["source_url"], "https://example.org/article")
            self.assertNotIn("authorization", requests[0].headers)
            self.assertIsNone(scraper.transport.client)
        finally:
            conn.close()

    def test_lobsters_reads_recent_once_preserves_links_and_skips_known_posts(self):
        def story(title, url, timestamp="1790474843"):
            return f'<li class="story"><span class="link"><a class="u-url" href="{url}">{title}</a></span><a class="u-author">writer</a><time data-at-unix="{timestamp}"></time><span class="comments_label">10 comments</span></li>'
        html = '<ol>' + story('Known', 'https://example.test/known') + story('New &amp; useful', 'https://example.test/new') + story('Duplicate', 'https://example.test/new') + story('Discussion', '/s/abc/thread') + story('Broken time', 'https://example.test/bad', 'invalid') + '</ol>'
        requests = []
        scraper = scraper_catalog.get("lobsters").scraper_cls()
        scraper.existing_urls = {"https://example.test/known"}
        def respond(request):
            requests.append(str(request.url))
            return httpx.Response(200, text=html)
        with source_http(respond):
            items = asyncio.run(scraper.run())
        self.assertEqual(requests, ["https://lobste.rs/recent"])
        self.assertEqual([item["url"] for item in items], ["https://example.test/new", "https://lobste.rs/s/abc/thread"])
        self.assertEqual(items[0]["title"], "New & useful")
        self.assertEqual(items[0]["published_at"], "2026-09-27T02:07:23+00:00")
        self.assertTrue(all(item["content"] == "" and item["source_site"] == "Lobsters" for item in items))
        scraper.existing_urls.update(item["url"] for item in items)
        with source_http(respond):
            self.assertEqual(asyncio.run(scraper.run()), [])
        with source_http(lambda request: httpx.Response(200, text="<title>Not a story list</title>")):
            with self.assertRaisesRegex(RuntimeError, "Lobsters"):
                asyncio.run(LobstersScraper().run())

    def test_hacker_news_skips_known_ids_and_tracks_reordering_without_new_rows(self):
        scraper = HackerNewsScraper()
        scraper.existing_urls = {"https://news.ycombinator.com/item?id=1"}
        html = hn_page(hn_row(1), hn_row(2), hn_row(2))
        with source_http(lambda request: httpx.Response(200, text=html)):
            items = asyncio.run(scraper.run())
            self.assertEqual(len(items), 1)
            scraper.existing_urls.add(items[0]["url"])
            self.assertEqual(asyncio.run(scraper.run()), [])
            self.assertEqual(len(scraper.front_page_entries), 2)
        with source_http(lambda request: httpx.Response(200, text=hn_page(hn_row(2), hn_row(1)))):
            self.assertEqual(asyncio.run(scraper.run()), [])
            self.assertEqual([entry['story_url'] for entry in scraper.front_page_entries],
                             ['https://news.ycombinator.com/item?id=2', 'https://news.ycombinator.com/item?id=1'])

    def test_hacker_news_empty_or_malformed_homepage_fails(self):
        for html in ('<html></html>', hn_page(hn_row()).replace('2026-09-26T06:00:00', 'invalid')):
            with self.subTest(html=html), source_http(lambda request: httpx.Response(200, text=html)):
                with self.assertRaisesRegex(RuntimeError, "Hacker News"):
                    asyncio.run(HackerNewsScraper().run())
        scraper = HackerNewsScraper()
        with source_http(lambda request: httpx.Response(403)):
            with self.assertRaisesRegex(RuntimeError, "403"):
                asyncio.run(scraper.run())
        self.assertIsNone(scraper.transport.client)

    def test_hacker_news_limit_applies_to_homepage_positions_not_new_item_count(self):
        scraper = HackerNewsScraper()
        scraper.max_items = 1
        html = hn_page(hn_row(1, None, 'Ask HN: <b>How?</b>'), hn_row(2))
        with source_http(lambda request: httpx.Response(200, text=html)):
            items = asyncio.run(scraper.run())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Ask HN: How?")
        self.assertEqual(items[0]["content"], "")
        scraper.existing_urls = {items[0]["url"]}
        with source_http(lambda request: httpx.Response(200, text=html)):
            self.assertEqual(asyncio.run(scraper.run()), [])
        self.assertEqual(len(scraper.front_page_entries), 1)

    def test_rss_reordered_known_items_do_not_hide_new_entries(self):
        source = {"display_name": "Feed", "site_url": "https://example.org/", "feed_url": "https://example.org/feed",
                  "default_limit": 6, "content_kind": "article"}
        xml = '<rss><channel>' + ''.join(
            f'<item><title>Story {number}</title><link>https://example.org/{number}</link></item>'
            for number in (1, 2, 3, 4, 4, 5)
        ) + '</channel></rss>'
        scraper = RssFeedScraper(source)
        scraper.last_news_url = "https://example.org/1"
        scraper.existing_urls = {f"https://example.org/{number}" for number in (1, 2, 3)}
        with source_http(lambda request: httpx.Response(200, text=xml)):
            items = asyncio.run(scraper.run())
            self.assertEqual([item["url"] for item in items], ["https://example.org/4", "https://example.org/5"])
            scraper.existing_urls.update(item["url"] for item in items)
            self.assertEqual(asyncio.run(scraper.run()), [])


class AiSourceMigrationTest(unittest.TestCase):
    def test_fresh_database_sources_reach_runtime_registry(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            create_current_schema(conn.cursor())
            repository = RssSourceRepository(conn)
            sources = RssSourceService(lambda: repository, None)
            registry = ScraperRegistryService(sources, (), RssFeedScraper)
            enabled_presets = {row[0]: row for row in (*AI_RSS_SOURCES, *CURATED_RSS_SOURCES) if row[0] != "qbitai"}
            self.assertIsNone(registry.get("rss__qbitai"))
            for slug, name, feed_url, _, _, _ in enabled_presets.values():
                definition = registry.require(f"rss__{slug}")
                self.assertEqual(definition.display_name, name)
                self.assertEqual(definition.transport_kind, "rss")
                self.assertEqual(definition.build_scraper().feed_url, feed_url)
                self.assertEqual(definition.content_kind, "article")
            seed_ai_rss_sources(conn.cursor())
            self.assertEqual(len(repository.list_sources()), 6 + len(enabled_presets) + 1)
        finally:
            conn.close()

    def test_existing_database_upgrade_preserves_settings_and_feed_aliases(self):
        with tempfile.TemporaryDirectory(dir=r"D:\Tools") as folder:
            path = Path(folder) / "old-sources.db"
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.cursor()
                # Produce the previous schema using its registered migration chain.
                LEGACY_COMPATIBILITY_STEP.apply(cursor)
                for step in resolve_migration_plan(LEGACY_BASELINE_VERSION):
                    if step.to_version == AI_NEWS_SOURCES_VERSION:
                        break
                    step.apply(cursor)
                cursor.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY)")
                cursor.execute("INSERT INTO schema_migrations VALUES (?)", (INTELLIGENCE_WORKFLOWS_VERSION,))
                cursor.execute("UPDATE rss_sources SET enabled=0, display_name='My feed' WHERE slug='chainfeeds'")
                cursor.execute("""INSERT INTO rss_sources (slug, display_name, feed_url, site_url, enabled)
                                  VALUES ('my-qbit', 'My Qbit', 'https://qbitai.com/feed', 'https://qbitai.com', 0)""")
                conn.commit()
            finally:
                conn.close()
            database = Database(str(path))
            database.init_db()
            database.init_db()
            with database.connect() as reopened:
                rows = {row["slug"]: dict(row) for row in reopened.execute("SELECT * FROM rss_sources")}
                self.assertEqual(rows["my-qbit"]["enabled"], 0)
                self.assertNotIn("qbitai", rows)
                self.assertEqual(rows["chainfeeds"]["display_name"], "My feed")
                self.assertEqual(rows["chainfeeds"]["enabled"], 0)
                self.assertIn("infoq-cn", rows)
                self.assertIn("huggingface-blog", rows)
                self.assertEqual(len(rows), 6 + len({s[0] for s in (*AI_RSS_SOURCES, *CURATED_RSS_SOURCES)}))
                self.assertEqual(reopened.execute("SELECT version FROM schema_migrations ORDER BY rowid DESC LIMIT 1").fetchone()[0], SCHEMA_VERSION)
            reopened.close()
            database.assert_schema_current()
            self.assertEqual(len(list((Path(folder) / "archive" / "database-backups").glob("*.db"))), 1)


if __name__ == "__main__":
    unittest.main()
