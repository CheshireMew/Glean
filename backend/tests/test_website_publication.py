from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from backend.app.composition import AppServices
from backend.app.core.exceptions import ConflictError, NotFoundError, ValidationError
from backend.app.infrastructure.database import database, init_database
from backend.app.infrastructure.repositories import repositories, transactional_repositories
from backend.app.infrastructure.repository_impl.daily_report_repository import DailyReportRepository


class WebsitePublicationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(dir=r"D:\Tools")
        self.original_db = database.db_path
        database.db_path = str(Path(self.temp_dir.name) / "website.db")
        init_database()
        self.services = AppServices()
        repositories().news.insert_news({
            "title": "开源模型发布", "content": "发布模型权重与评估方法。", "source_site": "Official Wire",
            "url": "https://example.test/model", "published_at": datetime.now(timezone.utc).isoformat(), "type": "article",
        })
        await self.services.pipeline.cluster_content(24, 0.85, "article")
        await self.services.pipeline.apply_blocklist(24, "article")
        self.entry = dict(repositories().review.execute("SELECT * FROM review_entries LIMIT 1").fetchone())
        self.publication = next(p for p in self.services.publications.list_publications() if p["content_type"] == "article")

    async def asyncTearDown(self):
        database.db_path = self.original_db
        self.temp_dir.cleanup()

    def select(self):
        return self.services.editorial_workbench.update_entry(self.entry["id"], {
            "review_status": "selected", "review_summary": "发布开源模型权重和评估方法。",
            "review_reason": "包含可复现的模型使用资料。", "change_note": "人工审核",
        }, "editor")

    def draft(self):
        return self.services.editorial_workbench.create_draft({
            "publication_id": self.publication["id"], "content_type": "article", "title": "开源精选",
            "items": [{"review_entry_id": self.entry["id"], "position": 0, "included": True, "section": "模型", "overrides": {}}],
        }, "editor")

    def public(self):
        return self.services.public_content.get_public_content("article", 20, 0)

    async def test_manual_review_to_website_is_persistent_and_does_not_deliver(self):
        before = self.public()
        selected = self.select()
        self.assertEqual(len(selected["revisions"]), 2)
        draft = self.draft()
        self.assertEqual(self.public()["total"], 0)
        with patch.object(self.services.publication_channel_gateway, "send_message_result", new_callable=AsyncMock) as send:
            result = await self.services.publication_workflow.publish_draft(draft["id"], website_only=True)
            repeat = await self.services.publication_workflow.publish_draft(draft["id"], website_only=True)
            send.assert_not_called()
        self.assertEqual(result["report_id"], repeat["report_id"])
        self.assertEqual(result["operations"], [])
        # Read through a new composition root, independent of any service memory.
        self.services = AppServices()
        public = self.public()
        self.assertEqual(public["total"], 1)
        self.assertEqual(self.services.public_content.get_public_reports('article', 20, 0)['total'], 1)
        self.assertNotEqual(public["revision"], before["revision"])
        self.assertEqual(public["items"][0]["source_url"], "https://example.test/model")
        self.assertEqual(self.services.public_content.search_public_content("开源模型", "article", 20, 0)["total"], 1)
        self.assertIn("开源模型发布", self.services.public_content.build_public_rss("article", 20))
        self.assertTrue(self.services.event_intelligence.get_detail(self.entry["event_id"], public_only=True)["reviews"])
        self.assertEqual(repositories().editorial_workbench.get_entry(self.entry["id"])["delivery_status"], "pending")
        self.assertEqual(repositories().daily_reports.list_reports("article", 20, 0)["total"], 1)
        self.services.publications.update_publication(self.publication["id"], {"is_public": False})
        self.assertEqual(self.public()["total"], 0)
        self.assertEqual(self.services.public_content.get_public_reports('article', 20, 0)['total'], 0)
        with self.assertRaises(NotFoundError):
            self.services.event_intelligence.get_detail(self.entry["event_id"], public_only=True)

    async def test_review_and_publish_guards(self):
        with self.assertRaises(ValidationError):
            self.services.editorial_workbench.update_entry(self.entry["id"], {"review_status": "selected"}, "editor")
        draft = self.draft()
        with self.assertRaises(ValidationError):
            await self.services.publication_workflow.publish_draft(draft["id"], website_only=True)

        self.select()
        self.services.publications.update_publication(self.publication["id"], {"is_public": False})
        with self.assertRaises(ValidationError):
            await self.services.publication_workflow.publish_draft(draft["id"], website_only=True)
        self.services.publications.update_publication(self.publication["id"], {"is_public": True})
        repositories().editorial_workbench.update_draft(draft["id"], status="publishing")
        for website_only in (True, False):
            with self.subTest(website_only=website_only):
                with self.assertRaisesRegex(ConflictError, "缺少原发布计划"):
                    await self.services.publication_workflow.publish_draft(draft["id"], website_only=website_only)
        self.assertIsNone(self.services.delivery_operations.get_plan(f"draft:{draft['draft_key']}"))
        self.assertEqual(repositories().delivery_operations.list_operations(), [])
        self.assertEqual(repositories().daily_reports.list_reports("article", 20, 0)["total"], 0)
        self.assertEqual(self.public()["total"], 0)

    async def test_sent_delivery_cannot_bypass_private_or_disabled_publication(self):
        self.select()
        draft = self.draft()
        await self.services.publication_workflow.publish_draft(draft['id'], website_only=True)
        repositories().review.execute("UPDATE review_entries SET delivery_status='sent' WHERE id=?", (self.entry['id'],))
        self.assertEqual(self.public()['total'], 1)
        for values in ({'is_public': False}, {'is_public': True, 'enabled': False}):
            self.services.publications.update_publication(self.publication['id'], values)
            self.assertEqual(self.public()['total'], 0)
            self.assertEqual(self.services.public_content.get_public_reports('article', 20, 0)['total'], 0)
            self.assertEqual(self.services.public_content.search_public_content('开源模型', 'article', 20, 0)['total'], 0)
            self.assertNotIn('开源模型发布', self.services.public_content.build_public_rss('article', 20))
            with self.assertRaises(NotFoundError):
                self.services.event_intelligence.get_detail(self.entry['event_id'], public_only=True)

    async def test_internal_delivery_without_website_report_is_private(self):
        self.select()
        repositories().review.execute("UPDATE review_entries SET delivery_status='sent' WHERE id=?", (self.entry['id'],))
        self.assertEqual(self.public()['total'], 0)
        with self.assertRaises(NotFoundError):
            self.services.event_intelligence.get_detail(self.entry['event_id'], public_only=True)

    async def test_failed_website_write_rolls_back_and_can_retry(self):
        self.select()
        draft = self.draft()
        plan_key = f"draft:{draft['draft_key']}"
        original_snapshot = repositories().editorial_workbench.execute(
            "SELECT snapshot_json FROM publication_draft_items WHERE draft_id=?", (draft["id"],),
        ).fetchone()[0]
        original_save = DailyReportRepository.save_report_items

        def fail_after_writing(repo, report_id, entries):
            original_save(repo, report_id, entries)
            raise RuntimeError("write failed")

        with patch.object(DailyReportRepository, "save_report_items", new=fail_after_writing):
            with self.assertRaisesRegex(RuntimeError, "write failed"):
                await self.services.publication_workflow.publish_draft(draft["id"], website_only=True)
        # The accepted plan survives; all unfinished website writes roll back.
        stored_draft = repositories().editorial_workbench.get_draft(draft["id"])
        self.assertEqual(stored_draft["status"], "publishing")
        self.assertIsNone(stored_draft["published_report_id"])
        frozen = self.services.delivery_operations.get_plan(plan_key)
        self.assertIsNotNone(frozen)
        self.assertIsNone(frozen["finalized_at"])
        self.assertIsNone(frozen["result"])
        self.assertEqual(frozen["operation_keys"], [])
        self.assertEqual(repositories().daily_reports.list_reports("article", 20, 0)["total"], 0)
        self.assertEqual(repositories().daily_reports.execute("SELECT COUNT(*) FROM daily_report_items").fetchone()[0], 0)
        snapshot = repositories().editorial_workbench.execute(
            "SELECT snapshot_json FROM publication_draft_items WHERE draft_id=?", (draft["id"],),
        ).fetchone()[0]
        self.assertEqual(snapshot, original_snapshot)
        self.assertEqual(self.public()["total"], 0)

        # Retry after a restart must publish the accepted version, even if the
        # live entry or publication template has changed in the meantime.
        self.services = AppServices()
        with self.assertRaises(ConflictError):
            self.services.editorial_workbench.update_draft(draft["id"], {"title": "不能修改已接收的草稿"})
        with self.assertRaisesRegex(ConflictError, "已有发布计划"):
            await self.services.publication_workflow.publish_draft(draft["id"], website_only=False)
        self.services.editorial_workbench.update_entry(self.entry["id"], {
            "title": "重试之前的新标题", "review_summary": "重试之前的新摘要", "change_note": "后续修改",
        }, "editor")
        self.services.publications.update_publication(self.publication["id"], {"template": {"title_prefix": "新模板"}})
        with patch.object(self.services.publication_channel_gateway, "send_message_result", new_callable=AsyncMock) as send:
            result = await self.services.publication_workflow.publish_draft(draft["id"], website_only=True)
            repeat = await self.services.publication_workflow.publish_draft(draft["id"], website_only=True)
            send.assert_not_called()
        self.assertEqual(result["status"], "published")
        self.assertEqual(result["report_id"], repeat["report_id"])
        self.assertEqual(result["operations"], [])
        stored_draft = repositories().editorial_workbench.get_draft(draft["id"])
        self.assertEqual(stored_draft["status"], "published")
        self.assertEqual(stored_draft["published_report_id"], result["report_id"])
        reports = repositories().daily_reports.list_reports("article", 20, 0)
        self.assertEqual(reports["total"], 1)
        report = reports["items"][0]
        self.assertEqual(report["title"], frozen["payload"]["title"])
        self.assertEqual(report["content"], frozen["payload"]["content"])
        self.assertEqual(len(report["items"]), 1)
        self.assertEqual(report["items"][0]["title"], frozen["payload"]["entries"][0]["title"])
        self.assertEqual(report["items"][0]["review_summary"], frozen["payload"]["entries"][0]["review_summary"])
        completed = self.services.delivery_operations.get_plan(plan_key)
        self.assertIsNotNone(completed["finalized_at"])
        self.assertEqual(completed["result"]["report_id"], result["report_id"])
        self.assertEqual(completed["payload"], frozen["payload"])
        self.assertEqual(self.public()["total"], 1)
        self.assertEqual(repositories().editorial_workbench.get_entry(self.entry["id"])["delivery_status"], "pending")

    async def test_background_scraper_outlives_command_database_transaction(self):
        # Only the remote scraper is replaced; launch, claims and persistence are real.
        class Scraper:
            site_name = "transaction-source"

            async def run(self):
                return [{"title": "transaction test", "content": "body", "url": "https://example.test/background",
                         "published_at": datetime.now(timezone.utc).isoformat(), "type": "article"}]

        class Definition:
            @staticmethod
            def build_scraper():
                return Scraper()

        runs = self.services.scraper_runs
        runs.configure_worker("test-worker")
        with patch.object(runs._runtime_state, "require_scraper", return_value=Definition()):
            with transactional_repositories():
                self.assertTrue(runs.launch_scraper("transaction-source", 1))
            await asyncio.wait_for(runs._running_tasks["transaction-source"], 10)
        row = repositories().news.execute("SELECT title FROM news WHERE source_url = ?", ("https://example.test/background",)).fetchone()
        self.assertIsNotNone(row)


if __name__ == "__main__":
    unittest.main()
