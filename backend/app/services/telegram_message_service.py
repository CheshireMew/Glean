from __future__ import annotations

import html as html_lib
from typing import Dict, List

from shared.content_contract import CONTENT_KIND_ARTICLE, CONTENT_KIND_NEWS, TELEGRAM_MESSAGE_LIMIT


class TelegramMessageService:
    def __init__(self, attribution_url: str = ""):
        self._attribution_url = attribution_url

    @staticmethod
    def _split_raw_text(value: str, escaped_budget: int) -> List[str]:
        if not value:
            return []
        chunks: List[str] = []
        remaining = value
        while remaining:
            low, high = 1, len(remaining)
            best = 0
            while low <= high:
                middle = (low + high) // 2
                if len(html_lib.escape(remaining[:middle])) <= escaped_budget:
                    best = middle
                    low = middle + 1
                else:
                    high = middle - 1
            if best <= 0:
                raise ValueError("无法在 Telegram 字符限制内安全分段")
            if best < len(remaining):
                floor = max(1, int(best * 0.6))
                break_at = max(remaining.rfind("\n", floor, best), remaining.rfind(" ", floor, best))
                if break_at > 0:
                    best = break_at
            chunks.append(remaining[:best].strip())
            remaining = remaining[best:].lstrip()
        return [chunk for chunk in chunks if chunk]

    @staticmethod
    def _entry_header(entry: Dict, continuation: bool = False) -> tuple[str, str]:
        raw_title = str(entry.get("title") or "无标题")
        title_preview = raw_title if len(raw_title) <= 500 else f"{raw_title[:500]}…"
        escaped_title = html_lib.escape(title_preview)
        escaped_url = html_lib.escape(str(entry.get("source_url") or ""), quote=True)
        icon = "📰" if (entry.get("content_type") or CONTENT_KIND_NEWS) == CONTENT_KIND_ARTICLE else "⚡"
        suffix = "（续）" if continuation else ""
        header = f'{icon} <b><a href="{escaped_url}">{escaped_title}{suffix}</a></b>'
        extra_title = raw_title if title_preview != raw_title else ""
        return header, extra_title

    def format_entry_parts(self, entry: Dict, limit: int = TELEGRAM_MESSAGE_LIMIT) -> List[str]:
        first_header, extra_title = self._entry_header(entry)
        body = entry.get("enriched_summary") or entry.get("enriched_impact") or ""
        if not body:
            body = entry.get("content") or ""
        raw_body = f"{extra_title}\n\n{body}".strip()
        if not raw_body:
            if len(first_header) > limit:
                raise ValueError("标题超过 Telegram 字符限制")
            return [first_header]

        parts: List[str] = []
        remaining = raw_body
        continuation = False
        while remaining:
            header, _ = self._entry_header(entry, continuation=continuation)
            budget = limit - len(header) - 2
            chunks = self._split_raw_text(remaining, budget)
            chunk = chunks[0]
            message = f"{header}\n\n{html_lib.escape(chunk)}"
            if len(message) > limit:
                raise ValueError("消息分段超过 Telegram 字符限制")
            parts.append(message)
            remaining = remaining[len(chunk):].lstrip()
            continuation = True
        return parts

    def format_entry(self, entry: Dict) -> str:
        return "\n\n".join(self.format_entry_parts(entry))

    def build_daily_report(self, entries: List[Dict], content_kind: str, now) -> tuple[str, List[str]]:
        formatted_items = []
        seen_identifiers = set()
        for entry in entries:
            identifier = entry.get("source_url") or entry["title"]
            if identifier in seen_identifiers:
                continue
            seen_identifiers.add(identifier)
            section = html_lib.escape(entry.get("digest_section") or "其他")
            source_count = int(entry.get("source_count") or 1)
            corroboration = f" · {source_count} 个来源" if source_count > 1 else ""
            raw_summary = str(entry.get("enriched_summary") or entry.get("review_summary") or entry.get("content") or "")
            escaped_url = html_lib.escape(str(entry.get("source_url") or ""), quote=True)
            escaped_title = html_lib.escape(str(entry.get("title") or ""))
            prefix = f'<b>【{section}】</b> <a href="{escaped_url}">{escaped_title}</a>{corroboration}'
            if not raw_summary:
                formatted_items.append(prefix)
                continue
            chunks = self._split_raw_text(raw_summary, max(256, 3000 - len(prefix)))
            for index, chunk in enumerate(chunks):
                continuation = "（续）" if index else ""
                item_prefix = prefix if index == 0 else f'<a href="{escaped_url}">{escaped_title}{continuation}</a>'
                formatted_items.append(f"{item_prefix}\n↳ {html_lib.escape(chunk)}")

        report_title = f"{now.strftime('%Y-%m-%d')} {'深度日报' if content_kind == CONTENT_KIND_ARTICLE else '精选日报'}"
        return report_title, formatted_items

    def compose_daily_report_part(
        self,
        report_title: str,
        items: List[str],
        intro: str | None = None,
        footer: str | None = None,
    ) -> str:
        attribution = "🤖 由 Glean 自动生成"
        if self._attribution_url:
            escaped_url = html_lib.escape(self._attribution_url, quote=True)
            attribution = f'🤖 由 <a href="{escaped_url}">Glean</a> 自动生成'
        rendered_footer = attribution if footer is None else html_lib.escape(str(footer))
        sections = [f"📅 <b>{html_lib.escape(report_title)}</b>"]
        if intro:
            sections.append(html_lib.escape(str(intro)))
        sections.extend(items)
        if rendered_footer:
            sections.append(rendered_footer)
        return "\n\n".join(sections)

    def split_daily_report_parts(
        self,
        report_title: str,
        items: List[str],
        limit: int = TELEGRAM_MESSAGE_LIMIT,
        intro: str | None = None,
        footer: str | None = None,
    ) -> List[str]:
        if not items:
            return [self.compose_daily_report_part(report_title, [], intro, footer)]

        parts: List[str] = []
        current_items: List[str] = []
        for item in items:
            candidate_items = [*current_items, item]
            candidate_text = self.compose_daily_report_part(report_title, candidate_items, intro, footer)
            single_text = self.compose_daily_report_part(report_title, [item], intro, footer)
            if len(single_text) > limit:
                raise ValueError("单条日报内容超过 Telegram 字符限制")
            if current_items and len(candidate_text) > limit:
                parts.append(self.compose_daily_report_part(report_title, current_items, intro, footer))
                current_items = [item]
            else:
                current_items = candidate_items

        if current_items:
            parts.append(self.compose_daily_report_part(report_title, current_items, intro, footer))
        return parts
