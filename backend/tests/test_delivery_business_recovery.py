from __future__ import annotations

import json
import unittest
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.app.core.exceptions import ValidationError
from backend.app.services.analyst_subscription_service import AnalystSubscriptionService
from backend.app.services.delivery_operation_service import DeliveryOperationService
from backend.app.services.delivery_retry_service import DeliveryRetryService
from backend.app.services.digest_planner_service import DigestPlannerService
from backend.app.services.publication_workflow_service import PublicationWorkflowService
from backend.app.services.telegram_message_service import TelegramMessageService
from backend.tests import test_editorial_integrity as integrity_fixture


class ControlledChannel:
    def __init__(self):
        self.blocked = {'channel-b'}
        self.unknown = set()
        self.calls = []
        self.limit = 4096
        self.limits = {}

    def channel_is_configured(self, _slug):
        return True

    def message_limit(self, _slug):
        return self.limits.get(_slug, 250000 if _slug == 'channel-b' else self.limit)

    async def send_message_result(self, slug, content):
        self.calls.append((slug, content))
        if slug in self.unknown:
            return {'status': 'unknown', 'error': 'confirmation lost'}
        if slug in self.blocked:
            return {'status': 'failed', 'error': 'controlled rejection'}
        return {'status': 'sent', 'remote_message_id': str(len(self.calls))}

    async def send_json_result(self, slug, payload):
        return await self.send_message_result(slug, json.dumps(payload, ensure_ascii=False))


