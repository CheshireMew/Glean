from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
from threading import Barrier
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
import uuid

from backend.app.domain.source_identity import source_identity
from backend.app.infrastructure.event_clustering import EventClusterer
from backend.app.infrastructure.repository_impl.archive_repository import ArchiveRepository
from backend.app.infrastructure.repository_impl.event_query_repository import EventQueryRepository
from backend.app.infrastructure.repository_impl.event_repository import EventRepository
from backend.app.infrastructure.repository_impl.news_repository import NewsRepository
from backend.app.infrastructure.scraper_impl.base import CANDIDATE_ACCEPT, CANDIDATE_SKIP, ScrapeCandidateCollector
from backend.app.infrastructure.scraper_impl.foresight_article import ForesightExclusiveScraper
from backend.app.infrastructure.scraper_impl.media_feed import MediaSnapshot, media_identity
from backend.app.infrastructure.scraper_impl.techflow_article import TechflowArticleScraper
from backend.app.infrastructure.sqlite import sqlite_migration_plan as migration
from backend.app.infrastructure.sqlite.db_sqlite import Database
from backend.app.infrastructure.sqlite.sqlite_schema import create_news_table
from backend.app.infrastructure.sqlite.news_identity_schema import create_news_identity_schema
from backend.app.services.content_transition_service import ContentTransitionService


def news(url, title='项目A完成1000万美元融资'):
    return dict(title=title, content='真实正文', source_site='Techflow Article', url=url,
                published_at='2026-10-06 10:00:00', type='news')


def items(*titles):
    return [dict(news(f'https://source.test/{index}', title), id=index,
                 scraped_at='2026-10-06 10:00:00') for index, title in enumerate(titles, 1)]


