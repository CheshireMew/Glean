
import asyncio
import traceback
from typing import Dict, List

from .base import BaseScraper

class ArticleScraper(BaseScraper):
    """
    文章类爬虫基类
    用于抓取深度文章（非快讯），默认 type='article'
    """
    
    def __init__(self, site_name: str, base_url: str, max_items: int = 10):
        super().__init__(site_name, base_url, max_items)
        self.news_type = "article"
        self.list_url = base_url
        self.list_wait_selector: str | None = None
        self.list_wait_timeout = 10000
        self.list_load_delay = 3

    async def scrape_important_news(self) -> List[Dict]:
        """Run the shared list-page lifecycle; subclasses only parse site markup."""
        try:
            print(f"\n正在访问: {self.list_url}")
            await self.fetch_page_with_delay(self.list_url)
            await asyncio.sleep(self.list_load_delay)
            await self._prepare_list_page()
            if self.list_wait_selector:
                try:
                    await self.page.wait_for_selector(
                        self.list_wait_selector, timeout=self.list_wait_timeout
                    )
                except Exception:
                    print("⚠️ 等待列表元素超时")
                    raise
            articles = await self._scrape_list_articles()
            print(f"📋 抓取到: {len(articles)} 篇文章")
            return articles[: self.max_items]
        except Exception as exc:
            print(f"❌ 抓取失败: {exc}")
            traceback.print_exc()
            raise

    async def _scrape_list_articles(self) -> List[Dict]:
        raise NotImplementedError

    async def _prepare_list_page(self) -> None:
        """Optional source-specific list preparation after the shared page load."""