class DeliveryBusinessRecoveryTest(unittest.IsolatedAsyncioTestCase):
    seed_entry = integrity_fixture.EditorialIntegrityTest.seed_entry
    item = staticmethod(integrity_fixture.EditorialIntegrityTest.item)
    draft_values = integrity_fixture.EditorialIntegrityTest.draft_values

    def setUp(self):
        integrity_fixture.EditorialIntegrityTest.setUp(self)
        self.channel = ControlledChannel()
        self.conn.execute("UPDATE review_entries SET enrichment_status='completed'")
        self.channel_ids = [self.repos.publications.save_channel({
            'slug': slug, 'name': slug, 'channel_type': 'webhook', 'enabled': True,
        }) for slug in ('channel-a', 'channel-b')]
        self.targets('digest')
        self.delivery = DeliveryOperationService(
            lambda: self.repos.delivery_operations, lambda: self.repos.delivery_execution,
            self.channel, self.transaction,
        )
        self.workflow = PublicationWorkflowService(
            lambda: self.repos.editorial_workbench, lambda: self.repos.publications,
            lambda: self.repos.daily_reports, lambda: self.repos.review_delivery,
            lambda: self.repos.review, lambda: self.repos.push,
            lambda: self.repos.intelligence_catalog, lambda: self.repos.event_intelligence,
            DigestPlannerService(), TelegramMessageService(), self.delivery, self.channel,
            lambda: SimpleNamespace(get_system_time=lambda: datetime(2026, 10, 5, tzinfo=timezone.utc)),
            self.transaction,
        )
        self.subscriptions = AnalystSubscriptionService(
            lambda: self.repos.analyst_subscriptions, lambda: self.repos.publications,
            lambda: self.repos.event_intelligence, lambda: self.repos.intelligence_catalog,
            lambda: self.repos.tags, self.delivery, self.transaction,
        )
        self.legacy_calls = Counter()
        self.retry = DeliveryRetryService(
            lambda: self.repos.delivery_operations, self.delivery,
            SimpleNamespace(finalize_success=self.finalize_daily),
            SimpleNamespace(finalize_success=self.finalize_manual),
        )
        # Composition binds business owners, including after a worker restart.
        self.retry._publication_workflow = self.workflow
        self.retry._analyst_subscriptions = self.subscriptions

    def tearDown(self):
        self.conn.close()

    @contextmanager
    def transaction(self):
        savepoint = self.conn.in_transaction
        self.conn.execute('SAVEPOINT recovery' if savepoint else 'BEGIN IMMEDIATE')
        try:
            yield self.repos
            self.conn.execute('RELEASE recovery') if savepoint else self.conn.commit()
        except BaseException:
            if savepoint:
                self.conn.execute('ROLLBACK TO recovery')
                self.conn.execute('RELEASE recovery')
            else:
                self.conn.rollback()
            raise

    def targets(self, mode):
        self.repos.publications.replace_targets(self.publication, [
            {'channel_id': channel_id, 'delivery_mode': mode, 'enabled': True}
            for channel_id in self.channel_ids
        ])

    def finalize_daily(self, key):
        self.legacy_calls['daily'] += 1
        return 77, 1

    def finalize_manual(self, key):
        self.legacy_calls['manual'] += 1

    async def test_draft_retry_uses_frozen_report_and_all_original_channels(self):
        draft = self.editorial.create_draft(self.draft_values([self.item(self.entry_id)]), 'editor')
        first = await self.workflow.publish_draft(draft['id'])
        self.assertEqual(first['status'], 'publishing')
        original = self.channel.calls[0][1]
        self.conn.execute("UPDATE review_entries SET title='later edit' WHERE id=?", (self.entry_id,))
        self.repos.publications.update_publication(self.publication, {'template': {'title_prefix': 'changed'}})
        self.repos.publications.replace_targets(self.publication, [])
        self.channel.blocked.clear()
        key = next(op['operation_key'] for op in first['operations'] if op['channel_slug'] == 'channel-b')
        await self.retry.retry(key)
        stored = self.repos.editorial_workbench.get_draft(draft['id'])
        self.assertEqual(stored['status'], 'published')
        report = self.conn.execute('SELECT * FROM daily_reports WHERE id=?', (stored['published_report_id'],)).fetchone()
        self.assertIn('original', report['content'])
        self.assertNotIn('later edit', report['content'])
        self.assertNotIn('changed', report['title'])
        self.assertEqual(self.channel.calls[-1][1], original)
        calls = len(self.channel.calls)
        await self.retry.retry(key)
        self.assertEqual(len(self.channel.calls), calls)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM daily_reports WHERE draft_id=?', (draft['id'],)).fetchone()[0], 1)
        self.assertEqual(self.legacy_calls['manual'], 0)

    async def test_correction_retry_finalizes_its_owner_without_repeating_sent_channels(self):
        correction_id = self.repos.editorial_workbench.add_correction(
            'correction', 'original correction', 'editor', report_id=None,
            review_entry_id=self.entry_id, event_id=None,
        )
        first = await self.workflow.publish_correction(correction_id)
        self.assertEqual(first['status'], 'publishing')
        self.assertIsNone(self.repos.editorial_workbench.get_correction(correction_id)['published_at'])
        self.channel.blocked.clear()
        key = next(op['operation_key'] for op in first['operations'] if op['channel_slug'] == 'channel-b')
        await self.retry.retry(key)
        self.assertIsNotNone(self.repos.editorial_workbench.get_correction(correction_id)['published_at'])
        self.assertEqual(sum(slug == 'channel-a' for slug, _ in self.channel.calls), 1)
        self.assertEqual(self.legacy_calls['manual'], 0)

    async def test_partial_retry_cannot_finalize_a_multi_target_business(self):
        self.channel.blocked = {'channel-a', 'channel-b'}
        correction_id = self.repos.editorial_workbench.add_correction(
            'correction', 'two failed channels', 'editor', report_id=None,
            review_entry_id=self.entry_id, event_id=None,
        )
        result = await self.workflow.publish_correction(correction_id)
        self.channel.blocked.remove('channel-a')
        partial = await self.retry.retry(result['operations'][0]['operation_key'])
        self.assertEqual(partial['business']['status'], 'publishing')
        self.assertIsNone(self.repos.editorial_workbench.get_correction(correction_id)['published_at'])
        self.channel.blocked.clear()
        await self.retry.retry(result['operations'][1]['operation_key'])
        self.assertIsNotNone(self.repos.editorial_workbench.get_correction(correction_id)['published_at'])

    async def test_all_target_acceptance_rolls_back_if_later_preparation_fails(self):
        draft = self.editorial.create_draft(self.draft_values([self.item(self.entry_id)]), 'editor')
        self.channel.limits['channel-b'] = 1
        with self.assertRaises(ValidationError):
            await self.workflow.publish_draft(draft['id'])
        self.assertEqual(self.repos.delivery_operations.list_operations(), [])
        self.assertEqual(self.delivery.active_plans('publication_draft'), [])
        self.assertEqual(self.repos.editorial_workbench.get_draft(draft['id'])['status'], 'draft')
        self.assertEqual(self.channel.calls, [])

    async def test_alert_preparation_failure_does_not_orphan_queued_match(self):
        policy = self.repos.intelligence_catalog.save_alert_policy({
            'name': 'too long', 'channel_id': self.channel_ids[0], 'schedule_type': 'instant',
        })
        self.repos.intelligence_catalog.save_alert_match(policy, self.event_id)
        self.conn.execute("UPDATE review_entries SET enriched_summary=? WHERE id=?", ('x' * 5000, self.entry_id))
        with self.assertRaises(ValidationError):
            await self.workflow.deliver_alert_matches()
        match = self.repos.intelligence_catalog.list_alert_matches(None)[0]
        self.assertEqual(match['status'], 'pending')
        self.assertIsNone(match['operation_key'])
        self.assertEqual(self.repos.delivery_operations.list_operations(), [])

    async def test_realtime_waits_for_every_original_target_and_keeps_legacy_dispatch(self):
        self.targets('realtime')
        first = await self.workflow.deliver_realtime_entries()
        self.assertEqual(first['sent_count'], 0)
        keys = [op['operation_key'] for row in first['results'] for op in row['operations'] if op['channel_slug'] == 'channel-b']
        self.conn.execute("UPDATE review_entries SET title='later realtime edit' WHERE id=?", (self.entry_id,))
        self.repos.publications.replace_targets(self.publication, [])
        self.channel.blocked.clear()
        await self.retry.retry(keys[0])
        self.assertIsNotNone(self.conn.execute('SELECT delivered_at FROM review_entries WHERE id=?', (self.entry_id,)).fetchone()[0])
        self.assertEqual(sum(slug == 'channel-a' for slug, _ in self.channel.calls), 2)
        self.assertNotIn('later realtime edit', self.channel.calls[-1][1])
        for kind in ('daily_auto', 'entry_manual', 'entry_auto'):
            key = f'legacy:{kind}:test'
            self.delivery.prepare(key, kind, 'news', ['legacy'], [], channel_slug='channel-a')
            await self.retry.retry(key)
        self.assertEqual(self.legacy_calls, Counter(daily=1, manual=2))

    async def test_realtime_changed_version_gets_an_independent_publication(self):
        self.targets('realtime')
        first = await self.workflow.deliver_realtime_entries()
        original = next(row for row in first['results'] if row['entry_id'] == self.entry_id)
        key = next(op['operation_key'] for op in original['operations'] if op['channel_slug'] == 'channel-b')
        self.editorial.update_entry(self.entry_id, {'title': 'new realtime revision'}, 'editor')
        self.channel.blocked.clear()
        await self.retry.retry(key)
        self.assertEqual(self.repos.editorial_workbench.get_entry(self.entry_id)['delivery_status'], 'pending')
        second = await self.workflow.deliver_realtime_entries()
        changed = next(row for row in second['results'] if row['entry_id'] == self.entry_id)
        self.assertNotEqual(changed['operations'][0]['operation_key'], original['operations'][0]['operation_key'])
        self.assertIn('new realtime revision', self.channel.calls[-1][1])
        self.assertEqual(self.repos.editorial_workbench.get_entry(self.entry_id)['delivery_status'], 'sent')

    async def test_subscription_recovers_frozen_payload_and_sent_before_finalization(self):
        sub = self.subscriptions.create({
            'name': 'test subscription', 'channel_id': self.channel_ids[1],
            'object_types': ['event'], 'content_types': [], 'profile_slugs': [],
            'batch_size': 50, 'start_from': 'beginning',
        })
        first = (await self.subscriptions.deliver(sub['id']))['results'][0]
        self.assertEqual(first['status'], 'failed')
        key = first['operation']['operation_key']
        original = self.channel.calls[0][1]
        self.conn.execute("UPDATE content_events SET title='later event edit' WHERE id=?", (self.event_id,))
        self.subscriptions.update(sub['id'], {'channel_id': self.channel_ids[0], 'object_types': []})
        self.channel.blocked.clear()
        await self.delivery.retry_operation(key)  # interruption after sent, before business completion
        calls = len(self.channel.calls)
        resumed = (await self.subscriptions.deliver(sub['id']))['results'][0]
        self.assertEqual(resumed['status'], 'sent')
        self.assertEqual(len(self.channel.calls), calls)
        self.assertEqual(self.channel.calls[-1], ('channel-b', original))
        stored = self.repos.analyst_subscriptions.get_subscription(sub['id'])
        self.assertEqual(stored['cursor'], first['cursor'])
        await self.retry.retry(key)
        self.assertEqual(self.repos.analyst_subscriptions.get_subscription(sub['id'])['cursor'], stored['cursor'])
        self.assertEqual(len(self.channel.calls), calls)

    async def test_subscription_adopts_legacy_payload_before_collecting_current_changes(self):
        sub = self.subscriptions.create({'name':'legacy subscription','channel_id':self.channel_ids[1],
            'object_types':['event'],'batch_size':1,'start_from':'beginning'})
        changes, cursor_to, has_more = self.subscriptions._collect(sub)
        payload = {'event':'ainews.analyst.changes','schema_version':1,'subscription':{'id':sub['id'],'name':sub['name']},
                   'cursor':{'from':sub['cursor'],'to':cursor_to,'has_more':has_more},'changes':changes}
        key = f"analyst-subscription:{sub['id']}:{sub['cursor']}-{cursor_to}"
        self.delivery.prepare(key, 'analyst_subscription', None, [json.dumps(payload)], [],
            metadata={'subscription_id':sub['id'],'cursor_from':sub['cursor'],'cursor_to':cursor_to}, channel_slug='channel-b')
        self.subscriptions.update(sub['id'], {'channel_id':self.channel_ids[0], 'object_types':['tag']})
        self.channel.blocked.clear()
        resumed = (await self.subscriptions.deliver(sub['id']))['results'][0]
        self.assertEqual(resumed['status'], 'sent')
        self.assertEqual(json.loads(self.channel.calls[-1][1]), payload)
        self.assertEqual(self.channel.calls[-1][0], 'channel-b')
        self.assertEqual(self.repos.analyst_subscriptions.get_subscription(sub['id'])['cursor'],cursor_to)

    async def test_alert_restart_recovers_orphans_and_requires_explicit_unknown_retry(self):
        policy = self.repos.intelligence_catalog.save_alert_policy({
            'name': 'recovery', 'channel_id': self.channel_ids[0], 'schedule_type': 'instant',
        })
        self.repos.intelligence_catalog.save_alert_match(policy, self.event_id)
        self.repos.intelligence_catalog.update_alert_match(policy, self.event_id, 'queued', 'old:missing:operation')
        self.channel.unknown.add('channel-a')
        result = await self.workflow.deliver_alert_matches()
        self.assertEqual(result['processed'], 1)
        key = result['results'][0]['delivery']['operation_key']
        calls = len(self.channel.calls)
        await self.workflow.deliver_alert_matches()
        self.assertEqual(len(self.channel.calls), calls)
        self.channel.unknown.clear()
        await self.retry.retry(key)
        match = self.repos.intelligence_catalog.list_alert_matches(None)[0]
        self.assertEqual(match['status'], 'sent')
        self.assertIsNotNone(match['delivered_at'])
        self.assertEqual(self.legacy_calls['manual'], 0)

    async def test_legacy_queued_alert_resumes_its_existing_pending_operation(self):
        policy = self.repos.intelligence_catalog.save_alert_policy({
            'name': 'legacy pending', 'channel_id': self.channel_ids[0], 'schedule_type': 'instant',
        })
        key = f'legacy-alert:{policy}:{self.event_id}'
        self.delivery.prepare(key, 'event_alert', 'news', ['original accepted alert'], [],
                              metadata={'policy_id': policy, 'event_ids': [self.event_id]}, channel_slug='channel-a')
        self.repos.intelligence_catalog.save_alert_match(policy, self.event_id)
        self.repos.intelligence_catalog.update_alert_match(policy, self.event_id, 'queued', key)
        await self.workflow.deliver_alert_matches()
        match = self.repos.intelligence_catalog.list_alert_matches(None)[0]
        self.assertEqual(match['status'], 'sent')
        self.assertEqual(self.channel.calls, [('channel-a', 'original accepted alert')])
        await self.workflow.deliver_alert_matches()
        self.assertEqual(len(self.channel.calls), 1)

    async def test_alert_eligible_tail_drains_across_restarted_batches(self):
        eligible = self.repos.intelligence_catalog.save_alert_policy({
            'name': 'eligible', 'channel_id': self.channel_ids[0], 'schedule_type': 'instant',
        })
        deferred = self.repos.intelligence_catalog.save_alert_policy({
            'name': 'deferred', 'channel_id': self.channel_ids[0], 'schedule_type': 'instant',
            'enabled': False,
        })
        ids = [self.seed_entry('daily-briefs', 'news', f'tail-{i}')[1] for i in range(405)]
        for event_id in ids:
            self.repos.intelligence_catalog.save_alert_match(eligible, event_id)
        for event_id in ids[:205]:
            self.repos.intelligence_catalog.save_alert_match(deferred, event_id)
        # The newer deferred head must not hide the eligible tail.
        self.conn.execute("UPDATE alert_matches SET matched_at='2099-01-01' WHERE policy_id=?", (deferred,))
        counts = []
        for _ in range(3):
            counts.append((await self.workflow.deliver_alert_matches(limit=200))['processed'])
        self.assertEqual(counts, [200, 200, 5])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM alert_matches WHERE policy_id=? AND status='sent'", (eligible,)).fetchone()[0], 405)
        self.assertEqual(len(self.channel.calls), 405)
