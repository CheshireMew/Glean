import sqlite3
import unittest

from backend.app.domain.ai_sources import PUBLIC_AI_SOURCES
from backend.app.infrastructure.repository_impl.news_repository import NewsRepository
from backend.app.infrastructure.sqlite.sqlite_migration_plan import (
    JUEJIN_WEEKLY_VERSION,
    LEGACY_BASELINE_VERSION,
    LEGACY_COMPATIBILITY_STEP,
    SCHEMA_VERSION,
    resolve_migration_plan,
)


class CuratedSourceMigrationTest(unittest.TestCase):
    def test_upgrade_adds_selected_feeds_once_disables_removed_media_and_preserves_history(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            LEGACY_COMPATIBILITY_STEP.apply(cursor)
            for step in resolve_migration_plan(LEGACY_BASELINE_VERSION):
                if step.to_version == SCHEMA_VERSION:
                    break
                step.apply(cursor)
            cursor.execute("UPDATE rss_sources SET display_name='我的技术订阅', enabled=0, default_interval=60 WHERE slug='v2ex-tech'")
            cursor.execute("INSERT INTO rss_sources (slug, display_name, feed_url, site_url) VALUES ('my-tmt', '旧钛媒体', 'https://tmtpost.com/feed/', 'https://tmtpost.com/')")
            NewsRepository(conn).insert_news({"source_site": "量子位", "title": "历史内容",
                "content": "历史正文", "url": "https://qbitai.com/old", "type": "article",
                "published_at": "2026-09-27 10:00:00"})
            before = cursor.execute("SELECT COUNT(*) FROM rss_sources").fetchone()[0]
            plan = resolve_migration_plan(JUEJIN_WEEKLY_VERSION)
            self.assertEqual(len(plan), 1)
            for _ in range(2):
                plan[0].apply(cursor)
            rows = {r['slug']: dict(r) for r in cursor.execute("SELECT * FROM rss_sources")}
            self.assertEqual(len(rows), before + 4)
            self.assertEqual(rows['qbitai']['enabled'], 0)
            self.assertEqual(rows['my-tmt']['enabled'], 0)
            self.assertEqual(rows['v2ex-tech']['display_name'], '我的技术订阅')
            self.assertEqual(rows['v2ex-tech']['enabled'], 0)
            self.assertEqual(rows['v2ex-tech']['default_interval'], 60)
            self.assertTrue(all(rows[slug]['enabled'] for slug in (
                'v2ex-main', 'hn-chinese-digest', 'acquired-video', 'baochipianjian')))
            self.assertEqual(cursor.execute("SELECT content FROM news WHERE source_site='量子位'").fetchone()[0], '历史正文')
            self.assertNotIn('rss__qbitai', {s['key'] for s in PUBLIC_AI_SOURCES})
        finally:
            conn.close()
