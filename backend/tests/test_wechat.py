from __future__ import annotations

import json
import sqlite3
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import httpx

from backend.app.composition import AppServices
from backend.app.core.exceptions import BusinessError
from backend.app.domain.ai_sources import ai_source_sql
from backend.app.infrastructure.database import database, init_database
from backend.app.infrastructure.repositories import repositories
from backend.app.infrastructure.scraper_impl.wechat import WechatScraper
from backend.app.infrastructure.sqlite.sqlite_migration_plan import (
    AI_TRANSLATIONS_VERSION,
    WECHAT_VERSION,
    resolve_migration_plan,
)
from backend.app.infrastructure.wechat_gateway import article_url
from backend.app.routers.auth import get_current_user
from backend.main import app


def article(number=1, digest='原文摘要', **extra):
    return {'title': f'测试文章 {number}', 'digest': digest, 'create_time': 1790488800,
            'link': f'https://mp.weixin.qq.com/s?__biz=ABC&mid={number}&idx=1&sn=xyz&chksm=tracking#rd',
            **extra}


def page_payload(items):
    return {'base_resp': {'ret': 0}, 'publish_page': json.dumps({'publish_list': [
        {'publish_info': json.dumps({'appmsgex': items})}
    ]})}


@contextmanager
def wechat_http(handler):
    client = httpx.AsyncClient
    with patch('backend.app.infrastructure.wechat_gateway.httpx.AsyncClient',
               side_effect=lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs)):
        yield


class WechatTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=r'D:\Tools')
        self.previous = database.db_path
        database.db_path = str(Path(self.folder.name) / 'wechat-test.db')
        init_database()
        self.services = AppServices()
        self.service = self.services.wechat_sources
        self.source = self.service.add_source({'fake_id': 'test-account', 'name': '测试公众号'})
        self.session = {'token': 'private-test-token', 'cookies': [
            {'name': 'slave_sid', 'value': 'private-test-cookie', 'domain': 'mp.weixin.qq.com', 'path': '/'}],
            'session_id': 'test-session', 'saved_at': time.time()}
        self.service.save_session(self.session)

    async def asyncTearDown(self):
        app.dependency_overrides.clear()
        database.db_path = self.previous
        self.folder.cleanup()

    def test_migration_adds_table_without_rewriting_existing_records(self):
        conn = sqlite3.connect(':memory:')
        conn.execute('CREATE TABLE news (id INTEGER PRIMARY KEY, title TEXT)')
        conn.execute("INSERT INTO news VALUES (1, '原数据')")
        for step in resolve_migration_plan(AI_TRANSLATIONS_VERSION):
            step.apply(conn.cursor())
            if step.to_version == WECHAT_VERSION:
                break
        self.assertEqual(conn.execute('SELECT title FROM news').fetchone()[0], '原数据')
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM wechat_sources').fetchone()[0], 0)
        conn.close()

    async def test_search_uses_stored_session_and_returns_only_public_account_fields(self):
        requests = []
        def respond(request):
            requests.append(request)
            return httpx.Response(200, json={'base_resp': {'ret': 0}, 'total': 8, 'list': [
                {'fakeid': 'target', 'nickname': '真正的名称', 'alias': 'real_account', 'signature': '<p>介绍</p>'}]})
        with wechat_http(respond):
            result = await self.services.wechat_gateway.search('名称')
        self.assertEqual(result['accounts'][0]['name'], '真正的名称')
        self.assertEqual(result['accounts'][0]['introduction'], '介绍')
        self.assertTrue(result['has_more'])
        self.assertEqual(requests[0].url.params['token'], 'private-test-token')
        self.assertIn('slave_sid=private-test-cookie', requests[0].headers['cookie'])
        self.assertNotIn('private-test', json.dumps(result))
        self.assertNotIn('private-test', json.dumps(self.service.status()))

    async def test_article_collection_persistence_dedup_and_ai_destination(self):
        source = self.source
        items = [article(1, '<p>真实摘要</p>'), article(1), article(2, '')]
        scraper = self.services.scraper_registry.require(f"wechat__{source['id']}").build_scraper()
        scraper.item_callback = repositories().news.insert_news
        with wechat_http(lambda request: httpx.Response(200, json=page_payload(items))), \
                patch.object(self.services.wechat_gateway, '_reserve_request', return_value=0):
            first = await scraper.run()
            scraper.existing_urls = {row['url'] for row in first}
            second = await scraper.run()
        self.assertEqual(len(first), 2)
        self.assertEqual(second, [])
        self.assertEqual(first[0]['content'], '真实摘要')
        self.assertEqual(first[1]['content'], '')
        result = self.services.ai_content.get_content(f"wechat__{source['id']}", '', 20, 0)
        self.assertEqual(result['total'], 2)
        self.assertEqual({row['source_excerpt'] for row in result['items']}, {'真实摘要', ''})
        self.assertNotIn('tracking', first[0]['url'])
        self.assertTrue(all(row['source_site'] == '公众号：测试公众号' for row in first))
        excluded = repositories().news.execute(f'SELECT count(*) AS count FROM news WHERE NOT {ai_source_sql("source_site")}').fetchone()
        self.assertEqual(excluded['count'], 0)

    async def test_expired_session_stops_requests_until_rescan(self):
        calls = []
        def respond(request):
            calls.append(request)
            return httpx.Response(200, json={'base_resp': {'ret': 200003}})
        with wechat_http(respond):
            with self.assertRaisesRegex(BusinessError, '重新扫码'):
                await self.services.wechat_gateway.search('test')
            with self.assertRaisesRegex(BusinessError, '扫码登录'):
                await self.services.wechat_gateway.search('test')
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.service.status()['state'], 'expired')
        self.service.save_session({**self.session, 'session_id': 'renewed'})
        self.service.mark_failure(self.session, 'expired', '旧请求失败')
        self.assertEqual(self.service.status()['state'], 'connected')

    async def test_existing_worker_runner_saves_items_and_finishes_successfully(self):
        runtime_name = f"wechat__{self.source['id']}"
        self.services.scraper_runs.configure_worker('test-worker')
        with wechat_http(lambda request: httpx.Response(200, json=page_payload([article()]))), \
                patch.object(self.services.wechat_gateway, '_reserve_request', return_value=0):
            self.assertTrue(self.services.scraper_runs.launch_scraper(runtime_name, 10))
            await self.services.scraper_runs._running_tasks[runtime_name]
        state = self.services.scraper_runtime_state.get_scraper_state(runtime_name)
        self.assertEqual(state['status'], 'idle')
        self.assertIsNone(state['last_error'])
        self.assertEqual(state['items_scraped'], 1)
        self.assertEqual(self.services.ai_content.get_content(runtime_name, '', 10, 0)['total'], 1)

    async def test_rate_limit_cooldown_survives_new_service_instance(self):
        with wechat_http(lambda request: httpx.Response(200, json={'base_resp': {'ret': 200013}})), \
                self.assertRaisesRegex(BusinessError, '30 分钟'):
            await self.services.wechat_gateway.search('test')
        restarted = AppServices()
        self.assertEqual(restarted.wechat_sources.status()['state'], 'limited')
        with self.assertRaisesRegex(BusinessError, '访问频率'):
            await restarted.wechat_gateway.search('test')

    async def test_queued_request_respects_limits_detected_while_waiting(self):
        def reserve_then_limit():
            self.service.mark_failure(self.session, 'limited', '限流')
            return 0

        with patch.object(self.services.wechat_gateway, '_reserve_request', side_effect=reserve_then_limit), \
                wechat_http(lambda request: self.fail('限流后不应继续请求微信')), \
                self.assertRaisesRegex(BusinessError, '访问频率'):
            await self.services.wechat_gateway.search('test')

    async def test_invalid_payload_is_failure_not_empty_success(self):
        for payload in ({}, {'base_resp': {'ret': 0}, 'publish_page': '{}'}, page_payload([{'title': '缺少链接'}])):
            with self.subTest(payload=payload), \
                    wechat_http(lambda request, payload=payload: httpx.Response(200, json=payload)), \
                    patch.object(self.services.wechat_gateway, '_reserve_request', return_value=0), \
                    self.assertRaises((BusinessError, RuntimeError)):
                await WechatScraper(self.source, self.services.wechat_gateway).run()

    def test_duplicate_subscription_settings_and_disabled_history(self):
        self.assertEqual(self.service.add_source({'fake_id': 'test-account', 'name': '测试公众号'})['id'], self.source['id'])
        self.assertEqual(len(self.service.list_sources()), 1)
        self.services.scraper_runtime_state.ensure_runtime_initialized()
        runtime_name = f"wechat__{self.source['id']}"
        self.service.update_source(self.source['id'], {'enabled': True, 'default_limit': 15, 'default_interval': 360})
        self.assertEqual(self.services.scraper_runtime_state.get_scraper_config(runtime_name)['interval'], 360)
        self.service.update_source(self.source['id'], {'enabled': False, 'default_limit': 15, 'default_interval': 360})
        self.assertNotIn(runtime_name, self.services.scraper_registry.names())
        self.assertNotIn(runtime_name, [row['key'] for row in self.services.ai_content.get_content(None, '', 10, 0)['sources']])

    def test_cross_process_request_slots_are_spaced(self):
        with patch('backend.app.services.wechat_source_service.time.time', return_value=1000):
            self.assertEqual(self.service.reserve_request(), 0)
            self.assertEqual(AppServices().wechat_sources.reserve_request(), 3)
            self.assertEqual(self.service.reserve_request(), 6)

    async def test_admin_api_protects_login_and_credentials(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            self.assertIn((await client.get('/api/wechat/status')).status_code, (401, 403))
            self.assertIn((await client.post('/api/wechat/login')).status_code, (401, 403))
            app.dependency_overrides[get_current_user] = lambda: 'test-admin'
            response = await client.get('/api/wechat/status')
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('private-test', response.text)
            response = await client.get('/api/wechat/sources')
            self.assertEqual(response.json()['data']['sources'][0]['runtime_name'], f"wechat__{self.source['id']}")
            response = await client.put(f"/api/wechat/sources/{self.source['id']}", json={'default_interval': 1})
            self.assertEqual(response.status_code, 422)

    def test_canonical_article_url_does_not_accept_other_hosts(self):
        self.assertEqual(article_url('https://example.com/s/xyz'), '')
        self.assertEqual(article_url('javascript:alert(1)'), '')
        self.assertEqual(article_url('https://mp.weixin.qq.com/s'), '')
        self.assertEqual(article_url('https://mp.weixin.qq.com/s/AbC?scene=1#rd'), 'https://mp.weixin.qq.com/s/AbC')

    async def test_disconnect_keeps_subscription_and_article_data(self):
        await self.service.disconnect()
        self.assertEqual(self.service.status()['state'], 'disconnected')
        self.assertEqual(len(self.service.list_sources()), 1)
        with self.assertRaisesRegex(BusinessError, '扫码登录'):
            await self.services.wechat_gateway.search('test')


if __name__ == '__main__':
    unittest.main()
