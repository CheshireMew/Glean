from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup

from .base import BaseScraper


class WaytoAGIScraper(BaseScraper):
    """Read the public page's embedded document data with one HTTP request."""

    transport_kind = "http"
    allow_empty_results = True

    def __init__(self):
        super().__init__("WaytoAGI", "https://waytoagi.feishu.cn/wiki/QPe5w5g7UisbEkkow8XcDmOpn8e", 100)
        self.news_type = "article"
        self.front_page_entries = self.front_page_items = None

    async def scrape_important_news(self) -> list[dict]:
        self.front_page_entries = self.front_page_items = None
        items = self.parse_updates(await self.fetch_text(self.base_url))[:self.max_items]
        self.front_page_entries = [{"story_url": item["url"], "source_url": item["source_link"]} for item in items]
        self.front_page_items = items
        results = self.create_result_buffer()
        for item in items:
            if self.incremental_mode and (item["url"] in self.existing_urls or item["url"] == self.last_news_url):
                continue
            results.append(item)
        return results

    @staticmethod
    def _text(block: dict) -> str:
        parts = block.get("text", {}).get("initialAttributedTexts", {}).get("text") or {}
        return "".join(parts.values()).strip()

    @staticmethod
    def _rich_text(block: dict) -> tuple[str, list[dict]]:
        text = block.get("text", {})
        initial = text.get("initialAttributedTexts", {})
        pool = text.get("apool", {}).get("numToAttrib") or {}
        links, chunks = [], []
        for key, raw in (initial.get("text") or {}).items():
            # Feishu lengths are UTF-16 code units, not Python character counts.
            encoded = raw.encode("utf-16-le")
            offset = 0
            for match in re.finditer(r"((?:\*[0-9a-z]+)*)(?:\|[0-9a-z]+)?\+([0-9a-z]+)", (initial.get("attribs") or {}).get(key, "")):
                length = int(match[2], 36) * 2
                segment = encoded[offset:offset + length].decode("utf-16-le")
                offset += length
                for number in re.findall(r"\*([0-9a-z]+)", match[1]):
                    attribute = pool.get(str(int(number, 36)), [])
                    if len(attribute) != 2 or attribute[0] != "inline-component":
                        continue
                    component = json.loads(attribute[1])
                    if component.get("type") != "mention_doc":
                        continue
                    data = component.get("data", {})
                    title, url = data.get("title", ""), data.get("raw_url", "")
                    parsed = urlsplit(url)
                    if title and parsed.scheme in {"http", "https"} and parsed.netloc:
                        links.append({"title": title, "url": urlunsplit(parsed._replace(query="", fragment=""))})
                        segment = title
                chunks.append(segment)
            chunks.append(encoded[offset:].decode("utf-16-le"))
        return "".join(chunks).strip(), links

    def parse_updates(self, html: str, today: datetime | None = None) -> list[dict]:
        marker = "clientVars: Object("
        soup = BeautifulSoup(html, "html.parser")
        data = None
        for script in soup.find_all("script"):
            text = script.string or ""
            position = text.find(marker)
            if position >= 0:
                # Decode JSON only; never execute scripts delivered by the page.
                payload, _ = json.JSONDecoder().raw_decode(text[position + len(marker):].lstrip())
                data = payload.get("data")
                break
        if not data or not data.get("block_map"):
            raise RuntimeError("WaytoAGI 公开页未提供文档数据，保留上次更新日志")
        blocks = data["block_map"]
        root = blocks.get(data.get("id"), {}).get("data", {})
        today = today or datetime.now(timezone(timedelta(hours=8)))
        items, active, finished = [], False, False
        seen = set()

        def children(block):
            for child_id in block.get("children", []):
                if child_id not in blocks:
                    raise RuntimeError("WaytoAGI 更新日志数据不完整，保留上次列表")
                child = blocks[child_id]["data"]
                if child.get("hidden"):
                    continue
                yield child_id, child
                yield from children(child)

        for block_id in root.get("children", []):
            block = blocks.get(block_id, {}).get("data", {})
            heading = self._text(block)
            if not active:
                if "近" in heading and "更新日志" in heading and block.get("type", "").startswith("heading"):
                    active = True
                continue
            if block.get("type") in {"heading1", "heading2"}:
                finished = True
                break
            date = re.fullmatch(r"\s*(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*", heading)
            if not date:
                continue
            year = int(date[1]) if date[1] else today.year - (int(date[2]) > today.month)
            published = datetime(year, int(date[2]), int(date[3]), tzinfo=timezone(timedelta(hours=8))).isoformat()
            for child_id, child in children(block):
                if child.get("type") not in {"bullet", "ordered", "text"} or child_id in seen:
                    continue
                text, links = self._rich_text(child)
                if not text:
                    continue
                seen.add(child_id)
                title = links[0]["title"] if links else text[:120]
                content = text
                prefix = f"《{title}》"
                if content.startswith(prefix):
                    content = content[len(prefix):].strip()
                elif content == title:
                    content = ""
                # A stable document block identifies the update even if another
                # source already links to its target article.
                url = f"{self.base_url}#{child_id}"
                items.append({"title": title, "content": content, "url": url,
                              "source_link": links[0]["url"] if links else url,
                              "published_at": published, "source_site": self.site_name,
                              "author": self.site_name, "type": "article"})
        if not finished or not items:
            raise RuntimeError("WaytoAGI 未解析出完整的近期更新日志，保留上次列表")
        return items