class EventAccuracyTest(unittest.TestCase):
    CONFLICTS = [
        ('交易价格为50.5美元', '交易价格为505美元'),
        ('交易价格为50.5美元', '交易价格为50.5元'),
        ('交易价格为$50.5', '交易价格为$505'),
        ('昨日比特币ETF净流入5亿美元', '昨日比特币ETF净流出5亿美元'),
        ('比特币突破10万美元', '比特币跌破10万美元'),
        ('项目A完成1000万美元融资', '项目B完成1000万美元融资'),
        ('项目完成1.2亿美元融资', '项目完成1.3亿美元融资'),
        ('币安拟收购FTX', '币安已收购FTX'),
        ('币安收购FTX', '币安收购Bitfinex'),
        ('甲公司完成1000万美元融资', '乙公司完成1000万美元融资'),
        ('比特币上涨5%', '比特币上涨50%'),
        ('项目收入为-50.5美元', '项目收入为50.5美元'),
        ('OpenAI发布GPT-9模型', 'OpenAI发布GPT-10模型'),
        ('币安批准项目A上线', '币安批准项目B上线'),
        ('SEC批准比特币ETF', 'SEC未批准比特币ETF'),
        ('项目A上线主网', '项目A未上线主网'),
        ('Alpha raises 1000000 usd', 'Beta raises 1000000 usd'),
    ]
    DUPLICATES = [
        ('BTC突破10万美元', '比特币突破100000美元'),
        ('BTC突破$100,000', '比特币突破10万美元'),
        ('ETHereum推出新功能', 'ETH推出新功能'),
        ('Solana主网上线', 'SOL主网上线'),
        ('币安购买100枚BTC', 'Binance买入100枚比特币'),
        ('美国 SEC 批准现货比特币 ETF', 'SEC 正式批准比特币现货 ETF'),
        ('项目A完成1000万美元融资', '项目A完成融资10000000美元'),
        ('OpenAI发布GPT-9', 'OpenAI正式发布GPT-9'),
        ('币安拟收购FTX', '币安计划收购FTX'),
        ('William launches a new product', 'William announces a new product'),
    ]

    def test_conflicting_reports_stay_separate_in_all_matching_paths(self):
        for threshold in (0, 0.5, 1):
            clusterer = EventClusterer(threshold)
            for left, right in self.CONFLICTS:
                with self.subTest(threshold=threshold, left=left, right=right):
                    rows = items(left, right)
                    self.assertFalse(clusterer.is_same_event(left, right))
                    self.assertEqual(len(clusterer.cluster(rows)), 2)
                    existing, _ = clusterer.best_existing_event(rows[1], [dict(rows[0], id=99)])
                    self.assertIsNone(existing)

    def test_equivalent_reports_still_merge(self):
        clusterer = EventClusterer()
        for left, right in self.DUPLICATES:
            with self.subTest(left=left, right=right):
                rows = items(left, right)
                self.assertTrue(clusterer.is_same_event(left, right))
                self.assertEqual(len(clusterer.cluster(rows)), 1)
                existing, _ = clusterer.best_existing_event(rows[1], [dict(rows[0], id=99)])
                self.assertEqual(existing['id'], 99)

    def test_fact_guards_are_independent_of_optional_tokenizer(self):
        tokenizer = SimpleNamespace(cut_for_search=lambda text: ['相同词', '相同词2'])
        with patch('backend.app.infrastructure.event_clustering.jieba', tokenizer):
            self.test_conflicting_reports_stay_separate_in_all_matching_paths()

    def test_normalization_preserves_values_and_word_boundaries(self):
        clusterer = EventClusterer()
        expected = {'10万': '100000', '1.2亿': '120000000', '1.234万': '12340',
                    '1万亿': '1000000000000', '50.50美元': '50.5美元',
                    '１．２亿美元': '120000000美元', '1,000,000美元': '1000000美元',
                    'PostgreSQL新版本': 'postgresql新版本', 'solution': 'solution',
                    'metadata': 'metadata', 'ETHereum': '以太坊', 'Solana': '索拉纳',
                    '币安拟收购': '币安拟收购', '币安已收购': '币安已收购',
                    '123456789012345678901234567890.5万': '1234567890123456789012345678905000'}
        for title, normalized in expected.items():
            with self.subTest(title=title):
                self.assertEqual(clusterer.normalize(title), normalized)

    def test_no_empty_title_shortcut(self):
        clusterer = EventClusterer(0)
        rows = items('!!!', '???')
        self.assertFalse(clusterer.is_same_event('!!!', '???'))
        self.assertEqual(len(clusterer.cluster(rows)), 2)
        self.assertIsNone(clusterer.best_existing_event(rows[1], [rows[0]])[0])

    def test_non_primary_facts_prevent_transitive_merges(self):
        clusterer = EventClusterer()
        rows = items('项目A宣布完成新一轮融资，用于扩大业务',
                     '项目A宣布完成1000万美元新一轮融资，用于扩大业务',
                     '项目A宣布完成2000万美元新一轮融资，用于扩大业务')
        rows[0]['is_marked_important'] = True
        self.assertEqual(len(clusterer.cluster(rows)), 2)
        existing = dict(rows[0], id=99, source_titles=[row['title'] for row in rows[:2]])
        self.assertIsNone(clusterer.best_existing_event(rows[2], [existing])[0])

    def test_inconsistent_historical_event_does_not_gain_new_sources(self):
        clusterer = EventClusterer()
        row = items('项目A完成1000万美元融资')[0]
        old = dict(row, id=99, source_titles=[row['title'], '项目A完成2000万美元融资'])
        self.assertIsNone(clusterer.best_existing_event(row, [old])[0])

    def test_real_archiving_respects_facts_added_later_in_same_batch(self):
        with sqlite3.connect(':memory:') as conn:
            conn.row_factory = sqlite3.Row
            migration.create_current_schema(conn.cursor())
            conn.commit()
            repos = SimpleNamespace(news=NewsRepository(conn), events=EventRepository(conn),
                                    event_queries=EventQueryRepository(conn), archive=ArchiveRepository(conn))

            @contextmanager
            def transaction():
                conn.execute('BEGIN')
                try:
                    yield repos
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise

            titles = ['项目A宣布完成新一轮融资，用于扩大业务',
                      '项目A宣布完成1000万美元新一轮融资，用于扩大业务',
                      '项目A宣布完成2000万美元新一轮融资，用于扩大业务']
            for index, title in enumerate(titles):
                repos.news.insert_news(news(f'https://source.test/{index}', title))
            rows = [dict(row) for row in conn.execute('SELECT * FROM news ORDER BY id')]
            clusterer = EventClusterer()
            service = ContentTransitionService(transaction)
            service.persist_event_clusters(clusterer.cluster(rows[:1]), clusterer, 'news', 24)
            outcome = service.persist_event_clusters(clusterer.cluster(rows[1:]), clusterer, 'news', 24)
            self.assertEqual(outcome['attached_events'], 1)
            self.assertEqual(outcome['created_events'], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM content_events').fetchone()[0], 2)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM archive_entries').fetchone()[0], 2)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM event_sources').fetchone()[0], 3)


