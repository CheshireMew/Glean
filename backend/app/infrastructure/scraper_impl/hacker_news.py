from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .base import BaseScraper


class HackerNewsScraper(BaseScraper):
    """Read the actual home page, preserving its current selection and order."""

    transport_kind = "http"
    allow_empty_results = True

    def __init__(self):
        super().__init__("Hacker News", "https://news.ycombinator.com/", max_items=30)
        self.news_type = "article"
        self.front_page_entries = None

    async def scrape_important_news(self) -> list[dict]:
        self.front_page_entries = None
        html = await self.fetch_text(self.base_url)
        rows = BeautifulSoup(html, "html.parser").select("tr.athing[id]")
        if not rows:
            raise RuntimeError("Hacker News 首页未解析出有效条目，请检查来源页面结构")
        selected = []
        seen_ids = set()
        for row in rows[:self.max_items]:
            item = self._parse_row(row)
            if item is None:
                raise RuntimeError("Hacker News 首页条目的标题、ID 或时间无效，保留上次列表")
            if item["url"] in seen_ids:
                continue
            seen_ids.add(item["url"])
            selected.append(item)

        # Membership must update even if every story is already in the database.
        self.front_page_entries = [{"story_url": item["url"], "source_url": item["source_link"]}
                                   for item in selected]
        articles = self.create_result_buffer()
        for item in selected:
            url = item["url"]
            if self.incremental_mode and (url in self.existing_urls or url == self.last_news_url):
                continue
            articles.append(item)
        return articles

    def _parse_row(self, row) -> dict | None:
        story_id = str(row.get("id") or "")
        link = row.select_one(".titleline > a[href]")
        metadata = row.find_next_sibling("tr")
        timestamp = metadata.select_one(".age[title]") if metadata else None
        if link is None or timestamp is None or not story_id.isdigit():
            return None
        title = link.get_text(" ", strip=True)
        if not title:
            return None
        try:
            published_at = datetime.fromisoformat(timestamp["title"].split()[0].replace("Z", "+00:00"))
            if published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=timezone.utc)
        except (ValueError, IndexError):
            return None
        discussion_url = f"https://news.ycombinator.com/item?id={story_id}"
        url = urljoin(self.base_url, link["href"])
        parsed_url = urlparse(url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            url = discussion_url
        author = metadata.select_one(".hnuser")
        # The HN permalink identifies this submission even when another source
        # links to the same article. Public reads use the saved outbound link.
        return {
            "title": title,
            "content": "",
            "url": discussion_url,
            "source_link": url,
            "published_at": published_at.isoformat(),
            "author": author.get_text(" ", strip=True) if author else self.site_name,
        }
