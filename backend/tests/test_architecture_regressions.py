from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
import json
import re
import sqlite3
import tempfile
import unittest
from unittest.mock import ANY, AsyncMock, patch

from fastapi.testclient import TestClient
from shared.content_contract import (
    ARCHIVED_STAGE,
    ENRICHMENT_STATUS_COMPLETED,
    ENRICHMENT_STATUS_PENDING,
    EXPORT_SCOPE_SELECTED,
    REVIEW_STATUS_SELECTED,
)

from backend.app.composition import app_services
from backend.app.core.config import settings
from backend.app.infrastructure.database import database, init_database
from backend.app.infrastructure.event_clustering import EventCluster, EventMember, build_event_clusterer
from backend.app.infrastructure.repositories import repositories, transactional_repositories
from backend.app.services.auth_service import AuthService
from backend.main import app

content_lifecycle_service = app_services.content_lifecycle
content_transition_service = app_services.content_transitions
delivery_operation_service = app_services.delivery_operations
editorial_profile_service = app_services.editorial_profiles
scraper_run_service = app_services.scraper_runs
scraper_runtime_state_service = app_services.scraper_runtime_state
telegram_gateway_service = app_services.telegram_gateway


class ArchitectureRegressionTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        tools_dir = Path(r"D:\Tools")
        tools_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir = tempfile.TemporaryDirectory(dir=tools_dir)
        self.original_db_path = database.db_path
        database.db_path = str(Path(self.temp_dir.name) / "architecture.db")
        init_database()

    async def asyncTearDown(self):
        database.db_path = self.original_db_path
        self.temp_dir.cleanup()

    def _seed_event(self, title: str, suffix: str, content_kind: str = "news") -> tuple[int, int, int]:
        news_id = repositories().news.insert_news(
            {
                "title": title,
                "content": f"{title} 的完整正文",
                "source_site": "Regression Source",
                "url": f"https://example.test/{suffix}",
                "published_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "type": content_kind,
            }
        )
        row = dict(repositories().news.execute("SELECT * FROM news WHERE id = ?", (news_id,)).fetchone())
        cluster = EventCluster(
            primary=row,
            members=[EventMember(item=row, similarity=1.0)],
            event_key=f"regression:{suffix}",
        )
        content_transition_service.persist_event_clusters(
            [cluster], build_event_clusterer(0.5), content_kind, 24
        )
        event_id = int(repositories().events.get_event_id_for_news(news_id))
        archive_id = int(
            repositories().archive_query.execute(
                "SELECT id FROM archive_entries WHERE event_id = ?", (event_id,)
            ).fetchone()["id"]
        )
        return int(news_id), event_id, archive_id

    async def test_blacklist_scope_and_blocked_restore_reenter_review(self):
        admin = repositories().blacklist
        self.assertTrue(admin.add_blacklist_keyword("恢复测试", "contains", "news"))
        self.assertTrue(admin.add_blacklist_keyword("恢复测试", "contains", "article"))
        self.assertFalse(admin.add_blacklist_keyword("恢复测试", "contains", "news"))

        _, _, archive_id = self._seed_event("恢复测试：应先被拦截", "restore")
        result = await app_services.pipeline.apply_blocklist(24, "news")
        self.assertEqual(result["stats"]["blocked"], 1)
        self.assertEqual(
            repositories().archive_query.get_entry(archive_id)["archive_status"], "blocked"
        )

        self.assertTrue(content_lifecycle_service.restore_blocked_entry(archive_id))
        archive = repositories().archive_query.get_entry(archive_id)
        self.assertEqual(archive["archive_status"], "reviewed")
        self.assertEqual(archive["restored_from_blocklist"], 1)
        pending = repositories().review.execute(
            "SELECT COUNT(*) AS total FROM review_entries WHERE event_id = ? AND review_status = 'pending'",
            (archive["event_id"],),
        ).fetchone()["total"]
        self.assertGreaterEqual(pending, 1)

    async def test_review_delete_is_local_and_daily_snapshot_is_immutable(self):
        editorial_profile_service.save_profile(
            {
                "slug": "secondary-review",
                "name": "第二审核档案",
                "content_type": "news",
                "review_prompt": "保留",
                "enrichment_prompt": "",
                "min_score": 5,
                "max_items": 10,
                "max_per_category": 4,
                "max_per_source": 4,
                "enabled": True,
                "is_default": False,
            }
        )
        news_id, event_id, _ = self._seed_event("不可变日报测试", "immutable")
        await app_services.pipeline.apply_blocklist(24, "news")
        reviews = [
            dict(row)
            for row in repositories().review.execute(
                "SELECT * FROM review_entries WHERE event_id = ? ORDER BY id", (event_id,)
            ).fetchall()
        ]
        self.assertEqual(len(reviews), 2)
        target = reviews[0]
        repositories().review.execute(
            "UPDATE review_entries SET review_status = 'selected', enrichment_status = 'completed', review_score = 8 WHERE id = ?",
            (target["id"],),
        )
        target.update({"review_score": 8, "source_count": 1})
        report_id = repositories().daily_reports.save_report(
            "regression:immutable", "2026-08-12", "news", "历史日报", "冻结正文", 1
        )
        repositories().daily_reports.save_report_items(report_id, [target])

        self.assertTrue(content_lifecycle_service.delete_review_entry(target["id"]))
        self.assertIsNotNone(repositories().event_queries.get_event(event_id))
        self.assertIsNotNone(repositories().news.execute("SELECT id FROM news WHERE id = ?", (news_id,)).fetchone())
        self.assertEqual(
            repositories().review.execute(
                "SELECT COUNT(*) AS total FROM review_entries WHERE event_id = ?", (event_id,)
            ).fetchone()["total"],
            1,
        )
        report = repositories().daily_reports.list_reports("news", 10, 0)["items"][0]
        self.assertEqual(report["content"], "冻结正文")
        self.assertEqual(report["items"][0]["title"], "不可变日报测试")
        self.assertIsNone(report["items"][0]["id"])

    async def test_primary_source_replacement_uses_the_shared_domain_ranking(self):
        primary_id, event_id, _ = self._seed_event("原始主来源", "primary-ranking")
        candidate_ids = []
        for suffix, important, content in (
            ("important", True, "短内容"),
            ("long", False, "长内容" * 200),
        ):
            news_id = repositories().news.insert_news(
                {
                    "title": f"候选-{suffix}",
                    "content": content,
                    "source_site": f"Source-{suffix}",
                    "url": f"https://example.test/{suffix}",
                    "published_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "is_marked_important": important,
                    "type": "news",
                }
            )
            repositories().events.execute(
                "INSERT INTO event_sources (event_id, news_id, similarity, is_primary) VALUES (?, ?, 0.9, 0)",
                (event_id, news_id),
            )
            repositories().events.execute(
                "UPDATE news SET stage = ?, event_id = ?, event_similarity = 0.9, is_event_primary = 0 WHERE id = ?",
                (ARCHIVED_STAGE, event_id, news_id),
            )
            candidate_ids.append(news_id)

        self.assertTrue(content_lifecycle_service.delete_incoming_entry(primary_id))
        event = repositories().event_queries.get_event(event_id)
        self.assertEqual(event["canonical_news_id"], candidate_ids[0])
        archive = repositories().archive_query.execute(
            "SELECT source_item_id FROM archive_entries WHERE event_id = ?", (event_id,)
        ).fetchone()
        self.assertEqual(archive["source_item_id"], candidate_ids[0])

    async def test_selected_export_and_delivery_share_enrichment_scope_semantics(self):
        _, event_id, _ = self._seed_event("范围真源", "scope-plan")
        await app_services.pipeline.apply_blocklist(24, "news")
        review_id = repositories().review.execute(
            "SELECT id FROM review_entries WHERE event_id = ? LIMIT 1", (event_id,)
        ).fetchone()["id"]
        repositories().review.execute(
            "UPDATE review_entries SET review_status = ?, enrichment_status = ? WHERE id = ?",
            (REVIEW_STATUS_SELECTED, ENRICHMENT_STATUS_PENDING, review_id),
        )
        self.assertEqual(
            list(
                repositories().content_queries.stream_export(
                    EXPORT_SCOPE_SELECTED, None, None, None, None, "news", ["id"]
                )
            ),
            [],
        )
        repositories().review.execute(
            "UPDATE review_entries SET enrichment_status = ? WHERE id = ?",
            (ENRICHMENT_STATUS_COMPLETED, review_id),
        )
        self.assertEqual(
            list(
                repositories().content_queries.stream_export(
                    EXPORT_SCOPE_SELECTED, None, None, None, None, "news", ["id"]
                )
            ),
            [{"id": review_id}],
        )

    async def test_typed_output_refs_and_delivery_lease_prevent_duplicate_senders(self):
        news_id = repositories().news.insert_news(
            {
                "title": "仍在采集池",
                "content": "内容",
                "source_site": "Regression Source",
                "url": "https://example.test/incoming-output",
                "published_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "type": "news",
            }
        )
        resolved = repositories().review_delivery.get_entries_by_refs(
            [{"scope": "incoming", "id": news_id}]
        )
        self.assertEqual(resolved[0]["output_ref"], {"scope": "incoming", "id": news_id})

        operation = delivery_operation_service.prepare(
            "regression:single-sender", "test", "news", ["one", "two"], []
        )
        original_send = telegram_gateway_service.send_message_result
        calls: list[str] = []

        async def delayed_send(message: str, parse_mode: str = "HTML"):
            calls.append(message)
            await asyncio.sleep(0.05)
            return {"status": "sent", "error": None, "remote_message_id": str(len(calls))}

        try:
            telegram_gateway_service.send_message_result = delayed_send
            results = await asyncio.gather(
                delivery_operation_service.send(operation["operation_key"]),
                delivery_operation_service.send(operation["operation_key"]),
            )
        finally:
            telegram_gateway_service.send_message_result = original_send
        self.assertEqual(calls, ["one", "two"])
        self.assertIn("sent", {result["status"] for result in results})
        self.assertTrue({result["status"] for result in results} <= {"sent", "in_progress"})

    async def test_nested_transaction_uses_savepoint(self):
        with transactional_repositories() as outer:
            outer.config.set_config("regression.outer", "kept")
            try:
                with transactional_repositories() as inner:
                    inner.config.set_config("regression.inner", "rolled-back")
                    raise RuntimeError("inner failure")
            except RuntimeError:
                pass
            self.assertEqual(outer.config.get_config("regression.outer"), "kept")
            self.assertIsNone(outer.config.get_config("regression.inner"))
        self.assertEqual(repositories().config.get_config("regression.outer"), "kept")

    async def test_repository_constraint_error_does_not_rollback_caller_transaction(self):
        with transactional_repositories() as tx_repos:
            tx_repos.config.set_config("regression.transaction.before", "kept")
            with self.assertRaises(sqlite3.IntegrityError):
                tx_repos.config.execute(
                    "INSERT INTO system_config (key, value) VALUES (?, ?)",
                    ("regression.transaction.before", "duplicate"),
                )
            tx_repos.config.set_config("regression.transaction.after", "also-kept")

        self.assertEqual(
            repositories().config.get_config("regression.transaction.before"), "kept"
        )
        self.assertEqual(
            repositories().config.get_config("regression.transaction.after"), "also-kept"
        )

    async def test_database_rejects_invalid_operational_domain_values(self):
        operation = delivery_operation_service.prepare(
            "regression:domain-constraints", "test", "news", ["part"], []
        )
        conn = database.connect()
        try:
            invalid_statements = (
                ("UPDATE editorial_profiles SET max_items = 0 WHERE slug = 'daily-briefs'", ()),
                ("UPDATE delivery_operations SET sent_parts = total_parts + 1 WHERE id = ?", (operation["id"],)),
                (
                    "INSERT INTO scraper_runtime_state (scraper_name, status) VALUES ('invalid-state', 'stuck')",
                    (),
                ),
                (
                    "INSERT INTO scraper_runtime_commands (scraper_name, command_type, status) VALUES ('invalid-command', 'restart', 'pending')",
                    (),
                ),
                (
                    "UPDATE rss_sources SET default_interval = 0 WHERE id = (SELECT id FROM rss_sources LIMIT 1)",
                    (),
                ),
            )
            for statement, params in invalid_statements:
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(statement, params)
        finally:
            conn.close()

    async def test_scraper_returned_rows_are_reconciled_even_after_buffer_replacement(self):
        class ReplacingBufferScraper:
            site_name = "replacement-source"
            max_items = 1
            existing_urls = set()
            last_news_url = None
            incremental_mode = True
            used_result_buffer = True

            async def run(self):
                return [
                    {
                        "title": "最终列表仍需落库",
                        "content": "正文",
                        "url": "https://example.test/reconciled",
                        "published_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                ]

        class Definition:
            @staticmethod
            def build_scraper():
                return ReplacingBufferScraper()

        original_require = scraper_runtime_state_service.require_scraper
        try:
            scraper_runtime_state_service.require_scraper = lambda _: Definition()
            scraper_run_service.configure_worker("reconcile-worker")
            run_id = "reconcile-run"
            self.assertTrue(
                repositories().scraper_state.claim_run(
                    "replacement-runtime", run_id, "reconcile-worker"
                )
            )
            await scraper_run_service.run_scraper_task("replacement-runtime", 1, run_id)
        finally:
            scraper_runtime_state_service.require_scraper = original_require
        row = repositories().news.execute(
            "SELECT source_site FROM news WHERE source_url = 'https://example.test/reconciled'"
        ).fetchone()
        self.assertEqual(row["source_site"], "replacement-source")

    async def test_review_table_rebuild_preserves_child_audit_rows(self):
        _, event_id, _ = self._seed_event("迁移保留子记录", "migration-child")
        await app_services.pipeline.apply_blocklist(24, "news")
        review = dict(
            repositories().review.execute(
                "SELECT * FROM review_entries WHERE event_id = ? LIMIT 1", (event_id,)
            ).fetchone()
        )
        report_id = repositories().daily_reports.save_report(
            "regression:migration", "2026-08-12", "news", "迁移日报", "正文", 1
        )
        repositories().daily_reports.save_report_items(report_id, [review])
        repositories().push.log_push_status(
            review["id"], "telegram", "failed", "legacy audit", "regression:migration-push"
        )

        conn = sqlite3.connect(database.db_path)
        try:
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute("PRAGMA legacy_alter_table=ON")
            for trigger in (
                "review_entries_fts_insert", "review_entries_fts_delete", "review_entries_fts_update",
                "review_domain_insert", "review_domain_update",
            ):
                conn.execute(f"DROP TRIGGER IF EXISTS {trigger}")
            conn.execute("DROP TABLE IF EXISTS review_entries_fts")
            conn.execute("ALTER TABLE review_entries RENAME TO current_review_entries")
            conn.execute("CREATE TABLE review_entries AS SELECT * FROM current_review_entries")
            conn.execute("DROP TABLE current_review_entries")
            conn.execute("DELETE FROM schema_migrations")
            conn.execute("INSERT INTO schema_migrations(version) VALUES ('2026.08.11.1')")
            conn.commit()
        finally:
            conn.close()

        init_database()
        conn = database.connect()
        try:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM daily_report_items WHERE report_id = ?", (report_id,)).fetchone()[0],
                1,
            )
            self.assertEqual(
                conn.execute("SELECT review_entry_id FROM push_logs WHERE operation_key = 'regression:migration-push'").fetchone()[0],
                review["id"],
            )
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
        finally:
            conn.close()

    async def test_api_contracts_and_command_http_semantics(self):
        repositories().config.set_config("admin_username", "test-admin")
        repositories().config.set_config("admin_password", AuthService.hash_password("test-password-1234"))
        token = AuthService(repositories().config, repositories().auth).create_access_token(
            {"sub": "test-admin"}
        )
        headers = {"Authorization": f"Bearer {token}"}
        repositories().runtime_leases.acquire(
            "worker",
            "api-contract-worker",
            30,
            owner_version=settings.APP_VERSION,
            runtime_status="ready",
        )
        with TestClient(app) as client:
            spiders = client.get("/api/spiders", headers=headers)
            accepted = client.post(
                "/api/spiders/run/techflow", headers=headers, json={"items": 1}
            )
            duplicate = client.post(
                "/api/spiders/run/techflow", headers=headers, json={"items": 1}
            )
            single_character = client.get("/api/public/search", params={"query": "x"})
            invalid = client.get("/api/public/search", params={"query": ""})
            schema = client.get("/openapi.json").json()

        self.assertEqual(spiders.status_code, 200)
        self.assertTrue(spiders.json()["success"])
        self.assertIn("spiders", spiders.json()["data"])
        self.assertEqual(accepted.status_code, 202)
        self.assertEqual(accepted.json()["code"], 202)
        self.assertIsInstance(accepted.json()["data"]["command_id"], int)
        self.assertEqual(duplicate.status_code, 409)
        self.assertFalse(duplicate.json()["success"])
        self.assertEqual(single_character.status_code, 200)
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(invalid.json()["error"]["type"], "RequestValidationError")
        response_202 = schema["paths"]["/api/spiders/run/{name}"]["post"]["responses"]["202"]
        self.assertEqual(
            response_202["content"]["application/json"]["schema"]["$ref"],
            "#/components/schemas/APIEnvelope_ScraperCommandData_",
        )

    async def test_connection_checks_consume_drafts_without_persisting_them(self):
        ai_draft = {
            "providers": [{
                "name": "draft",
                "api_key": "draft-key",
                "base_url": "https://draft.example/v1",
                "model": "draft-model",
            }],
            "analysis_concurrency": 7,
            "enrichment_concurrency": 4,
            "throttle_seconds": 0.5,
        }
        telegram_draft = {
            "bot_token": "draft-token",
            "chat_id": "draft-chat",
            "enabled": False,
        }
        ai_before = app_services.ai_provider_settings.get_config(include_secrets=True)
        telegram_before = app_services.telegram_settings.get_config()

        with patch("backend.app.services.ai_pipeline_service.EditorialAIService") as ai_service_class:
            ai_service = ai_service_class.return_value
            ai_service.test_connection = AsyncMock(return_value={"ok": True, "message": "连接成功"})
            ai_service.close = AsyncMock()
            result = await app_services.ai_pipeline.test_ai_connection(ai_draft)

        self.assertTrue(result["ok"])
        ai_service_class.assert_called_once_with(ai_draft["providers"], 7, 0.5, ANY, app_services.ai_budget)

        with patch("backend.app.services.telegram_gateway_service.TelegramBot") as bot_class:
            bot_class.return_value.send_message = AsyncMock(return_value=True)
            result = await app_services.telegram_gateway.send_test_message(telegram_draft)

        self.assertEqual(result["message"], "测试消息发送成功")
        bot_class.assert_called_once_with("draft-token", "draft-chat")
        self.assertEqual(app_services.ai_provider_settings.get_config(include_secrets=True), ai_before)
        self.assertEqual(app_services.telegram_settings.get_config(), telegram_before)

        repositories().config.set_config("admin_username", "test-admin")
        repositories().config.set_config("admin_password", AuthService.hash_password("test-password-1234"))
        token = AuthService(repositories().config, repositories().auth).create_access_token(
            {"sub": "test-admin"}
        )
        headers = {"Authorization": f"Bearer {token}"}
        with (
            patch.object(app_services.ai_pipeline, "test_ai_connection", AsyncMock(return_value={"ok": True, "message": "连接成功"})) as ai_test,
            patch.object(app_services.telegram_gateway, "send_test_message", AsyncMock(return_value={"message": "测试消息发送成功"})) as telegram_test,
            TestClient(app) as client,
        ):
            ai_response = client.post("/api/integration/ai/test", headers=headers, json=ai_draft)
            telegram_response = client.post("/api/delivery/test", headers=headers, json=telegram_draft)

        self.assertEqual(ai_response.status_code, 200)
        self.assertEqual(telegram_response.status_code, 200)
        ai_test.assert_awaited_once_with({
            **ai_draft,
            "providers": [{
                **ai_draft["providers"][0],
                "input_price_per_million": 0,
                "output_price_per_million": 0,
            }],
        })
        telegram_test.assert_awaited_once_with(telegram_draft)

    async def test_frontend_operation_registry_matches_concrete_openapi_contracts(self):
        operations_path = Path(__file__).resolve().parents[2] / "frontend" / "src" / "api" / "operations.json"
        operations = json.loads(operations_path.read_text(encoding="utf-8"))
        schema = app.openapi()

        def normalized(path: str) -> str:
            return re.sub(r"\{[^}]+\}", "{}", path)

        for operation_id, operation in operations.items():
            expected_path = normalized(f"/api{operation['path']}")
            matches = [path for path in schema["paths"] if normalized(path) == expected_path]
            self.assertEqual(len(matches), 1, operation_id)
            path = matches[0]
            method = operation["method"]
            self.assertIn(method, schema["paths"][path], operation_id)
            responses = schema["paths"][path][method]["responses"]
            success = next(responses[code] for code in sorted(responses) if code.startswith("2"))
            json_schema = success.get("content", {}).get("application/json", {}).get("schema")
            self.assertIsNotNone(json_schema, operation_id)
            if operation_id == "exportContent":
                self.assertEqual(json_schema.get("type"), "array")
                continue
            reference = json_schema.get("$ref", "")
            self.assertTrue(reference.startswith("#/components/schemas/APIEnvelope_"), operation_id)
            self.assertNotEqual(reference, "#/components/schemas/APIEnvelope", operation_id)

        for path, path_item in schema["paths"].items():
            if not path.startswith("/api/") or path.endswith("/rss.xml"):
                continue
            for method, operation in path_item.items():
                if method not in {"get", "post", "put", "patch", "delete"}:
                    continue
                responses = operation["responses"]
                success = next(responses[code] for code in sorted(responses) if code.startswith("2"))
                response_schema = success.get("content", {}).get("application/json", {}).get("schema", {})
                if path == "/api/content/export":
                    self.assertEqual(response_schema.get("type"), "array")
                else:
                    self.assertTrue(
                        response_schema.get("$ref", "").startswith("#/components/schemas/APIEnvelope_"),
                        f"{method.upper()} {path}",
                    )

    async def test_read_endpoints_serialize_through_their_declared_dtos(self):
        repositories().config.set_config("admin_username", "test-admin")
        repositories().config.set_config("admin_password", AuthService.hash_password("test-password-1234"))
        token = AuthService(repositories().config, repositories().auth).create_access_token(
            {"sub": "test-admin"}
        )
        headers = {"Authorization": f"Bearer {token}"}
        protected_requests = (
            ("/api/system/timezone", {}),
            ("/api/delivery/schedule", {}),
            ("/api/config/automation", {}),
            ("/api/integration/telegram", {}),
            ("/api/integration/ai", {}),
            ("/api/editorial/profiles", {}),
            ("/api/review/settings", {}),
            ("/api/rss/sources", {}),
            ("/api/content/overview", {}),
            ("/api/content/stats", {}),
            ("/api/content/incoming", {}),
            ("/api/content/events", {}),
            ("/api/content/archive", {}),
            ("/api/content/blocked", {}),
            ("/api/content/review", {}),
            ("/api/content/decisions", {"decision": "selected"}),
            ("/api/content/blocklist", {}),
            ("/api/spiders", {}),
            ("/api/spiders/status", {}),
            ("/api/delivery/operations", {}),
            ("/api/integration/analyst/keys", {}),
        )
        with TestClient(app) as client:
            for path, params in protected_requests:
                response = client.get(path, params=params, headers=headers)
                self.assertEqual(response.status_code, 200, f"{path}: {response.text}")
                self.assertTrue(response.json()["success"], path)

    async def test_public_reports_search_and_paginate_on_the_server(self):
        publication = repositories().publications.get_publication_by_profile('daily-briefs')
        public_fields = {'profile_slug': 'daily-briefs', 'publication_id': publication['id']}
        repositories().daily_reports.save_report(
            "report:alpha", "2026-08-23", "news", "Alpha protocol", "first body", 0, **public_fields
        )
        repositories().daily_reports.save_report(
            "report:beta", "2026-08-22", "news", "Beta market", "second body", 0, **public_fields
        )
        repositories().daily_reports.save_report('report:internal', '2026-08-24', 'news', 'Internal protocol', 'private body', 0)
        with TestClient(app) as client:
            public_config = client.get("/api/public/config")
            first = client.get(
                "/api/public/reports",
                params={"kind": "news", "query": "protocol", "limit": 1, "offset": 0},
            )
            empty_tail = client.get(
                "/api/public/reports",
                params={"kind": "news", "query": "protocol", "limit": 1, "offset": 1},
            )
        self.assertEqual(public_config.status_code, 200)
        self.assertEqual(public_config.json()["data"]["site_url"], settings.PUBLIC_SITE_URL)
        self.assertEqual(public_config.json()["data"]["links"], settings.PUBLIC_LINKS)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["data"]["total"], 1)
        self.assertEqual(first.json()["data"]["items"][0]["title"], "Alpha protocol")
        self.assertEqual(empty_tail.json()["data"]["items"], [])

    async def test_legacy_local_timestamps_are_normalized_exactly_once(self):
        news_id = repositories().news.insert_news(
            {
                "title": "时间迁移",
                "content": "正文",
                "source_site": "Regression Source",
                "url": "https://example.test/time-migration",
                "published_at": "2026-08-12 08:00:00",
            }
        )
        conn = database.connect()
        try:
            conn.execute(
                "UPDATE news SET published_at = '2026-08-12 08:00:00', scraped_at = '2026-08-12 09:00:00' WHERE id = ?",
                (news_id,),
            )
            conn.execute("DELETE FROM system_config WHERE key = 'system.timestamps.utc_normalized'")
            conn.execute("DELETE FROM schema_migrations")
            conn.execute("INSERT INTO schema_migrations (version) VALUES ('2026.08.11.1')")
        finally:
            conn.close()
        init_database()
        first = repositories().news.execute(
            "SELECT published_at, scraped_at FROM news WHERE id = ?", (news_id,)
        ).fetchone()
        self.assertEqual(first["published_at"], "2026-08-12 00:00:00")
        self.assertEqual(first["scraped_at"], "2026-08-12 01:00:00")
        init_database()
        second = repositories().news.execute(
            "SELECT published_at, scraped_at FROM news WHERE id = ?", (news_id,)
        ).fetchone()
        self.assertEqual(tuple(second), tuple(first))


if __name__ == "__main__":
    unittest.main()