class URLIdentityTest(unittest.TestCase):
    OLD = 'https://www.techflowpost.com/zh-CN/article/1'
    NEW = 'https://www.techflowpost.com/article/1'

    def test_meaningful_url_components_remain_distinct(self):
        bases = ('https://media.test/read', 'https://www.techflowpost.com/read')
        for base in bases:
            for first, second in [('?id=1', '?id=2'), ('?lang=en', '?lang=zh'), ('#a', '#b')]:
                with self.subTest(base=base, first=first):
                    self.assertNotEqual(media_identity(base + first), media_identity(base + second))
        self.assertNotEqual(media_identity('https://www.techflowpost.com:8443/read'), media_identity('https://www.techflowpost.com/read'))
        self.assertNotEqual(media_identity('http://www.techflowpost.com:8443/read'), media_identity('https://www.techflowpost.com:8443/read'))
        self.assertNotEqual(media_identity('https://eviltechflowpost.com/zh-CN/article/1'), media_identity(self.NEW))
        self.assertEqual(source_identity('https://news.ycombinator.com/item?id=1'), 'https://news.ycombinator.com/item?id=1')
        self.assertEqual(source_identity('https://waytoagi.test/doc#entry-1'), 'https://waytoagi.test/doc#entry-1')

    def test_verified_aliases_and_tracking_parameters_share_identity(self):
        self.assertEqual(source_identity(self.OLD), source_identity(self.NEW))
        self.assertEqual(source_identity(self.OLD + '?utm_source=rss'), source_identity(self.NEW))
        self.assertEqual(source_identity('https://m.theblockbeats.info/flash/1'), source_identity('https://www.theblockbeats.info/flash/1'))
        self.assertEqual(source_identity(self.OLD + '?id=2&utm_source=rss'), source_identity(self.NEW + '?id=2'))

    def test_database_rejects_alias_even_outside_history_cache(self):
        with sqlite3.connect(':memory:') as conn:
            create_news_table(conn.cursor())
            repo = NewsRepository(conn)
            self.assertIsNotNone(repo.insert_news(news(self.OLD)))
            self.assertEqual(repo.insert_news_batch([news(f'https://www.techflowpost.com/article/{i}') for i in range(2, 2103)]), 2101)
            self.assertIsNone(repo.insert_news(news(self.NEW)))
            self.assertEqual(repo.insert_news_batch([news(self.NEW), news(self.NEW + '?utm_source=rss')]), 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM news').fetchone()[0], 2102)
            self.assertEqual(conn.execute('SELECT source_url FROM news WHERE id=1').fetchone()[0], self.OLD)

    def test_query_ids_can_both_be_saved(self):
        with sqlite3.connect(':memory:') as conn:
            create_news_table(conn.cursor())
            repo = NewsRepository(conn)
            self.assertEqual(repo.insert_news_batch([news('https://www.techflowpost.com/read?id=1'), news('https://www.techflowpost.com/read?id=2')]), 2)

    def test_transaction_rolls_back_news_and_identity_together(self):
        with sqlite3.connect(':memory:') as conn:
            create_news_table(conn.cursor())
            conn.commit()
            conn.execute('BEGIN')
            NewsRepository(conn).insert_news(news(self.OLD))
            conn.rollback()
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM news_source_identities').fetchone()[0], 0)
            self.assertIsNotNone(NewsRepository(conn).insert_news(news(self.NEW)))

    def test_updating_url_keeps_identity_claim_consistent(self):
        with sqlite3.connect(':memory:') as conn:
            create_news_table(conn.cursor())
            repo = NewsRepository(conn)
            identifier = repo.insert_news(news(self.OLD))
            repo.update_news(identifier, {'source_url': 'https://www.techflowpost.com/article/2'})
            self.assertIsNone(repo.insert_news(news('https://www.techflowpost.com/zh-CN/article/2')))
            self.assertIsNotNone(repo.insert_news(news(self.NEW)))

    def test_migration_canonicalizes_raw_sql_rows_and_keeps_all_ids(self):
        with sqlite3.connect(':memory:') as conn:
            create_news_table(conn.cursor())
            for identifier, url in enumerate((self.OLD, self.NEW), 1):
                conn.execute('INSERT INTO news(id,title,source_site,source_url,published_at) VALUES (?,?,?,?,?)',
                             (identifier, '标题', 'Techflow Article', url, '2026-10-06 10:00:00'))
            create_news_identity_schema(conn.cursor())
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM news').fetchone()[0], 2)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM news_source_identities').fetchone()[0], 1)
            self.assertIsNone(NewsRepository(conn).insert_news(news(self.NEW + '?utm_source=rss')))

    def test_identity_cannot_be_cleared_to_bypass_dedup(self):
        with sqlite3.connect(':memory:') as conn:
            create_news_table(conn.cursor())
            identifier = NewsRepository(conn).insert_news(news(self.OLD))
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'news_source_identity_required'):
                conn.execute('UPDATE news SET source_identity=NULL WHERE id=?', (identifier,))


class DedupMigrationTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(os.environ.get('GLEAN_TEST_EVIDENCE_ROOT', r'D:\Tools\CodexAudits\Glean\dedup-tests')) / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.path = self.root / 'old.db'
        with sqlite3.connect(self.path) as conn:
            conn.execute('''CREATE TABLE news(id INTEGER PRIMARY KEY, title TEXT, content TEXT,
                source_site TEXT, source_url TEXT UNIQUE, published_at TEXT, scraped_at TEXT,
                is_marked_important INTEGER, site_importance_flag TEXT, stage TEXT, type TEXT, author TEXT)''')
            for identifier, url in enumerate((URLIdentityTest.OLD, URLIdentityTest.NEW), 1):
                conn.execute('INSERT INTO news(id,title,source_url) VALUES (?,?,?)', (identifier, '原始文章', url))
            conn.execute('CREATE TABLE preserved_links(news_id INTEGER REFERENCES news(id))')
            conn.executemany('INSERT INTO preserved_links VALUES (?)', [(1,), (2,)])
            conn.execute('CREATE TABLE schema_migrations(version TEXT PRIMARY KEY)')
            conn.execute('INSERT INTO schema_migrations VALUES (?)', (migration.DELIVERY_RETENTION_VERSION,))
        self.db = Database(str(self.path))

    def test_upgrade_preserves_historical_aliases_and_promotes_survivor(self):
        self.db.init_db()
        self.db.init_db()
        self.db.assert_schema_current()
        with self.db.connect() as conn:
            self.assertEqual([row['id'] for row in conn.execute('SELECT id FROM news ORDER BY id')], [1, 2])
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM preserved_links').fetchone()[0], 2)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM news_source_identities').fetchone()[0], 1)
            self.assertIsNone(NewsRepository(conn).insert_news(news(URLIdentityTest.NEW + '?utm_source=rss')))
            # Only the disposable fixture changes; the migration never removes rows.
            conn.execute('DELETE FROM preserved_links WHERE news_id=1')
            conn.execute('DELETE FROM news WHERE id=1')
            self.assertEqual(conn.execute('SELECT news_id FROM news_source_identities').fetchone()[0], 2)
            self.assertIsNone(NewsRepository(conn).insert_news(news(URLIdentityTest.OLD)))
        self.assertEqual(len(list((self.root / 'backups').iterdir())), 1)

    def test_failed_upgrade_is_atomic_and_retryable(self):
        step = migration.resolve_migration_plan(migration.DELIVERY_RETENTION_VERSION)[0]
        def fail(cursor):
            step.apply(cursor)
            raise RuntimeError('controlled interruption')
        with patch('backend.app.infrastructure.sqlite.db_sqlite.resolve_migration_plan',
                   return_value=(migration.MigrationStep(step.name, step.from_version, step.to_version, fail),)):
            with self.assertRaisesRegex(RuntimeError, 'controlled interruption'):
                self.db.init_db()
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT version FROM schema_migrations').fetchone()[0], migration.DELIVERY_RETENTION_VERSION)
            self.assertNotIn('source_identity', {row[1] for row in conn.execute('PRAGMA table_info(news)')})
        self.db.init_db()
        self.db.assert_schema_current()

    def test_parallel_writers_cannot_insert_two_aliases(self):
        self.path = self.root / 'fresh.db'
        db = Database(str(self.path))
        db.init_db()
        barrier = Barrier(2)
        def insert(url):
            barrier.wait(timeout=10)
            return NewsRepository(db).insert_news(news(url))
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(insert, [URLIdentityTest.OLD, URLIdentityTest.NEW]))
        self.assertEqual(sum(identifier is not None for identifier in results), 1)
        with db.connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM news').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM news_source_identities').fetchone()[0], 1)


