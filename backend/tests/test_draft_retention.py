from __future__ import annotations

import unittest

from backend.app.core.exceptions import ConflictError
from backend.app.services.content_lifecycle_service import ContentLifecycleService
from backend.app.services.content_transition_service import ContentTransitionService
from backend.tests import test_editorial_integrity as fixture


class DraftRetentionTest(unittest.TestCase):
    seed_entry = fixture.EditorialIntegrityTest.seed_entry
    item = staticmethod(fixture.EditorialIntegrityTest.item)
    draft_values = fixture.EditorialIntegrityTest.draft_values
    transaction = fixture.EditorialIntegrityTest.transaction

    def setUp(self):
        fixture.EditorialIntegrityTest.setUp(self)
        self.lifecycle = ContentLifecycleService(lambda: self.repos.review, self.transaction)
        self.conn.execute("UPDATE content_events SET last_seen_at='2000-01-01'")
        self.draft = self.editorial.create_draft(self.draft_values([self.item(self.entry_id)]), 'editor')

    def tearDown(self):
        self.conn.close()

    def test_retention_skips_active_draft_but_prunes_other_expired_events(self):
        self.assertEqual(self.repos.maintenance.prune_event_batch('2020-01-01', 100), 1)
        self.assertIsNotNone(self.repos.editorial_workbench.get_entry(self.entry_id))
        self.assertIsNone(self.repos.editorial_workbench.get_entry(self.other_entry))
        self.assertEqual(len(self.editorial.get_draft(self.draft['id'])['items']), 1)

    def test_published_and_cancelled_drafts_keep_readable_snapshots_after_prune(self):
        for status in ('published', 'cancelled'):
            with self.subTest(status=status):
                if status == 'published':
                    draft_id, entry_id, title = self.draft['id'], self.entry_id, 'original'
                else:
                    entry_id, event_id, _ = self.seed_entry('daily-briefs', 'news', 'cancelled original')
                    self.conn.execute("UPDATE content_events SET last_seen_at='2000-01-01' WHERE id=?", (event_id,))
                    draft_id = self.editorial.create_draft(self.draft_values([self.item(entry_id)]), 'editor')['id']
                    title = 'cancelled original'
                self.repos.editorial_workbench.update_draft(draft_id, status=status)
                self.repos.maintenance.prune_event_batch('2020-01-01', 100)
                self.assertIsNone(self.repos.editorial_workbench.get_entry(entry_id))
                items = self.editorial.get_draft(draft_id)['items']
                self.assertEqual(len(items), 1)
                self.assertEqual(items[0]['title'], title)
                self.assertIsNone(items[0]['review_entry_id'])

    def test_delete_restore_and_retroactive_blocklist_return_business_conflict(self):
        now = '2000-01-01 00:00:00'
        self.conn.execute('''
            INSERT INTO archive_entries(id,title,source_site,source_url,published_at,scraped_at,archived_at,
                content_type,source_item_id,event_id,archive_status)
            VALUES (1,'original','wire','https://example.test/original',?,?,?,'news',?,?,'reviewed')
        ''', (now, now, now, self.news_id, self.event_id))
        with self.assertRaises(ConflictError):
            self.lifecycle.delete_review_entry(self.entry_id)
        with self.assertRaises(ConflictError):
            self.lifecycle.restore_archive_entry(1)
        self.conn.execute("INSERT INTO keyword_blacklist(keyword, type) VALUES ('original','news')")
        with self.assertRaises(ConflictError):
            ContentTransitionService(self.transaction).apply_blocklist(0, 'news')
        self.assertEqual(self.repos.archive_query.get_entry(1)['archive_status'], 'reviewed')
        self.assertIsNotNone(self.repos.editorial_workbench.get_entry(self.entry_id))
