"""Shared snapshot and feed parsing for the fixed crypto media sources."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from .base import BaseScraper
from .rss_feed import RssFeedScraper
from ...domain.source_identity import source_identity


def html_text(value: str | None) -> str:
    soup = BeautifulSoup(value or "", "html.parser")
    for node in soup.find_all(["script", "style"]):
        node.decompose()
    for node in soup.find_all(["p", "div", "section", "h1", "h2", "h3", "li", "blockquote", "pre"]):
        node.insert_before("\n\n")
        node.insert_after("\n\n")
    for node in soup.find_all("br"):
        node.replace_with("\n")
    text = "\n".join(re.sub(r"[^\S\n]+", " ", line).strip() for line in soup.get_text().splitlines())
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def published_at(value) -> str:
    # API timestamps can be seconds or milliseconds; formatted dates are Beijing time.
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    parsed = RssFeedScraper._parse_date(str(value or ""))
    if not parsed:
        raise RuntimeError("媒体条目缺少有效发布时间")
    return parsed


def media_identity(url: str) -> str:
    """Compare old and new first-party URL forms without changing stored history."""
    return source_identity(url)


class MediaSnapshot:
    def select_new_items(self, items):
        results = self.create_result_buffer()
        known = {media_identity(url) for url in self.existing_urls}
        if self.last_news_url:
            known.add(media_identity(self.last_news_url))
        seen = set()
        for item in items:
            identity = media_identity(item["url"])
            if identity in seen:
                continue
            seen.add(identity)
            if self.incremental_mode and identity in known:
                self.encountered_existing_items = True
                continue
            results.append(item)
            if len(results) >= self.max_items:
                break
        return results


class MediaRssScraper(MediaSnapshot, RssFeedScraper):
    source_name = ""
    homepage = ""
    feed = ""
    content_kind = "article"
    required_category = None
    importance_flag = ""

    def __init__(self):
        super().__init__({
            "display_name": self.source_name, "site_url": self.homepage,
            "default_limit": 20 if self.content_kind == "article" else 10,
            "content_kind": self.content_kind, "feed_url": self.feed,
        })

    def accepts_entry(self, entry) -> bool:
        categories = {tag.get_text(strip=True) for tag in entry.find_all("category")}
        if self.required_category is not None and not any(categories):
            raise RuntimeError("RSS 条目缺少栏目分类字段")
        return self.required_category is None or self.required_category in categories

    def _extract_published_at(self, entry) -> str:
        for name in ("published", "updated", "pubDate"):
            tag = entry.find(name)
            if tag:
                return published_at(tag.get_text(strip=True))
        raise RuntimeError("RSS 条目缺少发布时间")

    def parse_entries(self, xml_content: str, limit: int | None = None):
        # Validate the original feed before filtering. A valid feed with no matching
        # column is an empty update; malformed XML or JSON is an error.
        items = super().parse_entries(xml_content)
        soup = BeautifulSoup(xml_content, "xml")
        accepted_urls = {self._extract_url(entry) for entry in (soup.find_all("item") or soup.find_all("entry"))
                         if self.accepts_entry(entry)}
        items = [dict(item, is_marked_important=bool(self.importance_flag),
                      site_importance_flag=self.importance_flag)
                 for item in items if item["url"] in accepted_urls]
        return items if limit is None else items[:limit]

    async def scrape_important_news(self):
        return self.select_new_items(self.parse_entries(await self.fetch_text(self.feed_url)))


class MediaApiScraper(MediaSnapshot, BaseScraper):
    transport_kind = "api"
    allow_empty_results = True
    page_size = 50
    max_pages = 10
    source_name = ""
    homepage = ""
    endpoint = ""
    content_kind = "news"

    def __init__(self):
        super().__init__(self.source_name, self.homepage, 20 if self.content_kind == "article" else 10)
        self.news_type = self.content_kind
        self.api_url = self.endpoint

    def prepare(self):
        pass

    async def fetch_items_page(self, page):
        raise NotImplementedError

    def parse_item(self, raw):
        raise NotImplementedError

    def make_item(self, *, title, content, url, date, author=None, importance_flag="", content_is_html=True):
        if not title or not url or urlsplit(url).scheme not in {"http", "https"}:
            raise RuntimeError("媒体接口条目缺少有效标题或站内链接")
        if isinstance(author, dict):
            author = author.get("nickname") or author.get("name")
        if author is not None and not isinstance(author, str):
            raise RuntimeError("媒体接口作者格式已变化")
        return {"title": title.strip(), "content": html_text(content) if content_is_html else (content or '').strip(), "url": url,
                "published_at": published_at(date), "author": author or self.site_name,
                "is_marked_important": bool(importance_flag), "site_importance_flag": importance_flag}

    async def scrape_important_news(self):
        self.prepare()
        candidates, seen = [], set()
        known = {media_identity(url) for url in self.existing_urls}
        if self.last_news_url:
            known.add(media_identity(self.last_news_url))
        new_count = 0
        for page in range(1, self.max_pages + 1):
            raw_items, has_more = await self.fetch_items_page(page)
            if not isinstance(raw_items, list) or any(not isinstance(raw, dict) for raw in raw_items):
                raise RuntimeError("媒体接口列表格式已变化")
            for raw in raw_items:
                item = self.parse_item(raw)
                if item is None:
                    continue
                identity = media_identity(item["url"])
                if identity in seen:
                    continue
                seen.add(identity)
                candidates.append(item)
                if not self.incremental_mode or identity not in known:
                    new_count += 1
            # Inspect the entire page: providers sometimes pin or reorder known posts.
            if new_count >= self.max_items or not has_more or not raw_items:
                break
        return self.select_new_items(candidates)