class IncrementalDedupTest(unittest.IsolatedAsyncioTestCase):
    async def test_browser_collector_skips_old_entries_and_reads_later_new_item(self):
        scraper = ForesightExclusiveScraper()
        scraper.incremental_mode = True
        scraper.existing_urls = {'old1', 'old2', 'old3'}
        scraper.last_news_url = 'old1'
        scraper.last_news_title = '重复标题'
        collector = ScrapeCandidateCollector(scraper)
        self.assertEqual([collector.consider('重复标题', url) for url in ('old1', 'old2', 'old3', 'new4')],
                         [CANDIDATE_SKIP, CANDIDATE_SKIP, CANDIDATE_SKIP, CANDIDATE_ACCEPT])

    async def test_foresight_column_skips_known_urls_without_stopping_list(self):
        scraper = ForesightExclusiveScraper()
        scraper.incremental_mode = True
        urls = [f'https://foresightnews.pro/article/detail/{i}' for i in range(4)]
        scraper.existing_urls = set(urls[:3])
        scraper.last_news_url = urls[0]
        elements = []
        for index, url in enumerate(urls):
            nodes = {'.article-body-title': SimpleNamespace(inner_text=AsyncMock(return_value=f'完整标题{index}')),
                     'a[href^="/article/detail/"]': SimpleNamespace(get_attribute=AsyncMock(return_value=url)),
                     '.article-body-content': SimpleNamespace(inner_text=AsyncMock(return_value='文章的真实正文摘要足够长')),
                     '.article-time': SimpleNamespace(inner_text=AsyncMock(return_value='2026-10-06 10:00'))}
            elements.append(SimpleNamespace(query_selector=AsyncMock(side_effect=nodes.get)))
        scraper.page = SimpleNamespace(query_selector_all=AsyncMock(return_value=elements))
        result = await scraper._scrape_list_articles()
        self.assertEqual([item['url'] for item in result], urls[3:])

    async def test_media_snapshot_preserves_distinct_query_ids(self):
        scraper = TechflowArticleScraper()
        rows = [news(f'https://www.techflowpost.com/read?id={i}') for i in (1, 2)]
        self.assertEqual(len(MediaSnapshot.select_new_items(scraper, rows)), 2)
        scraper.incremental_mode = True
        scraper.existing_urls = {rows[0]['url']}
        self.assertEqual([item['url'] for item in MediaSnapshot.select_new_items(scraper, rows)], [rows[1]['url']])
