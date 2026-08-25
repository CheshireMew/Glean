from __future__ import annotations

from typing import Dict, List, Optional

from shared.content_contract import INCOMING_STAGE
from .base_repository import BaseRepository
from ...core.time import utc_cutoff


class NewsRuntimeRepository(BaseRepository):
    def get_latest_news_url(self, source_site: str) -> Optional[str]:
        cursor = self.execute(
            "SELECT source_url FROM news WHERE source_site = ? ORDER BY scraped_at DESC LIMIT 1",
            (source_site,),
        )
        row = cursor.fetchone()
        return row["source_url"] if row else None

    def get_recent_news_urls(self, source_site: str, limit: int = 50) -> List[str]:
        cursor = self.execute(
            "SELECT source_url FROM news WHERE source_site = ? ORDER BY scraped_at DESC LIMIT ?",
            (source_site, limit),
        )
        return [row["source_url"] for row in cursor.fetchall()]

    def get_news_by_time_range(self, hours: int, type_filter: str = "news", limit: int = 1000) -> List[Dict]:
        params: List[object] = [INCOMING_STAGE, type_filter]
        sql = """
                SELECT id, title, content, source_site, source_url, published_at, scraped_at,
                       is_marked_important, site_importance_flag, stage, type
                FROM news
                WHERE stage = ? AND type = ?
            """
        if hours > 0:
            threshold = utc_cutoff(hours)
            sql += " AND scraped_at >= ?"
            params.append(threshold)
        sql += " ORDER BY scraped_at ASC, id ASC LIMIT ?"
        params.append(limit)
        cursor = self.execute(sql, tuple(params))
        rows = cursor.fetchall()
        return [
            {
                "id": row["id"], "title": row["title"], "content": row["content"],
                "source_site": row["source_site"], "source_url": row["source_url"], "url": row["source_url"],
                "published_at": row["published_at"], "scraped_at": row["scraped_at"],
                "is_marked_important": row["is_marked_important"],
                "site_importance_flag": row["site_importance_flag"], "stage": row["stage"], "type": row["type"],
            }
            for row in rows
        ]

    def count_news_by_time_range(self, hours: int, type_filter: str = "news") -> int:
        params: List[object] = [INCOMING_STAGE, type_filter]
        sql = "SELECT COUNT(*) AS total FROM news WHERE stage = ? AND type = ?"
        if hours > 0:
            sql += " AND scraped_at >= ?"
            params.append(utc_cutoff(hours))
        return int(self.execute(sql, tuple(params)).fetchone()["total"])

    def get_news_by_ids(self, news_ids: List[int]) -> List[Dict]:
        if not news_ids:
            return []
        placeholders = ",".join(["?" for _ in news_ids])
        cursor = self.execute(f"SELECT id, title FROM news WHERE id IN ({placeholders})", tuple(news_ids))
        return [dict(row) for row in cursor.fetchall()]

    def get_incoming_news_since(self, cutoff_time: str, type_filter: str, limit: int = 1000) -> List[Dict]:
        cursor = self.execute(
                """
                SELECT id, title, content, source_url, source_site, published_at, scraped_at, type
                FROM news
                WHERE stage = ? AND scraped_at >= ? AND type = ?
                ORDER BY scraped_at ASC, id ASC
                LIMIT ?
                """,
                (INCOMING_STAGE, cutoff_time, type_filter, limit),
        )
        return [dict(row) for row in cursor.fetchall()]

    def count_incoming_news_since(self, cutoff_time: str, type_filter: str) -> int:
        cursor = self.execute(
            "SELECT COUNT(*) AS total FROM news WHERE stage = ? AND scraped_at >= ? AND type = ?",
            (INCOMING_STAGE, cutoff_time, type_filter),
        )
        return int(cursor.fetchone()["total"])
