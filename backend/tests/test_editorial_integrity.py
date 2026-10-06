from __future__ import annotations

import sqlite3
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone

from backend.app.core.exceptions import NotFoundError, ValidationError
from backend.app.infrastructure.repositories import RepositoryUnitOfWork
from backend.app.infrastructure.sqlite.sqlite_migration_plan import create_current_schema
from backend.app.services.editorial_workbench_service import EditorialWorkbenchService
from backend.app.services.event_intelligence_service import EventIntelligenceService
from backend.app.services.publication_workflow_service import PublicationWorkflowService


class EditorialIntegrityTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:", isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        create_current_schema(self.conn.cursor())
        self.repos = RepositoryUnitOfWork(self.conn)
        self.editorial = EditorialWorkbenchService(lambda: self.repos.editorial_workbench, self.transaction)
        self.intelligence = EventIntelligenceService(lambda: self.repos.event_intelligence, self.transaction)
        self.publication = self.conn.execute(
            "SELECT id FROM profile_publications WHERE profile_slug='daily-briefs'"
        ).fetchone()["id"]
        self.entry_id, self.event_id, self.news_id = self.seed_entry("daily-briefs", "news", "original")
        self.other_entry, self.other_event, self.other_news = self.seed_entry("daily-briefs", "news", "other")

    def tearDown(self):
        self.conn.close()

    @contextmanager
    def transaction(self):
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield self.repos
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def seed_entry(self, profile, kind, key):
        now = datetime.now(timezone.utc).isoformat()
        news_id = self.conn.execute(
            "INSERT INTO news(title, content, source_site, source_url, published_at, type) VALUES (?, ?, 'wire', ?, ?, ?)",
            (key, key, f"https://example.test/{key}", now, kind),
        ).lastrowid
        event_id = self.conn.execute(
            "INSERT INTO content_events(canonical_news_id, title, content_type, published_at, first_seen_at, last_seen_at, event_key) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (news_id, key, kind, now, now, now, key),
        ).lastrowid
        self.conn.execute("INSERT INTO event_sources(event_id, news_id) VALUES (?, ?)", (event_id, news_id))
        review_id = self.conn.execute(
            "INSERT INTO review_entries(title, source_site, source_url, published_at, scraped_at, archived_at, queued_at, content_type, event_id, profile_slug, review_status, review_summary, review_reason) VALUES (?, 'wire', ?, ?, ?, ?, ?, ?, ?, ?, 'selected', 'summary', 'reason')",
            (key, f"https://example.test/{key}", now, now, now, now, kind, event_id, profile),
        ).lastrowid
        return review_id, event_id, news_id

    def draft_values(self, items):
        return {"publication_id": self.publication, "content_type": "news", "title": "original draft", "items": items}

    @staticmethod
    def item(entry_id):
        return {"review_entry_id": entry_id, "position": 0, "section": "test", "included": True, "overrides": {}}

    async def test_draft_create_patch_and_publish_reject_invalid_items_atomically(self):
        self.conn.execute("INSERT INTO editorial_profiles(slug, name, content_type) VALUES ('other-briefs', 'Other briefs', 'news')")
        wrong_profile, _, _ = self.seed_entry("other-briefs", "news", "wrong-profile")
        wrong_kind, _, _ = self.seed_entry("daily-briefs", "article", "wrong-kind")
        valid = [self.item(self.entry_id)]
        draft = self.editorial.create_draft(self.draft_values(valid), "editor")
        invalid_sets = [
            ([self.item(wrong_profile)], ValidationError),
            ([self.item(wrong_kind)], ValidationError),
            ([self.item(self.entry_id), {**self.item(self.entry_id), "position": 1}], ValidationError),
            ([self.item(999999)], NotFoundError),
        ]
        for items, error in invalid_sets:
            with self.subTest(items=items):
                with self.assertRaises(error):
                    self.editorial.create_draft(self.draft_values(items), "editor")
                with self.assertRaises(error):
                    self.editorial.update_draft(draft["id"], {"title": "must roll back", "items": items})
                stored = self.editorial.get_draft(draft["id"])
                self.assertEqual(stored["title"], "original draft")
                self.assertEqual([item["review_entry_id"] for item in stored["items"]], [self.entry_id])

        # A pre-existing bad draft must be rejected at the final publishing boundary too.
        self.repos.editorial_workbench.replace_draft_items(draft["id"], [self.item(wrong_profile)])
        workflow = PublicationWorkflowService(
            lambda: self.repos.editorial_workbench, lambda: self.repos.publications,
            lambda: self.repos.daily_reports, None, None, None, None, None,
            None, None, None, None, None, self.transaction,
        )
        with self.assertRaises(ValidationError):
            await workflow.publish_draft(draft["id"], website_only=True)
        self.assertEqual(self.editorial.get_draft(draft["id"])["status"], "draft")

    async def test_event_update_patch_keeps_source_in_owning_event(self):
        update = self.intelligence.add_update(self.event_id, {
            "title": "original update", "occurred_at": datetime.now(timezone.utc),
            "source_news_id": self.news_id,
        }, "editor")
        for source_id in (self.other_news, 999999):
            with self.subTest(source=source_id):
                with self.assertRaises(ValidationError):
                    self.intelligence.update_event_update(update["id"], {
                        "source_news_id": source_id, "title": "must roll back",
                    }, "editor")
                stored = self.intelligence.get_detail(self.event_id)["updates"][0]
                self.assertEqual((stored["source_news_id"], stored["title"]), (self.news_id, "original update"))
        self.intelligence.update_event_update(update["id"], {"source_news_id": None}, "editor")
        self.assertIsNone(self.intelligence.get_detail(self.event_id)["updates"][0]["source_news_id"])
        self.intelligence.update_event_update(update["id"], {"source_news_id": self.news_id}, "editor")
        self.assertEqual(self.intelligence.get_detail(self.event_id)["updates"][0]["source_news_id"], self.news_id)
        with self.assertRaises(NotFoundError):
            self.intelligence.update_event_update(999999, {"title": "missing"}, "editor")

    async def test_website_only_edit_invalidates_public_revision(self):
        self.conn.execute('UPDATE profile_publications SET is_public=1 WHERE id=?', (self.publication,))
        report = self.repos.daily_reports.save_report('website-revision', '2026-10-05', 'news', 'Website', 'original', 1,
            profile_slug='daily-briefs', publication_id=self.publication)
        self.repos.daily_reports.save_report_items(report, [self.repos.editorial_workbench.get_entry(self.entry_id)])
        repository = self.repos.review_public
        before = repository.get_public_revision('news', 'daily-briefs')
        self.editorial.update_entry(self.entry_id, {'title':'Website edited title'}, 'editor')
        after = repository.get_public_revision('news', 'daily-briefs')
        self.assertNotEqual(before, after)
        self.assertEqual(repository.list_public_entries('news','daily-briefs')['items'][0]['title'],'Website edited title')
