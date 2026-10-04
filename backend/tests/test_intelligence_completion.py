from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from shared.content_contract import DELIVERY_PART_STATUS_SENT, DELIVERY_PART_STATUS_UNKNOWN

from backend.app.composition import app_services
from backend.app.infrastructure.database import database, init_database
from backend.app.infrastructure.repositories import repositories


class IntelligenceCompletionTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        tools_dir = Path(r"D:\Tools")
        tools_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir = tempfile.TemporaryDirectory(dir=tools_dir)
        self.original_db_path = database.db_path
        database.db_path = str(Path(self.temp_dir.name) / "completion.db")
        init_database()
        self.ids = self._seed_public_event()

    async def asyncTearDown(self):
        database.db_path = self.original_db_path
        self.temp_dir.cleanup()

    @staticmethod
    def _seed_public_event() -> dict[str, int]:
        published = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(
            microsecond=0
        ).isoformat()
        conn = database.connect()
        try:
            conn.execute("BEGIN")
            news_id = conn.execute(
                """
                INSERT INTO news(
                    title, content, source_site, source_url, published_at,
                    scraped_at, stage, type
                ) VALUES (?, ?, ?, ?, ?, ?, 'incoming', 'news')
                """,
                (
                    "公开事件",
                    "事件正文",
                    "Official Wire",
                    "https://example.test/public-event",
                    published,
                    published,
                ),
            ).lastrowid
            event_id = conn.execute(
                """
                INSERT INTO content_events(
                    canonical_news_id, title, content, content_type, published_at,
                    first_seen_at, last_seen_at, source_count, event_key
                ) VALUES (?, ?, ?, 'news', ?, ?, ?, 1, ?)
                """,
                (news_id, "公开事件", "事件正文", published, published, published, "completion-event"),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO event_sources(
                    event_id, news_id, similarity, is_primary, source_role,
                    evidence_group, independence_score, verification_status
                ) VALUES (?, ?, 1, 1, 'primary', 'official:completion', 1, 'verified')
                """,
                (event_id, news_id),
            )
            review_id = conn.execute(
                """
                INSERT INTO review_entries(
                    title, content, source_site, source_url, published_at,
                    scraped_at, archived_at, queued_at, content_type,
                    source_item_id, event_id, profile_slug, review_status,
                    review_summary, review_reason, review_score,
                    review_category, review_tags, delivery_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'news', ?, ?, 'daily-briefs',
                    'selected', '审核摘要', '重要', 9, '监管', '[]', 'sent')
                """,
                (
                    "公开事件",
                    "事件正文",
                    "Official Wire",
                    "https://example.test/public-event",
                    published,
                    published,
                    published,
                    published,
                    news_id,
                    event_id,
                ),
            ).lastrowid
            conn.commit()
            from backend.app.infrastructure.repository_impl.daily_report_repository import DailyReportRepository
            publication = conn.execute("SELECT id FROM profile_publications WHERE profile_slug='daily-briefs'").fetchone()
            reports = DailyReportRepository(conn)
            report_id = reports.save_report('completion-public-evidence', published[:10], 'news', '公开事件', '事件正文', 1,
                                            profile_slug='daily-briefs', publication_id=publication['id'])
            entry = dict(conn.execute('SELECT * FROM review_entries WHERE id=?', (review_id,)).fetchone())
            reports.save_report_items(report_id, [entry])
            conn.commit()
            return {"news": int(news_id), "event": int(event_id), "review": int(review_id)}
        finally:
            conn.close()

    async def test_iso_scheduled_draft_is_due_on_the_same_day(self):
        publication = next(
            item
            for item in app_services.publications.list_publications()
            if item["profile_slug"] == "daily-briefs"
        )
        draft = app_services.editorial_workbench.create_draft(
            {
                "publication_id": publication["id"],
                "content_type": "news",
                "title": "同日定时草稿",
                "items": [
                    {
                        "review_entry_id": self.ids["review"],
                        "position": 0,
                        "section": "监管",
                        "included": True,
                        "overrides": {},
                    }
                ],
            },
            "test",
        )
        scheduled_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        app_services.editorial_workbench.update_draft(
            draft["id"], {"status": "scheduled", "scheduled_at": scheduled_at}
        )

        due_ids = {
            int(item["id"])
            for item in repositories().editorial_workbench.list_due_drafts()
        }
        self.assertIn(draft["id"], due_ids)

    async def test_public_event_hides_unpublished_corrections(self):
        correction = app_services.editorial_workbench.add_correction(
            {
                "correction_type": "correction",
                "message": "内部待核对更正",
                "event_id": self.ids["event"],
            },
            "editor",
        )

        internal = app_services.event_intelligence.get_detail(self.ids["event"])
        public = app_services.event_intelligence.get_detail(
            self.ids["event"], public_only=True
        )
        self.assertEqual([item["id"] for item in internal["corrections"]], [correction["id"]])
        self.assertEqual(public["corrections"], [])

        repositories().editorial_workbench.mark_correction_published(correction["id"])
        public_after_publish = app_services.event_intelligence.get_detail(
            self.ids["event"], public_only=True
        )
        self.assertEqual(
            [item["id"] for item in public_after_publish["corrections"]],
            [correction["id"]],
        )

    async def test_draft_preview_is_final_format_without_delivery_side_effects(self):
        publication = next(
            item for item in app_services.publications.list_publications()
            if item["profile_slug"] == "daily-briefs"
        )
        draft = app_services.editorial_workbench.create_draft(
            {
                "publication_id": publication["id"], "content_type": "news", "title": "预览测试",
                "items": [{"review_entry_id": self.ids["review"], "position": 0, "section": "监管", "included": True, "overrides": {}}],
            },
            "editor",
        )
        before = repositories().delivery_operations.list_operations(100)
        preview = app_services.publication_workflow.preview_draft(draft["id"])
        after = repositories().delivery_operations.list_operations(100)
        self.assertIn("预览测试", preview["content"])
        self.assertIn("公开事件", preview["content"])
        self.assertGreaterEqual(preview["target_count"], 1)
        self.assertEqual(len(before), len(after))

    async def test_public_facts_relations_and_rule_classification_are_complete(self):
        related_id = self._seed_related_event()
        visible = app_services.event_intelligence.add_fact(
            self.ids["event"],
            {"fact_text": "监管公告已正式发布", "source_news_id": self.ids["news"], "confidence": 0.95, "verification_status": "verified", "is_public": True},
            "editor",
        )
        app_services.event_intelligence.add_fact(
            self.ids["event"],
            {"fact_text": "内部待核实线索", "confidence": 0.4, "verification_status": "unverified", "is_public": False},
            "editor",
        )
        app_services.event_intelligence.add_relation(
            self.ids["event"],
            {"related_event_id": related_id, "relation_type": "follow_up", "notes": "后续进展", "is_public": True},
            "editor",
        )
        entity = app_services.intelligence_catalog.save_entity(
            {"entity_type": "organization", "slug": "public-event-org", "name": "公开事件机构", "description": "", "aliases": ["公开事件"], "metadata": {}}
        )
        app_services.intelligence_catalog.attach_entity(
            self.ids["event"], {"entity_id": entity["id"], "role": "subject", "confidence": 0.42, "source": "manual"}
        )
        narrative = app_services.intelligence_catalog.save_narrative(
            {"slug": "event-body", "name": "正文叙事", "description": "", "keywords": ["事件正文"], "enabled": True}
        )
        classified = app_services.intelligence_catalog.classify_event(self.ids["event"])
        public = app_services.event_intelligence.get_detail(self.ids["event"], public_only=True)
        self.assertEqual([item["id"] for item in public["facts"]], [visible["id"]])
        self.assertEqual(public["relations"][0]["related_id"], related_id)
        manual = next(item for item in public["entities"] if item["id"] == entity["id"])
        self.assertEqual(manual["source"], "manual")
        self.assertAlmostEqual(manual["confidence"], 0.42)
        self.assertEqual(classified["narratives"][0]["narrative_id"], narrative["id"])
        topic = app_services.intelligence_catalog.get_public_narrative("event-body", 20, 0)
        self.assertEqual(topic["keywords"], ["事件正文"])
        self.assertGreaterEqual(topic["trend"]["total"], 1)

    async def test_ai_feedback_summary_exposes_adoption_edit_and_error_rates(self):
        for outcome, score in (("accepted", 5), ("edited", 3), ("incorrect", 1)):
            app_services.editorial_workbench.add_feedback(
                self.ids["review"], {"outcome": outcome, "quality_score": score, "changed_fields": [], "notes": outcome}, "editor"
            )
        summary = app_services.ai_quality.summary(30)["feedback_summary"]
        self.assertEqual(summary["total"], 3)
        self.assertAlmostEqual(summary["adoption_rate"], 2 / 3)
        self.assertAlmostEqual(summary["edit_rate"], 1 / 3)
        self.assertAlmostEqual(summary["incorrect_rate"], 1 / 3)
        self.assertEqual(summary["average_quality_score"], 3)

    async def test_official_source_catalog_and_parser_drift_detection(self):
        official = {
            item["slug"]: item for item in app_services.rss_sources.list_sources()["sources"]
            if item.get("is_official")
        }
        self.assertTrue({"sec-press-releases", "cftc-press-releases", "kraken-blog", "ethereum-foundation-blog", "ens-governance-forum"} <= set(official))
        self.assertTrue(all(item["authority_type"] == "primary" for item in official.values()))
        drift = app_services.source_operations._parser_drift(
            {"item_count": 20, "content_completeness": 0.95},
            {"item_count": 3, "content_completeness": 0.4},
        )
        self.assertIsNotNone(drift)
        self.assertEqual(len(drift["reasons"]), 2)

    async def test_analyst_webhook_advances_cursor_only_after_confirmed_delivery(self):
        channel = app_services.publications.save_channel(
            {"slug": "analyst-change-hook", "name": "分析师变更", "channel_type": "webhook", "enabled": True, "config": {"url": "https://example.test/analyst"}}
        )
        subscription = app_services.analyst_subscriptions.create(
            {"name": "事件变化", "channel_id": channel["id"], "enabled": True, "object_types": ["event", "tag"], "content_types": ["news"], "profile_slugs": ["daily-briefs"], "batch_size": 100, "start_from": "beginning"}
        )
        sent_payloads = []
        original_send = app_services.publication_channel_gateway.send_json_result

        async def sent(_slug, payload):
            sent_payloads.append(payload)
            return {"status": DELIVERY_PART_STATUS_SENT, "error": None, "remote_message_id": "change-1"}

        app_services.publication_channel_gateway.send_json_result = sent
        try:
            first = await app_services.analyst_subscriptions.deliver(subscription["id"])
        finally:
            app_services.publication_channel_gateway.send_json_result = original_send
        self.assertEqual(first["results"][0]["status"], "sent")
        self.assertEqual(sent_payloads[0]["event"], "ainews.analyst.changes")
        delivered_cursor = app_services.analyst_subscriptions.list_subscriptions()[0]["cursor"]
        self.assertGreater(delivered_cursor, 0)

        app_services.event_intelligence.update_source_evidence(
            self.ids["event"], self.ids["news"], {"evidence_notes": "订阅失败测试"}
        )

        async def unknown(_slug, _payload):
            return {"status": DELIVERY_PART_STATUS_UNKNOWN, "error": "网络结果不确定", "remote_message_id": None}

        app_services.publication_channel_gateway.send_json_result = unknown
        try:
            failed = await app_services.analyst_subscriptions.deliver(subscription["id"])
        finally:
            app_services.publication_channel_gateway.send_json_result = original_send
        self.assertEqual(failed["results"][0]["status"], "needs_attention")
        self.assertEqual(app_services.analyst_subscriptions.list_subscriptions()[0]["cursor"], delivered_cursor)

    @staticmethod
    def _seed_related_event() -> int:
        published = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(microsecond=0).isoformat()
        conn = database.connect()
        try:
            conn.execute("BEGIN")
            news_id = conn.execute(
                """INSERT INTO news(title, content, source_site, source_url, published_at, scraped_at, stage, type)
                VALUES ('关联事件', '后续正文', 'Official Wire', 'https://example.test/related', ?, ?, 'incoming', 'news')""",
                (published, published),
            ).lastrowid
            event_id = conn.execute(
                """INSERT INTO content_events(canonical_news_id, title, content, content_type, published_at, first_seen_at, last_seen_at, source_count, event_key)
                VALUES (?, '关联事件', '后续正文', 'news', ?, ?, ?, 1, 'completion-related')""",
                (news_id, published, published, published),
            ).lastrowid
            conn.execute("INSERT INTO event_sources(event_id, news_id, similarity, is_primary) VALUES (?, ?, 1, 1)", (event_id, news_id))
            review_id = conn.execute(
                """INSERT INTO review_entries(title, content, source_site, source_url, published_at, scraped_at, archived_at, queued_at, content_type, source_item_id, event_id, profile_slug, review_status, review_summary, review_reason, review_score, review_category, review_tags, delivery_status)
                VALUES ('关联事件', '后续正文', 'Official Wire', 'https://example.test/related', ?, ?, ?, ?, 'news', ?, ?, 'daily-briefs', 'selected', '摘要', '重要', 8, '监管', '[]', 'sent')""",
                (published, published, published, published, news_id, event_id),
            ).lastrowid
            conn.commit()
            from backend.app.infrastructure.repository_impl.daily_report_repository import DailyReportRepository
            publication = conn.execute("SELECT id FROM profile_publications WHERE profile_slug='daily-briefs'").fetchone()
            reports = DailyReportRepository(conn)
            report_id = reports.save_report('completion-related-public', published[:10], 'news', '关联事件', '后续正文', 1,
                                            profile_slug='daily-briefs', publication_id=publication['id'])
            reports.save_report_items(report_id, [dict(conn.execute('SELECT * FROM review_entries WHERE id=?', (review_id,)).fetchone())])
            conn.commit()
            return int(event_id)
        finally:
            conn.close()
