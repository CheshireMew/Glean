from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from .base import BaseScraper


class RssFeedScraper(BaseScraper):
    transport_kind = "rss"

    def __init__(self, source: Dict):
        super().__init__(source["display_name"], source["site_url"], max_items=source["default_limit"])
        self.news_type = source["content_kind"]
        self.feed_url = source["feed_url"]
        self.parser_type = source.get("parser_type") or "generic"

    async def scrape_important_news(self) -> List[Dict]:
        xml_content = await self.fetch_text(self.feed_url)
        if not xml_content:
            raise RuntimeError("RSS 源返回了空响应")
        soup = BeautifulSoup(xml_content, "xml")
        entries = soup.find_all("item") or soup.find_all("entry")
        if not entries:
            raise RuntimeError("RSS 响应中没有 item 或 entry，可能是源格式已变化")
        articles: List[Dict] = self.create_result_buffer()
        stopped_at_existing = False

        for entry in entries:
            title = self._extract_title(entry)
            url = self._extract_url(entry)
            if not title or not url:
                continue
            if self.should_stop_scraping(title, url):
                stopped_at_existing = True
                break

            articles.append(
                {
                    "title": title,
                    "content": self._extract_content(entry),
                    "url": url,
                    "published_at": self._extract_published_at(entry),
                    "source_site": self.site_name,
                    "author": self._extract_author(entry),
                    "type": self.news_type,
                }
            )
            if len(articles) >= self.max_items:
                break

        if not articles and not stopped_at_existing:
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
            tag = entry.find(tag_name)
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
                summary_html = tag.get_text()
                break

        if not summary_html:
            return ""

        summary_soup = BeautifulSoup(summary_html, "html.parser")
        for text_pattern in ("文章来源", "文章作者", "内容来源", "Chainfeeds 导读"):
            for node in summary_soup.find_all(string=re.compile(text_pattern)):
                parent = node.parent
                if parent and getattr(parent, "decompose", None):
                    parent.decompose()

        for link in summary_soup.find_all("a"):
            link.unwrap()

        content = re.sub(r"\s+", " ", summary_soup.get_text(" ", strip=True)).strip()
        if len(content) > 500:
            return f"{content[:500]}..."
        return content

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
