from __future__ import annotations

import ast
from pathlib import Path
import unittest

from shared.content_contract import (
    DELIVERY_MAX_ATTEMPTS,
    DELIVERY_OPERATION_STATUS_FAILED,
    DELIVERY_PART_STATUS_FAILED,
    EXPORT_SCOPE_ARCHIVE,
    EXPORT_SCOPE_BLOCKED,
    EXPORT_SCOPE_DISCARDED,
    EXPORT_SCOPE_INCOMING,
    EXPORT_SCOPE_REVIEW,
    EXPORT_SCOPE_SELECTED,
    TELEGRAM_MESSAGE_LIMIT,
)

from backend.app.infrastructure.repository_impl.content_scope import CONTENT_SCOPE_PLANS
from backend.app.infrastructure.scraper_impl.article_base import ArticleScraper
from backend.app.infrastructure.scraper_impl.base import BaseScraper
from backend.app.infrastructure.scraper_impl.content_tools import parse_relative_time
from backend.app.domain.delivery import derive_delivery_operation_status
from backend.app.domain.events import select_event_primary


ROOT = Path(__file__).resolve().parents[2]
SERVICES = ROOT / "backend" / "app" / "services"
ROUTERS = ROOT / "backend" / "app" / "routers"
SCRAPERS = ROOT / "backend" / "app" / "infrastructure" / "scraper_impl"


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


