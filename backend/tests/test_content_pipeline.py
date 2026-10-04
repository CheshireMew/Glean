from __future__ import annotations

from contextlib import closing
import json
import re
import sqlite3
import tempfile
import threading
import unittest
import uuid
from datetime import datetime
from email.utils import format_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.composition import app_services
from backend.app.infrastructure.database import database, init_database
from backend.app.infrastructure.repositories import repositories
from backend.app.services.digest_planner_service import DigestPlannerService, DigestPolicy
from backend.app.services.llm import EditorialAIService
from backend.app.services.rss_source_service import rss_runtime_name
from backend.main import app

ai_provider_settings_service = app_services.ai_provider_settings
daily_report_service = app_services.daily_reports
event_clustering_service = app_services.event_clustering
editorial_profile_service = app_services.editorial_profiles
review_settings_service = app_services.review_settings
rss_source_service = app_services.rss_sources
scraper_registry_service = app_services.scraper_registry
scraper_run_service = app_services.scraper_runs


class LocalSourceAndAIHandler(BaseHTTPRequestHandler):
    server_version = "GleanTest/1.0"

    def log_message(self, format, *args):
        return

    def do_GET(self):
        if self.path != "/feed.xml":
            self.send_error(404)
            return
        published = format_datetime(datetime.now().astimezone())
        body = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Local Crypto Wire</title>
