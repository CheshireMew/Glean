from __future__ import annotations

import json
import sqlite3
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx

from backend.app.core.config import settings
from backend.app.infrastructure.repository_impl.news_repository import NewsRepository
from backend.app.infrastructure.scraper_impl import browser_runtime
from backend.app.infrastructure.scraper_impl.blockbeats import BlockBeatsScraper
from backend.app.infrastructure.scraper_impl.blockbeats_article import (
    BlockBeatsArticleScraper,
)
from backend.app.infrastructure.scraper_impl.chaincatcher import ChainCatcherScraper
from backend.app.infrastructure.scraper_impl.chaincatcher_article import (
    ChainCatcherArticleScraper,
)
from backend.app.infrastructure.scraper_impl.marsbit import MarsBitScraper
from backend.app.infrastructure.scraper_impl.marsbit_article import (
    MarsBitArticleScraper,
)
from backend.app.infrastructure.scraper_impl.media_feed import published_at
from backend.app.infrastructure.scraper_impl.odaily import OdailyScraper
from backend.app.infrastructure.scraper_impl.odaily_article import OdailyArticleScraper
from backend.app.infrastructure.scraper_impl.panews import PANewsScraper
from backend.app.infrastructure.scraper_impl.source_transport import HttpSourceTransport
from backend.app.infrastructure.scraper_impl.techflow_article import (
    TechflowArticleScraper,
)
from backend.app.infrastructure.scraper_impl.wublock_article import (
    WuBlockArticleScraper,
)
from backend.app.infrastructure.scrapers import ScraperCatalog
from backend.app.infrastructure.sqlite.sqlite_schema import create_news_table


def feed(*entries):
    return ('<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">'
            '<channel>' + ''.join(entries) + '</channel></rss>')


def entry(url, *categories, content='真实正文', title='标题'):
    return (f'<item><title>{title}</title><link>{url}</link>'
            '<pubDate>Mon, 05 Oct 2026 09:00:00 GMT</pubDate>'
            '<description>短摘要</description>'
            f'<content:encoded><![CDATA[<p>{content}</p><p>末段</p>]]></content:encoded>'
            + ''.join(f'<category>{category}</category>' for category in categories) + '</item>')


def odaily_row(identifier, important=True):
    return {'title': f'快讯 {identifier}', 'content': '<p>来自接口的正文</p>',
            'link': f'https://www.odaily.news/zh-CN/newsflash/{identifier}',
            'isImportant': important, 'publishTimestamp': 1791191803000}


