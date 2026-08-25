"""爬虫基类。"""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Browser, Page

from .source_transport import BrowserSourceTransport, HttpSourceTransport, create_source_transport
from .content_tools import (
    check_importance_by_style,
    clean_content,
    fetch_full_content,
    parse_relative_time,
    safe_extract_text,
    safe_get_attribute,
)
from .incremental_state import load_last_news, should_stop_scraping


logger = logging.getLogger(__name__)


CANDIDATE_ACCEPT = "accept"
CANDIDATE_SKIP = "skip"
CANDIDATE_STOP = "stop"


class ScraperResultBuffer(list):
    def __init__(self, scraper):
        super().__init__()
        self.scraper = scraper

    def append(self, item):
        normalized = self.scraper.normalize_result_item(item)
        super().append(normalized)
        callback = getattr(self.scraper, "item_callback", None)
        if callback:
            try:
                callback(normalized)
            except Exception as exc:
                self.scraper.persistence_errors.append(str(exc))

    def extend(self, items):
        for item in items:
            self.append(item)


class ScrapeCandidateCollector:
    """Shared de-duplication, incremental-stop and limit policy for list scrapers."""

    def __init__(self, scraper):
        self.scraper = scraper
        self.results = scraper.create_result_buffer()
        self.seen_urls: set[str] = set()

    def consider(self, title: str, url: str, published_at: datetime | None = None) -> str:
        if not url or url in self.seen_urls:
            return CANDIDATE_SKIP
        self.seen_urls.add(url)
        if self.scraper.should_stop_scraping(title, url, published_at):
            return CANDIDATE_STOP
        if len(self.results) >= self.scraper.max_items:
            print(f"[数量限制] 已达到最大抓取数量 {self.scraper.max_items}，停止抓取")
            return CANDIDATE_STOP
        return CANDIDATE_ACCEPT

    def append(self, item: Dict) -> None:
        self.results.append(item)

    def append_standard(
        self,
        *,
        title: str,
        url: str,
        published_at,
        content: str = "",
        fallback_content: str | None = None,
        min_content_length: int = 10,
        is_marked_important: bool = True,
        site_importance_flag: str | None = None,
        author: str | None = None,
        **extra,
    ) -> None:
        normalized_content = self.scraper.clean_content(content, title)
        if not normalized_content or len(normalized_content) < min_content_length:
            normalized_content = fallback_content or title
        self.append(
            {
                "title": title,
                "content": normalized_content,
                "url": url,
                "published_at": published_at,
                "is_marked_important": is_marked_important,
                "site_importance_flag": site_importance_flag,
                "author": author or self.scraper.site_name,
                **extra,
            }
        )


class BaseScraper(ABC):
    """所有爬虫的基类。"""

    transport_kind = "browser"

    def __init__(self, site_name: str, base_url: str, max_items: int = 10):
        self.site_name = site_name
        self.base_url = base_url
        self.news_type = "news"
        self.browser: Optional["Browser"] = None
        self.page: Optional["Page"] = None
        self.playwright = None
        self.last_news_title = None
        self.last_news_url = None
        self.existing_urls = set()
        self.last_news_time = None
        self.incremental_mode = True
        self.max_items = max_items
        self.transport = create_source_transport(self.transport_kind)
        self.item_callback = None
        self.persistence_errors: list[str] = []
        self.used_result_buffer = False

    def create_result_buffer(self) -> ScraperResultBuffer:
        self.used_result_buffer = True
        return ScraperResultBuffer(self)

    def create_candidate_collector(self) -> ScrapeCandidateCollector:
        return ScrapeCandidateCollector(self)

    def normalize_result_item(self, item: Dict) -> Dict:
        normalized = dict(item)
        normalized.setdefault("content", "")
        normalized.setdefault("source_site", self.site_name)
        normalized.setdefault("author", self.site_name)
        normalized.setdefault("type", self.news_type)
        return normalized

    async def init_browser(self, headless: bool = True):
        if not isinstance(self.transport, BrowserSourceTransport):
            raise RuntimeError(f"{self.site_name} does not use a browser transport")
        await self.transport.start(self)

    async def close_browser(self):
        await self.transport.close(self)

    async def fetch_page_with_delay(
        self,
        url: str,
        delay_range: tuple = (1, 3),
        max_retries: int = 3,
        return_response: bool = False,
        page: Optional[Page] = None,
    ):
        if not isinstance(self.transport, BrowserSourceTransport):
            raise RuntimeError(f"{self.site_name} does not expose a browser page")
        return await self.transport.fetch_page(
            self,
            url,
            delay_range=delay_range,
            max_retries=max_retries,
            return_response=return_response,
            page=page,
        )

    async def fetch_text(self, url: str, delay_range: tuple = (0.3, 1.0), max_retries: int = 3) -> str:
        if not isinstance(self.transport, HttpSourceTransport):
            raise RuntimeError(f"{self.site_name} does not use an HTTP transport")
        return await self.transport.fetch_text(url, delay_range=delay_range, max_retries=max_retries)

    @abstractmethod
    async def scrape_important_news(self) -> List[Dict]:
        pass

    async def click_important_filter(self, selector: str):
        try:
            await self.page.click(selector)
            await self.page.wait_for_timeout(2000)
        except Exception as exc:
            print(f"点击筛选器失败: {exc}")

    def generate_url_hash(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()

    async def safe_extract_text(self, element, selector: str = None) -> str:
        return await safe_extract_text(element, selector)

    async def safe_get_attribute(self, element, attr: str) -> str:
        return await safe_get_attribute(element, attr)

    def clean_content(self, content: str, title: str = "") -> str:
        return clean_content(content, title)

    def parse_relative_time(self, time_str: str) -> Optional[datetime]:
        return parse_relative_time(time_str)

    async def check_importance_by_style(self, element) -> Dict:
        return await check_importance_by_style(element)

    async def fetch_full_content(self, detail_url: str, content_selectors: List[str] = None, extract_paragraphs: bool = False) -> str:
        return await fetch_full_content(self, detail_url, content_selectors, extract_paragraphs)

    @asynccontextmanager
    async def detail_page(self, url: str, load_delay_seconds: float = 0):
        if not self.browser:
            raise RuntimeError(f"{self.site_name} browser is not initialized")
        page = await self.browser.new_page()
        try:
            await self.fetch_page_with_delay(url, page=page)
            if load_delay_seconds > 0:
                await page.wait_for_timeout(int(load_delay_seconds * 1000))
            yield page
        finally:
            try:
                await page.close()
            except Exception:
                logger.exception("%s 详情页资源清理失败: %s", self.site_name, url)

    def load_last_news(self, db):
        load_last_news(self, db)

    def should_stop_scraping(self, news_title: str, news_url: str, news_time: datetime = None) -> bool:
        return should_stop_scraping(self, news_title, news_url, news_time)

    async def run(self) -> List[Dict]:
        try:
            await self.transport.start(self)
            results = await self.scrape_important_news()
            if self.persistence_errors:
                raise RuntimeError("采集结果写入失败：" + "；".join(self.persistence_errors[:3]))
            if not results and self.transport_kind != "rss":
                raise RuntimeError("页面请求成功但没有解析出任何内容，请检查站点结构或反爬页面")
            return results
        except Exception as exc:
            logger.exception("%s 爬虫执行失败", self.site_name)
            raise RuntimeError(f"{self.site_name} 爬虫执行失败: {exc}") from exc
        finally:
            try:
                await self.transport.close(self)
            except Exception:
                logger.exception("%s 爬虫资源清理失败", self.site_name)