<item><title>美国 SEC 批准现货比特币 ETF</title><link>http://source.local/a</link><pubDate>{published}</pubDate><description>监管机构批准产品上市，文件给出了生效安排。</description></item>
<item><title>SEC 正式批准比特币现货 ETF</title><link>http://source.local/b</link><pubDate>{published}</pubDate><description>发行方确认产品获批，并披露首个交易日期。</description></item>
<item><title>故障事件：某项目发布测试公告</title><link>http://source.local/failure</link><pubDate>{published}</pubDate><description>这条内容用于验证单条模型失败不会阻塞其他事件。</description></item>
</channel></rss>""".encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/rss+xml; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path == "/fail/v1/chat/completions":
            self.send_response(503)
            self.end_headers()
            return
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length) or b"{}")
        messages = request.get("messages") or []
        system = next((item.get("content", "") for item in messages if item.get("role") == "system"), "")
        user = next((item.get("content", "") for item in messages if item.get("role") == "user"), "")
        if "新闻研究编辑" in system:
            citation_ids = [int(value) for value in re.findall(r"\[来源 (\d+)\]", user)]
            content = {
                "summary": "监管机构批准比特币现货 ETF，两家报道分别补充了生效与交易安排。",
                "why_it_matters": "产品获得监管放行，事件由多个来源交叉印证。",
                "background": "给定来源没有提供更早的背景材料。",
                "citation_ids": citation_ids,
            }
        elif "新闻审核助手" in system and "故障事件" in user:
            content = "not-json"
        elif "新闻审核助手" in system:
            content = {
                "passed": True,
                "score": 8,
                "reason": "监管决定具有直接市场影响",
                "category": "监管",
                "summary": "SEC 批准比特币现货 ETF",
            }
        else:
            content = {"ok": True}
        payload = json.dumps({
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 0,
            "model": request.get("model") or "test-model",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": json.dumps(content, ensure_ascii=False)}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class ContentPipelineIntegrationTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), LocalSourceAndAIHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=5)

    async def asyncSetUp(self):
        tools_dir = Path(r"D:\Tools")
        tools_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir = tempfile.TemporaryDirectory(dir=tools_dir)
        self.original_db_path = database.db_path
        database.db_path = str(Path(self.temp_dir.name) / "glean-test.db")
        init_database()

    async def asyncTearDown(self):
        database.db_path = self.original_db_path
        self.temp_dir.cleanup()

    async def test_real_source_to_public_digest_chain(self):
        base_url = f"http://127.0.0.1:{self.server.server_port}"
        ai_provider_settings_service.set_config({
            "providers": [{"name": "local", "api_key": "test-key", "base_url": f"{base_url}/v1", "model": "test-model"}],
            "analysis_concurrency": 2,
            "enrichment_concurrency": 2,
            "throttle_seconds": 0,
        })
        review_settings_service.set_config("优先保留明确的监管决定", 24, "news")
        editorial_profile_service.save_profile({
            "slug": "regulatory-research",
            "name": "监管研究",
            "content_type": "news",
            "review_prompt": "只保留能够形成监管研究线索的事件",
            "enrichment_prompt": "提炼监管决定、实施时间和市场影响",
            "min_score": 5,
            "max_items": 6,
            "max_per_category": 2,
            "max_per_source": 2,
            "enabled": True,
            "is_default": False,
        })
        source = rss_source_service.create_source({
            "slug": "local-crypto-wire",
            "display_name": "Local Crypto Wire",
            "feed_url": f"{base_url}/feed.xml",
            "site_url": base_url,
            "content_kind": "news",
            "parser_type": "generic",
            "default_limit": 10,
            "default_interval": 60,
            "enabled": True,
        })
        runtime_name = rss_runtime_name(source["slug"])
        definition = scraper_registry_service.require(runtime_name)
        self.assertEqual(definition.transport_kind, "rss")

        scraper_run_service.configure_worker("integration-test-worker")
        run_id = uuid.uuid4().hex
        self.assertTrue(repositories().scraper_state.claim_run(runtime_name, run_id, "integration-test-worker"))
        await scraper_run_service.run_scraper_task(runtime_name, 10, run_id)
        raw_sources = repositories().news_runtime.get_news_by_time_range(24, "news")
        self.assertEqual(len(raw_sources), 3)

        clustered = await event_clustering_service.cluster_content(24, 0.5, "news")
        self.assertEqual(clustered["stats"]["sources_clustered"], 3)
        event_payload = repositories().event_queries.list_groups(1, 20, None, None, "news")
        self.assertEqual(event_payload["total"], 2)
        multi_source_event = next(item for item in event_payload["results"] if len(item["sources"]) == 2)
        self.assertEqual(len(multi_source_event["sources"]), 2)

        transition = await app_services.pipeline.apply_blocklist(24, "news")
        self.assertEqual(transition["stats"]["review"], 4)
        review = await app_services.pipeline.run_review(24, "news")
        self.assertEqual(review["selected"], 2)
        self.assertEqual(review["enriched"], 2)
        self.assertEqual(review["failed"], 2)
        selected_profiles = repositories().review.execute(
            "SELECT profile_slug FROM review_entries WHERE event_id = ? AND review_status = 'selected' ORDER BY profile_slug",
            (multi_source_event["event"]["id"],),
        ).fetchall()
        self.assertEqual([row["profile_slug"] for row in selected_profiles], ["daily-briefs", "regulatory-research"])
        default_pending = repositories().push.get_pending_review_entries("news", "daily-briefs")
        self.assertEqual(len(default_pending), 1)
        self.assertEqual(default_pending[0]["profile_slug"], "daily-briefs")

        prepared = daily_report_service.prepare("news", repositories().config.get_system_time())
        self.assertIsNotNone(prepared)
        self.assertEqual(len(prepared.entries), 1)
        self.assertIn("2 个来源", prepared.content)
        report_id = daily_report_service.persist_success(prepared)
        self.assertGreater(report_id, 0)
        self.assertEqual(app_services.public_content.get_public_content('news', 20, 0)['total'], 0)
        publication = repositories().publications.get_publication_by_profile('daily-briefs')
        draft = app_services.editorial_workbench.create_draft({
            'publication_id': publication['id'], 'content_type': 'news', 'title': prepared.title,
            'items': [{'review_entry_id': entry['id'], 'position': index, 'included': True,
                       'section': '监管', 'overrides': {}} for index, entry in enumerate(prepared.entries)],
        }, 'integration-editor')
        await app_services.publication_workflow.publish_draft(draft['id'], website_only=True)

        with TestClient(app) as client:
            response = client.get("/api/public/content", params={"stream": "briefs", "limit": 20, "offset": 0})
            revision = response.json()["data"]["revision"]
            unchanged = client.get(
                "/api/public/content",
                params={"stream": "briefs", "limit": 1000, "known_revision": revision},
            )
            review_request_fields = client.get("/openapi.json").json()["components"]["schemas"]["ReviewRunRequest"]["properties"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(review_request_fields), {"hours", "kind"})
        public_items = response.json()["data"]["items"]
        self.assertEqual(len(public_items), 1)
        self.assertEqual(public_items[0]["source_count"], 2)
        self.assertEqual(len(public_items[0]["sources"]), 2)
        self.assertTrue(public_items[0]["enriched_summary"])
        self.assertEqual(len(public_items[0]["citations"]), 2)
        self.assertTrue(unchanged.json()["data"]["not_modified"])
        self.assertEqual(unchanged.json()["data"]["items"], [])

        reports = repositories().daily_reports.list_reports("news", 20, 0)
        self.assertEqual(reports["total"], 2)
        report_items = repositories().daily_reports.execute(
            "SELECT event_id, position, section, source_count FROM daily_report_items WHERE report_id = ?",
            (report_id,),
        ).fetchall()
        self.assertEqual(len(report_items), 1)
        self.assertEqual(report_items[0]["source_count"], 2)

    async def test_ai_provider_falls_back_to_next_endpoint(self):
        base_url = f"http://127.0.0.1:{self.server.server_port}"
        service = EditorialAIService(
            [
                {"name": "unavailable", "api_key": "test", "base_url": f"{base_url}/fail/v1", "model": "test-model"},
                {"name": "working", "api_key": "test", "base_url": f"{base_url}/v1", "model": "test-model"},
            ],
            concurrency=1,
        )
        try:
            result = await service.test_connection()
        finally:
            await service.close()
        self.assertTrue(result["ok"])

    async def test_legacy_orphan_review_is_preserved_during_profile_migration(self):
        with closing(sqlite3.connect(database.db_path)) as connection:
            connection.execute("ALTER TABLE news ADD COLUMN duplicate_of INTEGER")
            connection.execute("ALTER TABLE news ADD COLUMN ai_score INTEGER")
            connection.execute("DROP TABLE review_entries")
            connection.execute(
                """
                CREATE TABLE review_entries (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    content TEXT,
                    source_site TEXT NOT NULL,
                    source_url TEXT NOT NULL UNIQUE,
                    published_at DATETIME NOT NULL,
                    scraped_at DATETIME NOT NULL,
                    archived_at DATETIME NOT NULL,
                    queued_at DATETIME NOT NULL,
                    is_marked_important BOOLEAN,
                    site_importance_flag TEXT,
                    content_type TEXT DEFAULT 'news',
                    source_item_id INTEGER,
                    review_status TEXT DEFAULT 'pending',
                    review_summary TEXT,
                    review_reason TEXT,
                    review_score INTEGER,
                    review_category TEXT,
                    review_tags TEXT,
                    delivery_status TEXT DEFAULT 'pending',
                    delivered_at TIMESTAMP
                )
                """
            )
            connection.execute("DELETE FROM schema_migrations")
            connection.execute("INSERT INTO schema_migrations (version) VALUES ('2026.08.11.1')")
            connection.commit()
            connection.execute("CREATE INDEX idx_review_source ON review_entries(source_site)")
            connection.execute("CREATE INDEX idx_review_queue ON review_entries(review_status)")
            connection.execute("CREATE INDEX idx_review_delivery ON review_entries(delivery_status)")
            connection.execute(
                """
                INSERT INTO review_entries (
                    id, title, content, source_site, source_url, published_at, scraped_at,
                    archived_at, queued_at, content_type, review_status, delivery_status
                ) VALUES (41, '孤立旧审核记录', '原始新闻行已丢失', 'legacy-source',
                          'https://legacy.local/orphan', '2026-08-10 08:00:00',
                          '2026-08-10 08:01:00', '2026-08-10 08:02:00',
                          '2026-08-10 08:03:00', 'news', 'selected', 'pending')
                """
            )
            connection.commit()

        init_database()

        migrated = repositories().review.execute(
            "SELECT id, event_id, profile_slug, source_item_id FROM review_entries WHERE id = 41"
        ).fetchone()
        self.assertIsNotNone(migrated)
        self.assertGreater(migrated["event_id"], 0)
        self.assertGreater(migrated["source_item_id"], 0)
        self.assertEqual(migrated["profile_slug"], "daily-briefs")
        event_sources = repositories().review.execute(
            "SELECT COUNT(*) AS total FROM event_sources WHERE event_id = ?",
            (migrated["event_id"],),
        ).fetchone()
        self.assertEqual(event_sources["total"], 1)
        profile_index = repositories().review.execute(
            "SELECT tbl_name FROM sqlite_master WHERE type = 'index' AND name = 'idx_review_profile'"
        ).fetchone()
        self.assertEqual(profile_index["tbl_name"], "review_entries")
        legacy_table = repositories().review.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'legacy_review_entries_event_migration'"
        ).fetchone()
        self.assertIsNone(legacy_table)
        news_columns = repositories().review.execute("PRAGMA table_info(news)").fetchall()
        self.assertNotIn("duplicate_of", [row["name"] for row in news_columns])
        self.assertNotIn("ai_score", [row["name"] for row in news_columns])

    async def test_digest_balances_category_and_source_when_choices_exist(self):
        entries = [
            {"id": 1, "title": "A1", "review_score": 8, "review_category": "监管", "source_site": "S1", "published_at": "2026-08-11 10:00:00"},
            {"id": 2, "title": "A2", "review_score": 8, "review_category": "监管", "source_site": "S1", "published_at": "2026-08-11 09:00:00"},
            {"id": 3, "title": "A3", "review_score": 8, "review_category": "监管", "source_site": "S1", "published_at": "2026-08-11 08:00:00"},
            {"id": 4, "title": "B1", "review_score": 8, "review_category": "安全", "source_site": "S2", "published_at": "2026-08-11 07:00:00"},
            {"id": 5, "title": "C1", "review_score": 8, "review_category": "融资", "source_site": "S3", "published_at": "2026-08-11 06:00:00"},
        ]
        plan = DigestPlannerService().plan(entries, "news", DigestPolicy(max_items=4, max_per_category=2, max_per_source=2))
        self.assertEqual([entry["id"] for entry in plan], [1, 2, 4, 5])

        concentrated = DigestPlannerService().plan(
            entries[:3], "news", DigestPolicy(max_items=3, max_per_category=1, max_per_source=1, critical_score=10)
        )
        self.assertEqual([entry["id"] for entry in concentrated], [1])


if __name__ == "__main__":
    unittest.main()
