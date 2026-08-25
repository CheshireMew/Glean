from __future__ import annotations

import re
from typing import Dict, Optional

from shared.content_contract import ARCHIVED_STAGE, INCOMING_STAGE
from .base_repository import BaseRepository
from ..lease_fencing import assert_current_operation_lease
from ...core.time import format_utc_time, normalize_source_time


class NewsRepository(BaseRepository):
    @staticmethod
    def _normalize_news_content(content: str) -> str:
        normalized = content.replace("\r\n", "\n").replace("\r", "\n")
        return re.sub(r"\n\s*\n+", "\n", normalized).strip()

    def insert_news(self, news_data: Dict) -> Optional[int]:
        if news_data.get("content"):
            news_data["content"] = self._normalize_news_content(news_data["content"])

        scraped_at = format_utc_time()
        cursor = self.execute(
            """
            INSERT OR IGNORE INTO news (
                title, content, source_site, source_url, published_at, scraped_at,
                is_marked_important, site_importance_flag, stage, type, author
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                news_data["title"], news_data.get("content", ""), news_data["source_site"],
                news_data["url"], normalize_source_time(news_data["published_at"]), scraped_at,
                news_data.get("is_marked_important", False), news_data.get("site_importance_flag", ""),
                INCOMING_STAGE, news_data.get("type", "news"), news_data.get("author", ""),
            ),
        )
        return int(cursor.lastrowid) if cursor.rowcount > 0 and cursor.lastrowid is not None else None

    def insert_news_batch(self, items: list[Dict]) -> int:
        if not items:
            return 0
        scraped_at = format_utc_time()
        rows = []
        for item in items:
            content = item.get("content", "")
            if content:
                content = self._normalize_news_content(content)
            rows.append(
                (
                    item["title"],
                    content,
                    item["source_site"],
                    item["url"],
                    normalize_source_time(item["published_at"]),
                    scraped_at,
                    item.get("is_marked_important", False),
                    item.get("site_importance_flag", ""),
                    INCOMING_STAGE,
                    item.get("type", "news"),
                    item.get("author", ""),
                )
            )

        managed_conn = self.conn is None
        conn = self.conn or self.db.connect()
        started_transaction = False
        try:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
                started_transaction = True
            before = conn.total_changes
            conn.executemany(
                """
                INSERT OR IGNORE INTO news (
                    title, content, source_site, source_url, published_at, scraped_at,
                    is_marked_important, site_importance_flag, stage, type, author
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            inserted = conn.total_changes - before
            if started_transaction:
                assert_current_operation_lease(conn)
                conn.commit()
            return inserted
        except Exception:
            if started_transaction and conn.in_transaction:
                conn.rollback()
            raise
        finally:
            if managed_conn:
                conn.close()

    def update_news(self, news_id: int, updates: Dict):
        if "content" in updates and updates["content"]:
            updates["content"] = self._normalize_news_content(updates["content"])
        set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
        values = list(updates.values()) + [news_id]
        self.execute(f"UPDATE news SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", tuple(values))

    def delete_news(self, news_id: int) -> bool:
        cursor = self.execute("DELETE FROM news WHERE id = ?", (news_id,))
        return cursor.rowcount > 0

    def delete_by_source_url(self, source_url: str):
        self.execute("DELETE FROM news WHERE source_url = ?", (source_url,))

    def reset_to_incoming_by_source_url(self, source_url: str) -> bool:
        cursor = self.execute(
            """
            UPDATE news
            SET stage = ?, event_id = NULL, event_similarity = NULL, is_event_primary = 0
            WHERE source_url = ?
            """,
            (INCOMING_STAGE, source_url),
        )
        return cursor.rowcount > 0

    def mark_clustered(self, news_id: int, event_id: int, similarity: float, is_primary: bool) -> None:
        self.execute(
            """
            UPDATE news
            SET stage = ?, event_id = ?, event_similarity = ?, is_event_primary = ?
            WHERE id = ?
            """,
            (ARCHIVED_STAGE, event_id, similarity, int(is_primary), news_id),
        )
