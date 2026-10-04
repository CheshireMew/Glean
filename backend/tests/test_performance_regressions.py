from __future__ import annotations

import sqlite3
import asyncio
import inspect
import json
import subprocess
import sys
import statistics
import time
import unittest
from datetime import datetime, timezone

from backend.app.infrastructure.event_clustering import EventClusterer
from backend.app.infrastructure.repository_impl.review_public_repository import ReviewPublicRepository
from backend.app.infrastructure.repository_impl.maintenance_repository import MaintenanceRepository
from backend.app.infrastructure.sqlite.sqlite_migration_plan import create_current_schema
from backend.app.services.scraper_run_service import ScraperRunService


class CountingClusterer(EventClusterer):
    def __init__(self, similarity_threshold: float = 0.5):
        super().__init__(similarity_threshold)
        self.similarity_calls = 0
        self.feature_calls = 0

    def extract_features(self, text: str):
        self.feature_calls += 1
        return super().extract_features(text)

    def calculate_similarity(self, left, right):
        self.similarity_calls += 1
        return super().calculate_similarity(left, right)


class PerformanceRegressionTest(unittest.TestCase):
    def test_event_clustering_comparisons_stay_linear_for_one_large_cluster(self):
        clusterer = CountingClusterer()
        rows = [
            {
                "id": index,
                "title": f"OpenAI 发布 GPT-9 模型，参数规模 9000 亿 第{index}版",
                "source_site": f"source-{index % 7}",
                "published_at": "2026-08-24 10:00:00",
                "content": "",
            }
            for index in range(1, 1001)
        ]

        clusters = clusterer.cluster(rows)

        self.assertEqual(len(clusters), 1)
        self.assertLess(clusterer.similarity_calls, 5_000)

    def test_historic_event_matching_prepares_features_and_caps_candidates(self):
        clusterer = CountingClusterer()
        candidates = [
            {"id": index, "canonical_news_id": index, "title": f"公司 {index} 发布季度报告"}
            for index in range(1, 2001)
        ]
        prepared = clusterer.prepare_existing_events(candidates)
        feature_calls_after_prepare = clusterer.feature_calls

        for index in range(100):
            clusterer.best_existing_event(
                {"id": 10_000 + index, "title": f"公司 {index + 1} 发布季度报告"},
                prepared,
            )

        self.assertEqual(feature_calls_after_prepare, 2000)
        self.assertEqual(clusterer.feature_calls - feature_calls_after_prepare, 100)
        self.assertLessEqual(clusterer.similarity_calls, 100 * clusterer.MAX_EXISTING_CANDIDATES)

    def test_fts_search_uses_the_virtual_table_as_the_candidate_source(self):
        class RecordingRepository(ReviewPublicRepository):
            def __init__(self):
                self.statements = []

            def execute(self, query: str, params: tuple = ()):
                self.statements.append(query)
                raise RuntimeError("captured")

        repository = RecordingRepository()
        with self.assertRaisesRegex(RuntimeError, "captured"):
            repository.search_public_entries(
                "OpenAI",
                "news",
                {"news": "daily-briefs", "article": "deep-reads"},
            )

        count_sql = " ".join(repository.statements[0].split()).lower()
        self.assertIn("r.id in (select rowid from review_entries_fts", count_sql)
        self.assertNotIn("join review_entries_fts", count_sql)

    def test_fts_search_remains_fast_at_thirty_thousand_reviews(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        try:
            create_current_schema(connection.cursor())
            connection.commit()
            current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            rows = [
                (
                    f"{'OpenAI' if index % 100 == 0 else 'Market'} report {index}",
                    "Body text",
                    "example",
                    f"https://example.test/search/{index}",
                    current_time,
                    current_time,
                    current_time,
                    current_time,
                    "news",
                    "daily-briefs",
                    "selected",
                    "sent",
                )
                for index in range(30_000)
            ]
            connection.executemany(
                """
                INSERT INTO review_entries (
                    title, content, source_site, source_url, published_at, scraped_at,
                    archived_at, queued_at, content_type, profile_slug,
                    review_status, delivery_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            connection.execute("UPDATE profile_publications SET enabled=1, is_public=1 WHERE profile_slug='daily-briefs'")
            publication_id = connection.execute("SELECT id FROM profile_publications WHERE profile_slug='daily-briefs'").fetchone()[0]
            connection.execute("INSERT INTO daily_reports(publication_key, date, type, title, content, news_count, profile_slug, publication_id) VALUES ('performance-public', ?, 'news', '日报', '正文', 30000, 'daily-briefs', ?)", (current_time[:10], publication_id))
            report_id = connection.execute('SELECT id FROM daily_reports').fetchone()[0]
            connection.execute("""INSERT INTO daily_report_items(report_id, review_entry_id, position, section, ranking_score, title, source_url, source_site, content_type)
                                  SELECT ?, id, id, '其他', 0, title, source_url, source_site, content_type FROM review_entries""", (report_id,))
            connection.commit()
            repository = ReviewPublicRepository(connection)
            arguments = ("OpenAI", "news", {"news": "daily-briefs", "article": "deep-reads"})
            repository.search_public_entries(*arguments)
            samples = []
            for _ in range(5):
                started = time.perf_counter()
                result = repository.search_public_entries(*arguments)
                samples.append(time.perf_counter() - started)

            self.assertEqual(result["total"], 300)
            self.assertLess(statistics.median(samples), 0.4)
        finally:
            connection.close()

    def test_status_only_review_update_does_not_rewrite_fts(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        try:
            create_current_schema(connection.cursor())
            connection.execute(
                """
                INSERT INTO review_entries (
                    title, content, source_site, source_url, published_at, scraped_at,
                    archived_at, queued_at, content_type, profile_slug
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "OpenAI 发布新模型",
                    "正文",
                    "example",
                    "https://example.test/fts",
                    "2026-08-24 10:00:00",
                    "2026-08-24 10:00:00",
                    "2026-08-24 10:00:00",
                    "2026-08-24 10:00:00",
                    "news",
                    "daily-briefs",
                ),
            )
            before = connection.total_changes

            connection.execute(
                "UPDATE review_entries SET review_status = 'processing' WHERE id = 1"
            )

            self.assertEqual(connection.total_changes - before, 1)
        finally:
            connection.close()

    def test_public_revision_changes_only_when_the_visible_projection_changes(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            create_current_schema(connection.cursor())
            connection.execute(
                """
                INSERT INTO review_entries (
                    title, content, source_site, source_url, published_at, scraped_at,
                    archived_at, queued_at, content_type, profile_slug,
                    review_status, delivery_status, review_summary
                ) VALUES (?, ?, ?, ?, datetime('now'), datetime('now'), datetime('now'),
                          datetime('now'), ?, ?, 'selected', 'sent', ?)
                """,
                (
                    "Visible item", "Body", "example", "https://example.test/revision",
                    "news", "daily-briefs", "Summary one",
                ),
            )
            repository = ReviewPublicRepository(connection)
            initial = repository.get_public_revision("news", "daily-briefs")

            connection.execute(
                "UPDATE review_entries SET review_claim_expires_at = datetime('now', '+5 minutes') WHERE id = 1"
            )
            self.assertEqual(
                repository.get_public_revision("news", "daily-briefs"),
                initial,
            )

            connection.execute(
                "UPDATE review_entries SET review_summary = 'Summary two' WHERE id = 1"
            )
            self.assertNotEqual(
                repository.get_public_revision("news", "daily-briefs"),
                initial,
            )
        finally:
            connection.close()

    def test_retention_prunes_expired_chains_but_preserves_recent_report_snapshots(self):
        connection = sqlite3.connect(":memory:", isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            create_current_schema(connection.cursor())
            news_id = connection.execute(
                """
                INSERT INTO news (
                    title, content, source_site, source_url, published_at, scraped_at, stage, type
                ) VALUES ('Old item', 'Body', 'example', 'https://example.test/old',
                          '2020-01-01 00:00:00', '2020-01-01 00:00:00', 'archived', 'news')
                """
            ).lastrowid
            event_id = connection.execute(
                """
                INSERT INTO content_events (
                    canonical_news_id, title, content, content_type, published_at,
                    first_seen_at, last_seen_at, source_count
                ) VALUES (?, 'Old item', 'Body', 'news', '2020-01-01 00:00:00',
                          '2020-01-01 00:00:00', '2020-01-01 00:00:00', 1)
                """,
                (news_id,),
            ).lastrowid
            connection.execute(
                "UPDATE news SET event_id = ?, event_similarity = 1, is_event_primary = 1 WHERE id = ?",
                (event_id, news_id),
            )
            connection.execute(
                "INSERT INTO event_sources(event_id, news_id, similarity, is_primary) VALUES (?, ?, 1, 1)",
                (event_id, news_id),
            )
            review_id = connection.execute(
                """
                INSERT INTO review_entries (
                    title, content, source_site, source_url, published_at, scraped_at,
                    archived_at, queued_at, content_type, source_item_id, event_id,
                    profile_slug, review_status, delivery_status, review_summary
                ) VALUES ('Old item', 'Body', 'example', 'https://example.test/old',
                          '2020-01-01 00:00:00', '2020-01-01 00:00:00',
                          '2020-01-01 00:00:00', '2020-01-01 00:00:00', 'news', ?, ?,
                          'daily-briefs', 'selected', 'sent', 'Snapshot summary')
                """,
                (news_id, event_id),
            ).lastrowid
            report_id = connection.execute(
                """
                INSERT INTO daily_reports(publication_key, date, type, title, content, news_count)
                VALUES ('retention-report', '2026-08-24', 'news', 'Current report', 'Report body', 1)
                """
            ).lastrowid
            connection.execute(
                """
                INSERT INTO daily_report_items (
                    report_id, review_entry_id, event_id, position, section, ranking_score,
                    source_count, title, source_url, content_type, review_summary
                ) VALUES (?, ?, ?, 1, 'Main', 1, 1, 'Old item',
                          'https://example.test/old', 'news', 'Snapshot summary')
                """,
                (report_id, review_id, event_id),
            )
            connection.execute(
                "INSERT INTO processing_logs(stage, action, created_at) VALUES ('old', 'old', '2020-01-01 00:00:00')"
            )
            repository = MaintenanceRepository(connection)

            repository.prune_operational_batch("2025-01-01 00:00:00", 500)
            repository.prune_event_batch("2025-01-01 00:00:00", 500)
            repository.prune_content_batch("2025-01-01 00:00:00", 500)
            repository.optimize_storage()

            self.assertEqual(connection.execute("SELECT COUNT(*) FROM processing_logs").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM content_events").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM news").fetchone()[0], 0)
            snapshot = connection.execute(
                "SELECT review_entry_id, event_id, title, review_summary FROM daily_report_items"
            ).fetchone()
            self.assertIsNone(snapshot["review_entry_id"])
            self.assertIsNone(snapshot["event_id"])
            self.assertEqual(snapshot["title"], "Old item")
            self.assertEqual(snapshot["review_summary"], "Snapshot summary")
        finally:
            connection.close()

    def test_api_composition_does_not_eagerly_import_optional_ai_or_browser_runtimes(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import json,sys,time; start=time.perf_counter(); "
                    "import backend.app.composition; "
                    "print(json.dumps({'seconds': time.perf_counter()-start, "
                    "'openai': 'openai' in sys.modules, "
                    "'playwright': any(name.startswith('playwright') for name in sys.modules)}))"
                ),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        metrics = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertFalse(metrics["openai"])
        self.assertFalse(metrics["playwright"])
        self.assertLess(metrics["seconds"], 2.5)

    def test_password_hashing_and_session_database_reads_run_in_fastapi_threadpool(self):
        from backend.app.routers import auth

        self.assertFalse(inspect.iscoroutinefunction(auth.login))
        self.assertFalse(inspect.iscoroutinefunction(auth.get_current_user))


class ScraperPerformanceRegressionTest(unittest.IsolatedAsyncioTestCase):
    class RuntimeSettings:
        @staticmethod
        def get_runtime():
            return {"scraper_concurrency": 2}

    class RuntimeRepository:
        @staticmethod
        def get_recent_news_urls(_site_name, limit=2000):
            return []

        @staticmethod
        def get_latest_news_url(_site_name):
            return None

    class StateRepository:
        def __init__(self):
            self.finished = []

        @staticmethod
        def claim_run(_name, _run_id, _worker_id):
            return True

        @staticmethod
        def heartbeat(_name, _run_id, _worker_id):
            return True

        def finish_run(self, name, run_id, payload):
            self.finished.append((name, run_id, payload))
            return True

    class RuntimeState:
        def __init__(self, definition):
            self.definition = definition

        @staticmethod
        def ensure_runtime_initialized():
            return None

        def require_scraper(self, _name):
            return self.definition

        @staticmethod
        def get_source_cooldown(_name):
            return {}

        @staticmethod
        def append_log(_name, _message):
            return None

        @staticmethod
        def append_logs(_name, _messages):
            return None

        @staticmethod
        def get_spider_status():
            return {}

    async def test_scraper_launches_never_exceed_the_configured_capacity(self):
        release = asyncio.Event()

        class BlockingScraper:
            site_name = "blocking"
            max_items = 1
            item_callback = None

            async def run(self):
                await release.wait()
                return []

        class Definition:
            @staticmethod
            def build_scraper():
                return BlockingScraper()

        state_repository = self.StateRepository()
        service = ScraperRunService(
            lambda: type("News", (), {"insert_news_batch": staticmethod(lambda _items: 0)})(),
            lambda: self.RuntimeRepository(),
            lambda: state_repository,
            self.RuntimeState(Definition()),
            self.RuntimeSettings(),
        )
        service.configure_worker("capacity-worker")

        self.assertTrue(service.launch_scraper("one", 1))
        self.assertTrue(service.launch_scraper("two", 1))
        self.assertFalse(service.launch_scraper("three", 1))
        self.assertEqual(service.available_launch_slots(), 0)

        release.set()
        await asyncio.gather(*list(service._running_tasks.values()))
        self.assertEqual(service.available_launch_slots(), 2)

    async def test_scraper_callback_and_return_buffer_write_each_item_once_in_bounded_batches(self):
        items = [
            {
                "title": f"item-{index}",
                "content": "content",
                "url": f"https://example.test/{index}",
                "published_at": "2026-08-24 10:00:00",
            }
            for index in range(53)
        ]

        class CallbackScraper:
            site_name = "callback"
            max_items = 100
            item_callback = None

            async def run(self):
                for item in items:
                    self.item_callback(dict(item))
                return items

        class Definition:
            @staticmethod
            def build_scraper():
                return CallbackScraper()

        class BatchRepository:
            def __init__(self):
                self.batches = []

            def insert_news_batch(self, batch):
                self.batches.append([item["url"] for item in batch])
                return len(batch)

        news_repository = BatchRepository()
        state_repository = self.StateRepository()
        service = ScraperRunService(
            lambda: news_repository,
            lambda: self.RuntimeRepository(),
            lambda: state_repository,
            self.RuntimeState(Definition()),
            self.RuntimeSettings(),
        )
        service.configure_worker("batch-worker")

        await service.run_scraper_task("callback", 100, "batch-run")

        self.assertEqual([len(batch) for batch in news_repository.batches], [20, 20, 13])
        written_urls = [url for batch in news_repository.batches for url in batch]
        self.assertEqual(len(written_urls), 53)
        self.assertEqual(len(set(written_urls)), 53)


if __name__ == "__main__":
    unittest.main()