class ArchitectureBoundaryTest(unittest.TestCase):
    def test_services_receive_dependencies_instead_of_locating_infrastructure(self):
        violations = []
        for path in SERVICES.glob("*.py"):
            tree = parse(path)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if "infrastructure" in module:
                        violations.append(f"{path.name}:{node.lineno}:{module}")
                elif isinstance(node, ast.Import):
                    for imported in node.names:
                        if "infrastructure" in imported.name:
                            violations.append(f"{path.name}:{node.lineno}:{imported.name}")
            for node in tree.body:
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and any(
                    isinstance(target, ast.Name) and target.id.endswith("_service")
                    for target in node.targets
                ):
                    violations.append(f"{path.name}:{node.lineno}:module singleton")
        self.assertEqual(violations, [])

    def test_routers_use_application_services_only(self):
        violations = []
        for path in ROUTERS.glob("*.py"):
            for node in ast.walk(parse(path)):
                if isinstance(node, ast.ImportFrom) and "infrastructure" in (node.module or ""):
                    violations.append(f"{path.name}:{node.lineno}:{node.module}")
        self.assertEqual(violations, [])

    def test_retired_duplicate_apis_do_not_return(self):
        production = "\n".join(
            path.read_text(encoding="utf-8")
            for base in (ROOT / "backend" / "app", ROOT / "frontend" / "src", ROOT / "shared")
            for path in base.rglob("*")
            if path.suffix in {".py", ".js", ".jsx"}
        )
        for symbol in (
            "restore_blocked_entries",
            "get_incoming_news_for_export",
            "export_selected_entries",
            "export_review_results",
            "export const usePagination",
            "def _positive_int",
        ):
            self.assertNotIn(symbol, production)
        self.assertNotIn("repository_impl.time_utils", production)

    def test_pipeline_router_has_one_domain(self):
        source = (ROUTERS / "pipeline.py").read_text(encoding="utf-8")
        self.assertNotIn('"/spiders', source)
        self.assertNotIn('"/delivery', source)
        self.assertNotIn('"/integration', source)
        self.assertIn('"/content/', source)

        admin_content = (ROUTERS / "news.py").read_text(encoding="utf-8")
        self.assertNotIn('"/public/', admin_content)
        self.assertNotIn('"/analyst/', admin_content)

    def test_registered_http_routes_have_one_owner(self):
        from backend.main import app

        seen = set()
        duplicates = []
        for route in app.routes:
            for method in getattr(route, "methods", set()):
                key = (method, route.path)
                if key in seen:
                    duplicates.append(key)
                seen.add(key)
        self.assertEqual(duplicates, [])

    def test_standard_article_adapters_use_the_shared_lifecycle(self):
        standard = {
            "blockbeats_article.py",
            "chaincatcher_article.py",
            "foresight_article.py",
            "marsbit_article.py",
            "odaily_article.py",
            "panews_article.py",
            "techflow_article.py",
            "wublock_article.py",
        }
        overrides = []
        for name in standard:
            for node in parse(SCRAPERS / name).body:
                if isinstance(node, ast.ClassDef) and any(
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and item.name == "scrape_important_news"
                    for item in node.body
                ):
                    overrides.append(name)
        self.assertEqual(overrides, [])

    def test_flash_adapters_use_the_shared_candidate_policy(self):
        names = {
            "blockbeats.py",
            "chaincatcher.py",
            "foresight.py",
            "marsbit.py",
            "odaily.py",
            "panews.py",
            "techflow.py",
        }
        for name in names:
            source = (SCRAPERS / name).read_text(encoding="utf-8")
            self.assertIn("create_candidate_collector", source, name)
            self.assertIn("collector.consider", source, name)
            self.assertIn("collector.append_standard", source, name)
            self.assertNotIn("collector.append(", source, name)
            self.assertNotIn("processed_urls", source, name)

    def test_scraper_detail_pages_and_relative_time_have_one_owner(self):
        adapter_sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in SCRAPERS.glob("*_article.py")
        )
        self.assertNotIn("browser.new_page(", adapter_sources)
        self.assertNotIn("await page.close(", adapter_sources)
        self.assertNotIn("await detail_page.close(", adapter_sources)
        self.assertNotIn("def _parse_relative_time", adapter_sources)
        self.assertIn(
            "async with scraper.detail_page(detail_url)",
            (SCRAPERS / "content_tools.py").read_text(encoding="utf-8"),
        )

    def test_delivery_and_event_repositories_keep_separate_write_read_execution_roles(self):
        delivery_operations = (SCRAPERS.parent / "repository_impl" / "delivery_repository.py").read_text(
            encoding="utf-8"
        )
        delivery_execution = (
            SCRAPERS.parent / "repository_impl" / "delivery_execution_repository.py"
        ).read_text(encoding="utf-8")
        event_path = SCRAPERS.parent / "repository_impl" / "event_repository.py"
        self.assertNotIn("def claim_next_part", delivery_operations)
        self.assertNotIn("def create_operation", delivery_execution)
        event_methods = {
            item.name
            for node in parse(event_path).body
            if isinstance(node, ast.ClassDef)
            for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertTrue(
            {"list_groups", "get_event", "list_recent_candidates"}.isdisjoint(event_methods)
        )

    def test_operational_contracts_and_export_scopes_have_one_owner(self):
        self.assertEqual(DELIVERY_MAX_ATTEMPTS, 3)
        self.assertEqual(TELEGRAM_MESSAGE_LIMIT, 4096)
        self.assertEqual(
            set(CONTENT_SCOPE_PLANS),
            {
                EXPORT_SCOPE_INCOMING,
                EXPORT_SCOPE_ARCHIVE,
                EXPORT_SCOPE_BLOCKED,
                EXPORT_SCOPE_REVIEW,
                EXPORT_SCOPE_SELECTED,
                EXPORT_SCOPE_DISCARDED,
            },
        )

    def test_domain_policies_are_shared_and_deterministic(self):
        primary = select_event_primary(
            [
                {"id": 1, "is_marked_important": False, "content": "x" * 500},
                {"id": 2, "is_marked_important": True, "content": "short"},
            ]
        )
        self.assertEqual(primary["id"], 2)
        self.assertEqual(
            derive_delivery_operation_status(
                [
                    {
                        "status": DELIVERY_PART_STATUS_FAILED,
                        "attempt_count": DELIVERY_MAX_ATTEMPTS,
                    }
                ]
            ),
            (DELIVERY_OPERATION_STATUS_FAILED, 0),
        )
        self.assertEqual(parse_relative_time("2026-08-23 12:34").strftime("%Y-%m-%d %H:%M"), "2026-08-23 12:34")
        self.assertIsNotNone(parse_relative_time("2天前"))

    def test_frontend_does_not_restore_global_timers_or_operational_url_defaults(self):
        frontend = ROOT / "frontend" / "src"
        production = "\n".join(
            path.read_text(encoding="utf-8")
            for path in frontend.rglob("*")
            if path.suffix in {".js", ".jsx"} and ".test." not in path.name
        )
        self.assertNotIn("window.searchTimeout", production)
        self.assertNotIn("https://t.me/", production)
        self.assertNotIn("20:00", production)
        self.assertNotIn("21:00", production)
        self.assertIn(
            "reviewResultColumns",
            (frontend / "components" / "dashboard" / "SelectedContentTab.jsx").read_text(
                encoding="utf-8"
            ),
        )
        self.assertIn(
            "reviewResultColumns",
            (frontend / "components" / "dashboard" / "DiscardedContentTab.jsx").read_text(
                encoding="utf-8"
            ),
        )

    def test_scraper_adapters_do_not_embed_manual_test_programs(self):
        offenders = [
            path.name
            for path in SCRAPERS.glob("*.py")
            if "__main__" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(offenders, [])


class _FakePage:
    def __init__(self):
        self.waits = []

    async def wait_for_selector(self, selector, timeout):
        self.waits.append((selector, timeout))


class _ArticleContractScraper(ArticleScraper):
    def __init__(self):
        super().__init__("Contract Article", "https://example.test", max_items=2)
        self.list_url = "https://example.test/articles"
        self.list_wait_selector = ".article"
        self.list_load_delay = 0
        self.page = _FakePage()
        self.fetched = []

    async def fetch_page_with_delay(self, url, **kwargs):
        self.fetched.append(url)

    async def _scrape_list_articles(self):
        return [{"id": 1}, {"id": 2}, {"id": 3}]


class _CollectorContractScraper(BaseScraper):
    def __init__(self):
        super().__init__("Contract Flash", "https://example.test", max_items=1)
        self.stop_urls = set()

    async def scrape_important_news(self):
        return []

    def should_stop_scraping(self, title, url, news_time=None):
        return url in self.stop_urls


class ScraperLifecycleContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_article_lifecycle_fetches_waits_and_limits_once(self):
        scraper = _ArticleContractScraper()
        result = await scraper.scrape_important_news()
        self.assertEqual(scraper.fetched, [scraper.list_url])
        self.assertEqual(scraper.page.waits, [(".article", 10000)])
        self.assertEqual(result, [{"id": 1}, {"id": 2}])

    async def test_candidate_collector_owns_dedup_stop_limit_and_callback(self):
        scraper = _CollectorContractScraper()
        callback_items = []
        scraper.item_callback = callback_items.append
        collector = scraper.create_candidate_collector()

        self.assertEqual(collector.consider("first", "https://example.test/1"), "accept")
        collector.append({"title": "first"})
        self.assertEqual(
            callback_items,
            [{
                "title": "first",
                "content": "",
                "source_site": "Contract Flash",
                "author": "Contract Flash",
                "type": "news",
            }],
        )
        self.assertEqual(collector.consider("duplicate", "https://example.test/1"), "skip")
        self.assertEqual(collector.consider("limited", "https://example.test/2"), "stop")

        another = scraper.create_candidate_collector()
        scraper.stop_urls.add("https://example.test/stop")
        self.assertEqual(another.consider("stop", "https://example.test/stop"), "stop")
