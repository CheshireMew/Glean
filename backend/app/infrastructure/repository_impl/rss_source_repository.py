from __future__ import annotations

from typing import Dict, List, Optional

from .base_repository import BaseRepository


class RssSourceRepository(BaseRepository):
    def list_sources(self, enabled_only: bool = False) -> List[Dict]:
        where = "WHERE enabled = 1" if enabled_only else ""
        cursor = self.execute(
            f"""
            SELECT id, slug, display_name, feed_url, site_url, content_kind, parser_type,
                   default_limit, default_interval, enabled, authority_type, is_official,
                   created_at, updated_at
            FROM rss_sources
            {where}
            ORDER BY enabled DESC, display_name COLLATE NOCASE ASC, id ASC
            """
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_source(self, source_id: int) -> Optional[Dict]:
        cursor = self.execute(
            """
            SELECT id, slug, display_name, feed_url, site_url, content_kind, parser_type,
                   default_limit, default_interval, enabled, authority_type, is_official,
                   created_at, updated_at
            FROM rss_sources
            WHERE id = ?
            """,
            (source_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_source_by_slug(self, slug: str) -> Optional[Dict]:
        cursor = self.execute(
            """
            SELECT id, slug, display_name, feed_url, site_url, content_kind, parser_type,
                   default_limit, default_interval, enabled, authority_type, is_official,
                   created_at, updated_at
            FROM rss_sources
            WHERE slug = ?
            """,
            (slug,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def create_source(self, payload: Dict) -> Dict:
        cursor = self.execute(
            """
            INSERT INTO rss_sources (
                slug, display_name, feed_url, site_url, content_kind, parser_type,
                default_limit, default_interval, enabled, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                payload["slug"],
                payload["display_name"],
                payload["feed_url"],
                payload["site_url"],
                payload["content_kind"],
                payload["parser_type"],
                payload["default_limit"],
                payload["default_interval"],
                1 if payload["enabled"] else 0,
            ),
        )
        return self.get_source(cursor.lastrowid)

    def update_source(self, source_id: int, payload: Dict) -> Optional[Dict]:
        self.execute(
            """
            UPDATE rss_sources
            SET slug = ?, display_name = ?, feed_url = ?, site_url = ?, content_kind = ?,
                parser_type = ?, default_limit = ?, default_interval = ?, enabled = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                payload["slug"],
                payload["display_name"],
                payload["feed_url"],
                payload["site_url"],
                payload["content_kind"],
                payload["parser_type"],
                payload["default_limit"],
                payload["default_interval"],
                1 if payload["enabled"] else 0,
                source_id,
            ),
        )
        return self.get_source(source_id)

    def delete_source(self, source_id: int) -> bool:
        cursor = self.execute("DELETE FROM rss_sources WHERE id = ?", (source_id,))
        return cursor.rowcount > 0
