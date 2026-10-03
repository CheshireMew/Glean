from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .base import BaseScraper


class LobstersScraper(BaseScraper):
    """Read the requested recent list without fetching linked articles."""

    transport_kind = "http"
    allow_empty_results = True

    def __init__(self):
        super().__init__("Lobsters", "https://lobste.rs/recent", max_items=20)
        self.news_type = "article"

    async def scrape_important_news(self) -> list[dict]:
        html = await self.fetch_text(self.base_url)
        stories = BeautifulSoup(html, "html.parser").select("li.story")
        articles = self.create_result_buffer()
        seen_urls = set()
        valid_count = 0
        for story in stories:
            link = story.select_one(".link a.u-url[href]")
            timestamp = story.select_one("time[data-at-unix]")
            if link is None or timestamp is None:
                continue
            title = link.get_text(" ", strip=True)
            url = urljoin(self.base_url, link["href"])
            if not title or urlparse(url).scheme not in {"http", "https"}:
                continue
            try:
                published_at = datetime.fromtimestamp(int(timestamp["data-at-unix"]), timezone.utc)
            except (ValueError, OverflowError, OSError):
                continue
            valid_count += 1
            if url in seen_urls:
                continue
            seen_urls.add(url)
            if self.incremental_mode and (url in self.existing_urls or url == self.last_news_url):
                continue
            author = story.select_one(".u-author")
            # This list contains links and submission metadata, not article summaries.
            articles.append({"title": title, "content": "", "url": url,
                             "published_at": published_at.isoformat(),
                             "author": author.get_text(" ", strip=True) if author else self.site_name})
            if len(articles) >= self.max_items:
                break
        if not valid_count:
            raise RuntimeError("Lobsters recent 页面未解析出有效条目，请检查来源页面结构")
        return articles
