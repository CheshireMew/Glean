from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from shared.content_contract import DELIVERY_PART_STATUS_SENT

from backend.app.composition import app_services
from backend.app.core.exceptions import NotFoundError, ValidationError
from backend.app.infrastructure.database import database, init_database
from backend.app.infrastructure.repositories import repositories


class IntelligenceExtensionsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        tools_dir = Path(r"D:\Tools")
        tools_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir = tempfile.TemporaryDirectory(dir=tools_dir)
        self.original_db_path = database.db_path
        database.db_path = str(Path(self.temp_dir.name) / "intelligence.db")
        init_database()
        self.ids = self._seed_selected_event()

    async def asyncTearDown(self):
        database.db_path = self.original_db_path
        self.temp_dir.cleanup()

    def _seed_selected_event(self):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        published = (now - timedelta(hours=2)).isoformat()
        conn = database.connect()
        try:
            conn.execute("BEGIN")
            news_id = conn.execute(
                """
                INSERT INTO news(title, content, source_site, source_url, published_at, scraped_at, stage, type)
                VALUES ('测试事件', '事件正文', 'Official Wire', 'https://example.test/event', ?, ?, 'incoming', 'news')
                """,
                (published, published),
            ).lastrowid
            event_id = conn.execute(
                """
                INSERT INTO content_events(canonical_news_id, title, content, content_type, published_at,
                    first_seen_at, last_seen_at, source_count, event_key)
                VALUES (?, '测试事件', '事件正文', 'news', ?, ?, ?, 1, 'test-event')
                """,
                (news_id, published, published, published),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO event_sources(event_id, news_id, similarity, is_primary, source_role,
                    evidence_group, independence_score, verification_status)
                VALUES (?, ?, 1, 1, 'primary', 'official:test-event', 1, 'verified')
                """,
                (event_id, news_id),
            )
            review_id = conn.execute(
                """
                INSERT INTO review_entries(title, content, source_site, source_url, published_at,
                    scraped_at, archived_at, queued_at, content_type, source_item_id, event_id,
                    profile_slug, review_status, review_summary, review_reason, review_score,
                    review_category, review_tags, delivery_status, enrichment_status, enriched_summary,
                    enrichment_citations)
                VALUES ('测试事件', '事件正文', 'Official Wire', 'https://example.test/event', ?, ?, ?, ?,
                    'news', ?, ?, 'daily-briefs', 'selected', '审核摘要', '重要', 9, '市场', '[]',
                    'pending', 'completed', '补充摘要', '[]')
                """,
                (published, published, published, published, news_id, event_id),
            ).lastrowid
            conn.commit()
            return {"news": int(news_id), "event": int(event_id), "review": int(review_id)}
        finally:
            conn.close()

    async def test_intelligence_alert_market_and_analyst_read_model(self):
        entity = app_services.intelligence_catalog.save_entity(
            {
                "entity_type": "asset", "slug": "bitcoin", "name": "Bitcoin", "symbol": "BTC",
                "description": "比特币", "aliases": ["比特币"], "metadata": {},
            }
        )
        narrative = app_services.intelligence_catalog.save_narrative(
            {"slug": "institutional-adoption", "name": "机构采用", "description": "机构采用加密资产", "enabled": True}
        )
        app_services.intelligence_catalog.attach_entity(
            self.ids["event"], {"entity_id": entity["id"], "role": "subject", "confidence": 1, "source": "manual"}
        )
        app_services.intelligence_catalog.attach_narrative(
            self.ids["event"], {"narrative_id": narrative["id"], "confidence": 0.9, "source": "manual"}
        )
        watchlist = app_services.intelligence_catalog.save_watchlist(
            {"name": "重点资产", "description": "测试", "enabled": True, "visibility": "private", "entity_ids": [entity["id"]], "narrative_ids": [narrative["id"]]}
        )
        channel = app_services.publications.save_channel(
            {"slug": "test-webhook", "name": "测试 Webhook", "channel_type": "webhook", "enabled": True, "config": {"url": "https://example.test/hook"}}
        )
        policy = app_services.intelligence_catalog.save_alert_policy(
            {
                "name": "重点事件", "description": "测试", "enabled": True,
                "watchlist_id": watchlist["id"], "profile_slug": "daily-briefs",
                "conditions": {"min_score": 8, "min_independent_sources": 1, "verified_only": True},
                "schedule_type": "instant", "quiet_hours": {}, "channel_id": channel["id"],
            }
        )
        evaluated = app_services.intelligence_catalog.evaluate_alerts(policy["id"], 24)
        self.assertEqual(evaluated["new_matches"], 1)

        instrument = app_services.market_intelligence.save_instrument(
            {"entity_id": entity["id"], "provider": "manual", "symbol": "BTC", "quote_symbol": "USD", "enabled": True, "metadata": {}}
        )
        event_time = datetime.now(timezone.utc) - timedelta(hours=2)
        app_services.market_intelligence.save_expectation(
            self.ids["event"], instrument["id"],
            {"expected_direction": "positive", "expected_impact": "测试预期", "confidence": 0.7, "metadata": {}},
        )
        app_services.market_intelligence.save_snapshot(
            self.ids["event"], instrument["id"],
            {"observation_window": "t0", "observed_at": event_time, "price": 100, "volume": 10, "metadata": {}},
        )
        market = app_services.market_intelligence.save_snapshot(
            self.ids["event"], instrument["id"],
            {"observation_window": "t+1h", "observed_at": event_time + timedelta(hours=1), "price": 110, "volume": 12, "metadata": {}},
        )
        self.assertAlmostEqual(market["assessment"]["return_1h"], 0.1)
        self.assertEqual(market["assessment"]["realized_direction"], "positive")

        key = await app_services.analyst_access.create_api_key("test", None)
        page = app_services.analyst_data.list_events(key["api_key"], 1, 20, "news", None)
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["items"][0]["entities"][0]["slug"], "bitcoin")
        self.assertEqual(page["items"][0]["markets"][0]["instrument"]["symbol"], "BTC")
        delta = app_services.analyst_data.delta(key["api_key"], "2000-01-01T00:00:00+00:00", 20)
        self.assertEqual(delta["events"][0]["event"]["id"], self.ids["event"])
        self.assertTrue(delta["next_cursor"])
        recent_cursor = (datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat()
        app_services.event_intelligence.update_source_evidence(
            self.ids["event"], self.ids["news"], {"evidence_notes": "增量核验"}
        )
        recent = app_services.analyst_data.delta(key["api_key"], recent_cursor, 20)
        self.assertEqual(recent["events"][0]["sources"][0]["evidence_notes"], "增量核验")
        with self.assertRaises(ValidationError):
            app_services.analyst_data.delta(key["api_key"], "not-a-time", 20)

    async def test_draft_publication_uses_durable_channel_delivery_and_persists_report(self):
        channel = app_services.publications.save_channel(
            {"slug": "release-webhook", "name": "发布 Webhook", "channel_type": "webhook", "enabled": True, "config": {"url": "https://example.test/release"}}
        )
        publication = next(
            item for item in app_services.publications.list_publications()
            if item["profile_slug"] == "daily-briefs"
        )
        publication = app_services.publications.update_publication(
            publication["id"],
            {
                "is_public": True,
                "rss_enabled": False,
                "template": {
                    "title_prefix": "【内参】",
                    "intro": "今天的重点如下 <请核对>",
                    "footer": "Glean 编辑部",
                },
                "targets": [{"channel_id": channel["id"], "delivery_mode": "digest", "enabled": True}],
            },
        )
        draft = app_services.editorial_workbench.create_draft(
            {
                "publication_id": publication["id"], "content_type": publication["content_type"],
                "title": "测试发布", "items": [{"review_entry_id": self.ids["review"], "position": 0, "section": "市场", "included": True, "overrides": {}}],
            },
            "test",
        )
        original_send = app_services.publication_channel_gateway.send_message_result

        async def sent(_channel_slug, _text):
            return {"status": DELIVERY_PART_STATUS_SENT, "error": None, "remote_message_id": "remote-1"}

        app_services.publication_channel_gateway.send_message_result = sent
        try:
            result = await app_services.publication_workflow.publish_draft(draft["id"])
        finally:
            app_services.publication_channel_gateway.send_message_result = original_send
        self.assertEqual(result["status"], "published")
        persisted = repositories().editorial_workbench.get_draft(draft["id"])
        self.assertEqual(persisted["status"], "published")
        reports = repositories().daily_reports.list_reports("news", 20, 0, publication_id=publication["id"])
        self.assertEqual(reports["total"], 1)
        self.assertEqual(reports["items"][0]["draft_id"], draft["id"])
        self.assertEqual(reports["items"][0]["title"], "【内参】测试发布")
        self.assertIn("今天的重点如下 &lt;请核对&gt;", reports["items"][0]["content"])
        self.assertIn("Glean 编辑部", reports["items"][0]["content"])
        review = repositories().editorial_workbench.get_entry(self.ids["review"])
        self.assertEqual(review["delivery_status"], "sent")
        operation = repositories().delivery_operations.get_operation(result["operations"][0]["operation_key"])
        self.assertEqual(operation["channel_slug"], "release-webhook")

        private = app_services.publications.update_publication(publication["id"], {"is_public": False})
        hidden = app_services.public_content.get_public_content("news", 20, 0, publication_slug=private["public_slug"])
        self.assertEqual(hidden["items"], [])
        app_services.publications.update_publication(publication["id"], {"is_public": True, "rss_enabled": False})
        disabled_rss = app_services.public_content.build_public_rss("news", 20, private["public_slug"])
        self.assertNotIn("测试事件", disabled_rss)
        app_services.publications.update_publication(publication["id"], {"rss_enabled": True})
        enabled_rss = app_services.public_content.build_public_rss("news", 20, private["public_slug"])
        self.assertIn("测试事件", enabled_rss)

    async def test_discord_messages_are_split_without_truncation_and_alert_channels_are_validated(self):
        channel = app_services.publications.save_channel(
            {"slug": "discord-test", "name": "Discord", "channel_type": "discord", "enabled": True, "config": {"url": "https://example.test/discord"}}
        )
        source = "<b>标题</b>\n\n" + ("完整内容 " * 700)
        parts = app_services.publication_channel_gateway.prepare_messages("discord-test", [source])
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(part) <= 2000 for part in parts))
        self.assertEqual("".join(parts).replace(" ", ""), ("标题\n\n" + ("完整内容 " * 700)).strip().replace(" ", ""))
        with self.assertRaises(NotFoundError):
            app_services.intelligence_catalog.save_alert_policy(
                {
                    "name": "无效渠道", "description": "", "enabled": True, "watchlist_id": None,
                    "profile_slug": None, "conditions": {}, "schedule_type": "instant",
                    "quiet_hours": {}, "channel_id": channel["id"] + 9999,
                }
            )

    async def test_source_catalog_snapshot_is_generated_from_registered_scrapers(self):
        sources = app_services.source_operations.list_sources()
        self.assertGreater(len(sources), 0)
        result = app_services.source_operations.snapshot(sources[0]["source_key"], 24)
        self.assertEqual(result["sources"], 1)
        self.assertEqual(len(result["snapshots"]), 1)
        saved = repositories().source_operations.list_health(sources[0]["source_key"], 10)
        self.assertEqual(len(saved), 1)