class CryptoMediaTest(unittest.IsolatedAsyncioTestCase):
    def test_fixed_source_names_and_content_kinds_survive_migration(self):
        expected = {'techflow': 'techflow', 'odaily': 'odaily', 'blockbeats': 'blockbeats',
                    'chaincatcher': 'chaincatcher', 'panews': 'panews', 'marsbit': 'marsbit',
                    'blockbeats_article': 'BlockBeats Article', 'chaincatcher_article': 'ChainCatcher Article',
                    'marsbit_article': 'MarsBit Article', 'odaily_article': 'Odaily Article',
                    'panews_article': 'PANews Article', 'techflow_article': 'Techflow Article',
                    'wublock_article': 'WuBlock Article'}
        catalog = ScraperCatalog()
        for name, source_site in expected.items():
            scraper = catalog.get(name).scraper_cls()
            self.assertEqual(scraper.site_name, source_site)
            self.assertEqual(scraper.news_type, catalog.get(name).content_kind)
            self.assertNotEqual(scraper.transport_kind, 'browser')
        for name in ('foresight', 'foresight_exclusive', 'foresight_express', 'foresight_depth'):
            self.assertEqual(catalog.get(name).scraper_cls.transport_kind, 'browser')

    async def test_rss_reads_beyond_known_entries_and_compares_old_locale_urls(self):
        scraper = TechflowArticleScraper()
        scraper.max_items = 1
        scraper.existing_urls = {f'https://www.techflowpost.com/zh-CN/article/{i}' for i in range(3)}
        scraper.fetch_text = AsyncMock(return_value=feed(*(entry(f'https://www.techflowpost.com/article/{i}') for i in range(4))))
        saved = []
        scraper.item_callback = saved.append
        items = await scraper.scrape_important_news()
        self.assertEqual([item['url'] for item in items], ['https://www.techflowpost.com/article/3'])
        self.assertEqual(saved, items)
        self.assertTrue(scraper.encountered_existing_items)

    def test_chain_category_and_wu_depth_filter_keep_mixed_feed_out(self):
        xml = feed(entry('https://www.chaincatcher.com/article/1', '快讯'),
                   entry('https://www.chaincatcher.com/article/2', '文章'))
        items = ChainCatcherArticleScraper().parse_entries(xml)
        self.assertEqual([item['url'] for item in items], ['https://www.chaincatcher.com/article/2'])
        self.assertFalse(items[0]['is_marked_important'])
        xml = feed(entry('https://www.wublock123.com/news/1', '快讯', '深度'),
                   entry('https://www.wublock123.com/articles/2', '文章', '项目周报'),
                   entry('https://www.wublock123.com/articles/3', '文章', '深度'))
        self.assertEqual([item['url'] for item in WuBlockArticleScraper().parse_entries(xml)],
                         ['https://www.wublock123.com/articles/3'])
        self.assertEqual(WuBlockArticleScraper().parse_entries(feed(entry('https://www.wublock123.com/news/1', '快讯'))), [])

    def test_feed_full_body_dates_and_featured_flag(self):
        items = PANewsScraper().parse_entries(feed(entry('https://www.panewslab.com/zh/articles/id', content='正文' * 500)))
        self.assertGreater(len(items[0]['content']), 1000)
        self.assertTrue(items[0]['content'].endswith('末段'))
        self.assertEqual(items[0]['published_at'], '2026-10-05 17:00:00')
        self.assertTrue(items[0]['is_marked_important'])
        self.assertEqual(items[0]['site_importance_flag'], 'featured')
        with self.assertRaises(RuntimeError):
            PANewsScraper().parse_entries('{"status":0,"data":[]}')

    def test_rss_missing_required_category_is_an_error_not_an_empty_update(self):
        for scraper, url in [(ChainCatcherArticleScraper(), 'https://www.chaincatcher.com/article/1'),
                             (WuBlockArticleScraper(), 'https://www.wublock123.com/articles/1')]:
            with self.subTest(source=scraper.site_name), self.assertRaisesRegex(RuntimeError, '栏目分类'):
                scraper.parse_entries(feed(entry(url)))

    async def test_odaily_locally_filters_important_and_pages_to_fill_limit(self):
        scraper = OdailyScraper()
        scraper.max_items = 2
        scraper.transport.fetch_json = AsyncMock(side_effect=[
            {'code': 200, 'success': True, 'data': {'list': [odaily_row(1, False), odaily_row(2)], 'hasMore': True}},
            {'code': 200, 'success': True, 'data': {'list': [odaily_row(3)], 'hasMore': False}},
        ])
        items = await scraper.scrape_important_news()
        self.assertEqual([item['title'] for item in items], ['快讯 2', '快讯 3'])
        self.assertEqual(scraper.transport.fetch_json.await_count, 2)
        self.assertTrue(all(item['is_marked_important'] for item in items))
        self.assertIn('page=2', scraper.transport.fetch_json.call_args.args[0])

    async def test_api_reordered_known_rows_do_not_hide_later_new_items(self):
        scraper = OdailyScraper()
        scraper.max_items = 1
        scraper.existing_urls = {odaily_row(i)['link'] for i in range(3)}
        scraper.transport.fetch_json = AsyncMock(return_value={
            'code': 200, 'success': True, 'data': {'list': [odaily_row(i) for i in range(4)], 'hasMore': False}})
        self.assertEqual([item['title'] for item in await scraper.scrape_important_news()], ['快讯 3'])

    async def test_api_known_page_does_not_hide_a_new_post_on_the_next_page(self):
        scraper = OdailyScraper()
        scraper.max_items = 1
        scraper.existing_urls = {odaily_row(1)['link']}
        scraper.transport.fetch_json = AsyncMock(side_effect=[
            {'code': 200, 'success': True, 'data': {'list': [odaily_row(1)], 'hasMore': True}},
            {'code': 200, 'success': True, 'data': {'list': [odaily_row(2)], 'hasMore': False}},
        ])
        self.assertEqual([item['title'] for item in await scraper.scrape_important_news()], ['快讯 2'])

    def test_plain_text_api_fields_keep_angle_brackets(self):
        row = {'id': 1, 'type': 2, 'newsFlashType': 2, 'title': '输入 <GO> 查看行情',
               'description': '彭博终端输入 WSL HYPE <GO>\n保留原文', 'releaseTime': '2026-10-05 17:00:00'}
        item = ChainCatcherScraper().parse_item(row)
        self.assertEqual(item['title'], row['title'])
        self.assertEqual(item['content'], row['description'])
        article = MarsBitArticleScraper().parse_item({'id': 1, 'title': '摘要', 'synopsis': '【GPT】关注 <POLY>',
                                                     'publishTime': 1791191803000})
        self.assertEqual(article['content'], '【GPT】关注 <POLY>')

    async def test_chain_api_uses_selected_field_and_total_for_pagination(self):
        scraper = ChainCatcherScraper()
        scraper.page_size = 1
        scraper.max_items = 1
        scraper.transport.fetch_json = AsyncMock(side_effect=[
            {'result': 1, 'data': {'total': 2, 'items': [{'id': 1, 'type': 2, 'newsFlashType': 1}]}},
            {'result': 1, 'data': {'total': 2, 'items': [{'id': 2, 'type': 2, 'newsFlashType': 2,
                'title': '精选', 'description': '接口内容', 'releaseTime': '2026-10-05 17:00:00'}]}},
        ])
        items = await scraper.scrape_important_news()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['site_importance_flag'], 'newsFlashType=2')
        self.assertEqual(scraper.transport.fetch_json.call_args.kwargs['json_body']['pageNumber'], 2)
        self.assertEqual(scraper.transport.fetch_json.call_args.kwargs['json_body']['newsFlashTypes'], [2])

    def test_mars_important_body_canonical_url_and_real_article_summary(self):
        scraper = MarsBitScraper()
        raw = {'id': '123', 'tag': 2, 'content': '<p>【标题】正文内容</p>', 'createdTime': 1791191803000,
               'url': 'https://external.test/source'}
        item = scraper.parse_item(raw)
        self.assertEqual(item['title'], '标题')
        self.assertEqual(item['content'], '正文内容')
        self.assertEqual(item['url'], 'https://news.marsbit.co/flash/123.html')
        self.assertIsNone(scraper.parse_item(dict(raw, tag=1)))
        article = MarsBitArticleScraper().parse_item({'id': '456', 'title': '文章', 'synopsis': '【GPT】网站摘要',
                                                   'publishTime': 1791191803000})
        self.assertEqual(article['content'], '【GPT】网站摘要')
        self.assertFalse(article['is_marked_important'])

    def test_missing_flags_and_dates_are_errors_not_empty_success(self):
        for scraper, raw in [(OdailyScraper(), {}), (ChainCatcherScraper(), {}), (MarsBitScraper(), {})]:
            with self.assertRaises(RuntimeError):
                scraper.parse_item(raw)
        with self.assertRaises(RuntimeError):
            published_at('bad-date')
        self.assertEqual(OdailyArticleScraper().parse_item(dict(odaily_row(1), content=''))['content'], '')

    async def test_business_error_is_not_a_successful_empty_list(self):
        for scraper, body in [(OdailyScraper(), {'code': 403, 'success': False}),
                              (ChainCatcherScraper(), {'result': 0}), (MarsBitScraper(), {'code': 0})]:
            scraper.transport.fetch_json = AsyncMock(return_value=body)
            with self.assertRaises(RuntimeError):
                await scraper.scrape_important_news()

    async def test_full_body_structured_author_and_identity_reach_sqlite(self):
        conn = sqlite3.connect(':memory:')
        try:
            create_news_table(conn.cursor())
            scraper = OdailyArticleScraper()
            row = dict(odaily_row(1), content='<p>' + '全文' * 1000 + '</p>',
                       author={'nickname': '真实作者', 'title': '资深作者'})
            scraper.transport.fetch_json = AsyncMock(return_value={
                'code': 200, 'success': True, 'data': {'list': [row], 'hasMore': False}})
            scraper.item_callback = NewsRepository(conn).insert_news
            items = await scraper.scrape_important_news()
            stored = conn.execute('SELECT source_site, type, author, content, is_marked_important, published_at FROM news').fetchone()
            self.assertEqual(stored[:3], ('Odaily Article', 'article', '真实作者'))
            self.assertEqual(stored[3], '全文' * 1000)
            self.assertEqual(stored[4:], (0, '2026-10-05 09:16:43'))
            self.assertEqual(items[0]['source_site'], stored[0])
            self.assertEqual(scraper.persistence_errors, [])
        finally:
            conn.close()

    async def test_blockbeats_missing_key_makes_no_request_and_union_is_deduplicated(self):
        scraper = BlockBeatsScraper()
        scraper.transport_kind = 'api'
        scraper.api_url = scraper.endpoint
        scraper.transport.fetch_json = AsyncMock()
        with patch.object(settings, 'BLOCKBEATS_API_KEY', ''), self.assertRaisesRegex(RuntimeError, 'BLOCKBEATS_API_KEY'):
            await scraper.scrape_important_news()
        scraper.transport.fetch_json.assert_not_awaited()
        row = {'id': 1, 'title': '重要', 'content': '<p>正文</p>', 'link': 'https://m.theblockbeats.info/flash/1',
               'create_time': '2026-10-05 17:00:00'}
        scraper.transport.fetch_json = AsyncMock(side_effect=[
            {'status': 0, 'data': {'page': 1, 'data': [row]}},
            {'status': 0, 'data': {'page': 1, 'data': [row, dict(row, id=2, title='首发', link='https://m.theblockbeats.info/flash/2')]}}
        ])
        with patch.object(settings, 'BLOCKBEATS_API_KEY', 'test-only-key'):
            items = await scraper.scrape_important_news()
        self.assertEqual(len(items), 2)
        self.assertEqual(items[1]['site_importance_flag'], 'first')
        self.assertTrue(all(item['url'].startswith('https://www.theblockbeats.info/') for item in items))
        self.assertEqual(scraper.transport.fetch_json.call_args.kwargs['headers'], {'api-key': 'test-only-key'})

    async def test_blockbeats_http_preserves_selection_dates_and_incremental_history_without_key(self):
        html = '''<div class="flash-list"><div class="flash-list-today">2026-10-06</div>
          <div class="news-flash-wrapper"><a class="news-flash-title" href="/flash/1">00:10
            <div class="news-flash-title-text news-flash-title-text-active">已知重要</div></a>
            <div class="news-flash-item-content"><p>重要正文</p></div></div>
          <div class="news-flash-wrapper"><a class="news-flash-title" href="/flash/2">00:05
            <img class="home-first-png"><div class="news-flash-title-text">首发 &lt;GO&gt;</div></a>
            <div class="news-flash-item-content"><p>首段</p><p>末段</p></div></div>
          <div class="news-flash-wrapper"><a class="news-flash-title" href="/flash/3">00:01
            <div class="news-flash-title-text">普通快讯</div></a></div>
          <div class="news-flash-wrapper"><a class="news-flash-title" href="/flash/2">00:05
            <img class="home-first-png"><div class="news-flash-title-text">重复首发</div></a>
            <div class="news-flash-item-content">重复</div></div></div>
          <div class="flash-list"><div class="flash-list-today">2026-10-05</div>
          <div class="news-flash-wrapper"><a class="news-flash-title" href="/flash/4">23:59
            <img class="home-first-png"><div class="news-flash-title-text news-flash-title-text-active">昨天的快讯</div></a>
            <div class="news-flash-item-content">昨天正文</div></div>
          <div class="news-flash-wrapper"><a class="news-flash-title" href="/flash/5">23:58
            <div class="news-flash-title-text news-flash-title-text-active">付费快讯</div></a>
            <a class="premium-unlock-btn">解锁</a></div></div>'''
        with patch.object(BlockBeatsScraper, 'transport_kind', 'http'), patch.object(settings, 'BLOCKBEATS_API_KEY', ''):
            scraper = BlockBeatsScraper()
            scraper.max_items = 2
            scraper.existing_urls = {'https://m.theblockbeats.info/flash/1'}
            scraper.fetch_text = AsyncMock(return_value=html)
            scraper.transport.start = AsyncMock()
            scraper.transport.close = AsyncMock()
            scraper.transport.fetch_json = AsyncMock()
            saved = []
            scraper.item_callback = saved.append
            self.assertIsNone(scraper.configuration_error())
            items = await scraper.run()
            self.assertEqual([item['url'].rsplit('/', 1)[1] for item in items], ['2', '4'])
            self.assertEqual(items[0]['title'], '首发 <GO>')
            self.assertEqual(items[0]['content'], '首段\n\n末段')
            self.assertEqual([item['published_at'] for item in items], ['2026-10-06 00:05:00', '2026-10-05 23:59:00'])
            self.assertEqual([item['site_importance_flag'] for item in items], ['first', 'important+first'])
            self.assertTrue(all(item['source_site'] == 'blockbeats' and item['type'] == 'news' for item in items))
            self.assertEqual(saved, items)
            scraper.transport.fetch_json.assert_not_awaited()
            scraper.fetch_text.assert_awaited_once_with('https://www.theblockbeats.info/newsflash')
            scraper.existing_urls.update(item['url'] for item in items)
            self.assertEqual(await scraper.run(), [])

    def test_blockbeats_http_structure_changes_fail_instead_of_returning_empty(self):
        scraper = BlockBeatsScraper()
        for html in ('<html>维护页面</html>',
                     '<div class="flash-list"><div class="news-flash-wrapper"></div></div>',
                     '<div class="flash-list"><div class="flash-list-today">2026-10-06</div><div class="news-flash-wrapper"></div></div>'):
            with self.subTest(html=html), self.assertRaises(RuntimeError):
                scraper.parse_public_news(html)

    async def test_blockbeats_article_http_remains_usable_without_key(self):
        scraper = BlockBeatsArticleScraper()
        scraper.transport_kind = 'http'
        scraper.api_url = scraper.homepage + '/article_choice'
        metadata = {'@type': 'NewsArticle', 'headline': '文章', 'datePublished': '2026-10-05T09:00:00Z',
                    'author': {'name': '作者'}}
        scraper.fetch_text = AsyncMock(side_effect=[
            '<a class="article-item-title" href="/news/1">文章</a>',
            '<div class="news-content"><p>真实正文</p></div><script type="application/ld+json">'
            + json.dumps(metadata) + '</script>',
        ])
        items = await scraper.scrape_important_news()
        self.assertEqual(items[0]['content'], '真实正文')
        self.assertEqual(items[0]['published_at'], '2026-10-05 17:00:00')
        self.assertEqual(items[0]['author'], '作者')

    async def test_blockbeats_article_with_key_uses_api_and_business_errors_fail(self):
        with patch.object(BlockBeatsArticleScraper, 'transport_kind', 'api'), patch.object(settings, 'BLOCKBEATS_API_KEY', 'test-only-key'):
            scraper = BlockBeatsArticleScraper()
            scraper.fetch_text = AsyncMock()
            scraper.transport.fetch_json = AsyncMock(return_value={'status': 0, 'data': {'page': 1, 'data': [
                {'title': '精选文章', 'content': '<p>文章全文</p>', 'link': 'https://m.theblockbeats.info/news/1',
                 'author': {'name': '作者'}, 'create_time': '2026-10-05 17:00:00'}]}})
            items = await scraper.scrape_important_news()
            self.assertEqual(items[0]['content'], '文章全文')
            self.assertEqual(items[0]['author'], '作者')
            self.assertFalse(items[0]['is_marked_important'])
            self.assertIn('/v1/article/important?', scraper.transport.fetch_json.call_args.args[0])
            scraper.fetch_text.assert_not_awaited()
            scraper.transport.fetch_json = AsyncMock(return_value={'status': 100, 'message': 'test-only-key'})
            with self.assertRaisesRegex(RuntimeError, '认证、额度或业务请求失败') as caught:
                await scraper.scrape_important_news()
            self.assertNotIn('test-only-key', str(caught.exception))

    async def test_api_key_stays_on_its_own_origin_after_redirect(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(302, headers={'Location': 'https://other.test/list'}) if len(requests) == 1 else httpx.Response(200, json={})
        access = SimpleNamespace(wait=AsyncMock(), inspect=Mock())
        transport = HttpSourceTransport(access=access)
        transport.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            await transport.fetch_json('https://media.test/list', headers={'api-key': 'test-only-key'})
            self.assertEqual(requests[0].headers['api-key'], 'test-only-key')
            self.assertNotIn('api-key', requests[1].headers)
        finally:
            await transport.close(None)

    async def test_prefetch_does_not_use_content_budget(self):
        owner = SimpleNamespace(base_url='https://media.test/', _source_access_error=None,
                                _source_access=SimpleNamespace(wait=AsyncMock(), assert_allowed=Mock()))
        for headers in ({'purpose': 'prefetch'}, {'next-router-prefetch': '1'}, {'sec-purpose': 'prefetch;prerender'}):
            route = SimpleNamespace(request=SimpleNamespace(resource_type='fetch', url=owner.base_url, headers=headers),
                                    abort=AsyncMock(), fetch=AsyncMock())
            await browser_runtime.pace_browser_request(owner, route)
            route.abort.assert_awaited_once()
            route.fetch.assert_not_awaited()
        owner._source_access.wait.assert_not_awaited()

    async def test_browser_closing_error_does_not_cool_down_source(self):
        page = Mock()
        page.is_closed.return_value = True
        owner = SimpleNamespace(base_url='https://media.test/', _source_access_error=None,
                                _source_access=SimpleNamespace(wait=AsyncMock(), defer=Mock()), _source_closing=True)
        route = SimpleNamespace(request=SimpleNamespace(resource_type='fetch', url=owner.base_url, method='GET',
                                headers={}, frame=SimpleNamespace(page=page)),
                                fetch=AsyncMock(side_effect=RuntimeError('Target closed')), abort=AsyncMock())
        await browser_runtime.pace_browser_request(owner, route)
        owner._source_access.defer.assert_not_called()
        self.assertIsNone(owner._source_access_error)
