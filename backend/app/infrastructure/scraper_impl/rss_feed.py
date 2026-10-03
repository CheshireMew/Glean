from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Dict, List, Optional
from urllib.parse import urldefrag, urlsplit

from bs4 import BeautifulSoup

from .base import BaseScraper
from ...domain.ai_sources import AI_SOURCES


class RssFeedScraper(BaseScraper):
    transport_kind = "rss"

    def __init__(self, source: Dict):
        super().__init__(source["display_name"], source["site_url"], max_items=source["default_limit"])
        self.news_type = source["content_kind"]
        self.feed_url = source["feed_url"]
        self.parser_type = source.get("parser_type") or "generic"
        self.identity_fragment = next(("glean-" + source["slug"] for item in AI_SOURCES
            if item.get("rss_slug") == source.get("slug") and item.get("separate_identity")), "")
        self.snapshot_feed = any(item.get("snapshot") and item.get("rss_slug") == source.get("slug")
                                 for item in AI_SOURCES if item.get("rss_slug"))
        self.front_page_entries = None
        self.front_page_items = None

    async def scrape_important_news(self) -> List[Dict]:
        self.front_page_entries = self.front_page_items = None
        xml_content = await self.fetch_text(self.feed_url)
        entries = self.parse_entries(xml_content, limit=self.max_items)
        if self.snapshot_feed:
            self.front_page_items = entries
            self.front_page_entries = [{"story_url": item["url"], "source_url": item.get("source_link", item["url"])} for item in entries]
        articles: List[Dict] = self.create_result_buffer()
        seen_urls: set[str] = set()
        for item in entries:
            url = item["url"]
            if url in seen_urls:
                continue
            seen_urls.add(url)
            # Feeds can reorder posts. Inspect the whole bounded snapshot instead
            # of stopping at consecutive known entries and missing later updates.
            if self.incremental_mode and (url in self.existing_urls or url == self.last_news_url):
                continue
            articles.append(item)
            if len(articles) >= self.max_items:
                break
        return articles

    async def preview(self, limit: int) -> List[Dict]:
        # No run(), incremental state, result buffer or persistence callback here.
        try:
            await self.transport.start(self)
            xml_content = await self.fetch_text(self.feed_url, delay_range=(0, 0), max_retries=1)
            return self.parse_entries(xml_content, limit=limit)
        finally:
            await self.transport.close(self)

    def parse_entries(self, xml_content: str, limit: int | None = None) -> List[Dict]:
        if not xml_content:
            raise RuntimeError("RSS 源返回了空响应")
        soup = BeautifulSoup(xml_content, "xml")
        if not (soup.find("rss") or soup.find("feed") or soup.find("RDF")):
            raise RuntimeError("响应不是支持的 RSS/Atom 格式，请检查订阅地址")
        entries = soup.find_all("item") or soup.find_all("entry")
        if not entries:
            raise RuntimeError("RSS 响应中没有 item 或 entry，可能是源格式已变化")
        articles: List[Dict] = []

        for entry in entries:
            title = self._extract_title(entry)
            url = self._extract_url(entry)
            # V2EX changes #replyN with each reply; it is still the same topic.
            if urlsplit(url).hostname in {"v2ex.com", "www.v2ex.com"}:
                url = urldefrag(url)[0]
            if not title or not url:
                continue
            source_link = url
            # Keep weekly and recommendation records independent even when the
            # same article appears in both. Public links use the unmodified URL.
            if self.identity_fragment:
                url = urldefrag(url)[0] + "#" + self.identity_fragment
            articles.append(
                {
                    "title": title,
                    "content": self._extract_content(entry),
                    "url": url,
                    **({"source_link": source_link} if self.identity_fragment else {}),
                    "published_at": self._extract_published_at(entry),
                    "source_site": self.site_name,
                    "author": self._extract_author(entry),
                    "type": self.news_type,
                }
            )
            if limit is not None and len(articles) >= limit:
                break

        if not articles:
            raise RuntimeError("RSS 条目存在，但没有解析出有效的标题和链接")
        return articles

    def _extract_title(self, entry) -> str:
        tag = entry.find("title")
        return tag.get_text(" ", strip=True) if tag else ""

    def _extract_url(self, entry) -> str:
        if self.parser_type == "summary_source_link":
            summary_link = self._extract_summary_source_link(entry)
            if summary_link:
                return summary_link

        for tag_name in ("link", "guid", "id"):
            tag = entry.find(tag_name, attrs={"rel": "alternate"}) if tag_name == "link" else None
            tag = tag or entry.find(tag_name)
            if not tag:
                continue
            href = tag.get("href") if hasattr(tag, "get") else None
            if href:
                return href.strip()
            text = tag.get_text(" ", strip=True)
            if text.startswith("http://") or text.startswith("https://"):
                return text
        return ""

    def _extract_author(self, entry) -> str:
        author_tag = entry.find("author")
        if author_tag:
            name_tag = author_tag.find("name")
            if name_tag:
                return name_tag.get_text(" ", strip=True)
            author_text = author_tag.get_text(" ", strip=True)
            if author_text:
                return author_text

        for tag_name in ("dc:creator", "creator"):
            tag = entry.find(tag_name)
            if tag and tag.get_text(" ", strip=True):
                return tag.get_text(" ", strip=True)

        return self.site_name

    def _extract_published_at(self, entry) -> str:
        for tag_name in ("published", "updated", "pubDate"):
            tag = entry.find(tag_name)
            if not tag:
                continue
            parsed = self._parse_date(tag.get_text(" ", strip=True))
            if parsed:
                return parsed
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _extract_content(self, entry) -> str:
        summary_html = ""
        for tag_name in ("content:encoded", "content", "summary", "description"):
            tag = entry.find(tag_name)
            if tag and tag.get_text(" ", strip=True):
                summary_html = tag.decode_contents() if tag.find() else tag.get_text()
                break

        if not summary_html:
            return ""

        summary_soup = BeautifulSoup(summary_html, "html.parser")
        for text_pattern in (("文章来源", "文章作者", "内容来源", "Chainfeeds 导读") if self.parser_type == "summary_source_link" else ()):
            for node in summary_soup.find_all(string=re.compile(text_pattern)):
                parent = node.parent
                if parent and getattr(parent, "decompose", None):
                    parent.decompose()

        for node in summary_soup.find_all(["script", "style"]):
            node.decompose()
        for node in summary_soup.find_all(["p", "div", "section", "article", "h1", "h2", "h3", "h4", "li", "blockquote", "pre", "tr"]):
            node.insert_before("\n\n")
            node.insert_after("\n\n")
        for node in summary_soup.find_all("br"):
            node.replace_with("\n")
        content = summary_soup.get_text()
        content = "\n".join(re.sub(r"[^\S\n]+", " ", line).strip() for line in content.splitlines())
        return re.sub(r"\n{3,}", "\n\n", content).strip()

    def _extract_summary_source_link(self, entry) -> str:
        summary_html = ""
        for tag_name in ("summary", "content", "description"):
            tag = entry.find(tag_name)
            if tag and tag.get_text(" ", strip=True):
                summary_html = tag.get_text()
                break
        if not summary_html:
            return ""

        summary_soup = BeautifulSoup(summary_html, "html.parser")
        label = summary_soup.find(string=re.compile("文章来源"))
        if label:
            current = label.parent
            while current:
                current = current.next_sibling
                if hasattr(current, "find"):
                    link = current.find("a", href=True)
                    if link:
                        return link["href"].strip()

        first_link = summary_soup.find("a", href=True)
        return first_link["href"].strip() if first_link else ""

    @staticmethod
    def _parse_date(value: str) -> Optional[str]:
        normalized = value.strip()
        if not normalized:
            return None

        iso_value = normalized.replace("Z", "+00:00")
        parsers = (
            lambda raw: datetime.fromisoformat(raw),
            lambda raw: datetime.strptime(raw, "%a, %d %b %Y %H:%M:%S %z"),
            lambda raw: datetime.strptime(raw, "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=timezone.utc),
        )
        for parser in parsers:
            try:
                dt = parser(iso_value)
                if dt.tzinfo:
                    dt = dt.astimezone(timezone(timedelta(hours=8)))
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                continue
        return None
