from __future__ import annotations

from typing import Dict, List, Optional

from shared.content_contract import ARCHIVE_STATUS_READY, ARCHIVE_TABLE
from .base_repository import BaseRepository


class ArchiveQueryRepository(BaseRepository):
    def get_entry(self, entry_id: int) -> Optional[Dict]:
        cursor = self.execute(f"SELECT * FROM {ARCHIVE_TABLE} WHERE id = ?", (entry_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_entries(
        self,
        page: int = 1,
        limit: int = 50,
        source: Optional[str] = None,
        keyword: Optional[str] = None,
        content_kind: str = "news",
        archive_status: Optional[str] = None,
    ) -> Dict:
        where = "content_type = ?"
        params = [content_kind]

        if archive_status:
            where += " AND archive_status = ?"
            params.append(archive_status)
        if source:
            where += " AND source_site = ?"
            params.append(source)
        if keyword:
            where += " AND (title LIKE ? OR content LIKE ?)"
            term = f"%{keyword}%"
            params.extend([term, term])

        return self.paginated_query(
            table=ARCHIVE_TABLE,
            fields="id, title, content, source_site, source_url, published_at, scraped_at, archived_at, is_marked_important, site_importance_flag, archive_status, content_type, source_item_id, event_id, restored_from_blocklist, block_reason",
            where=where,
            where_params=tuple(params),
            order_by="published_at DESC",
            page=page,
            limit=limit,
        )

    def list_filter_candidates(self, start_time: str, content_kind: str, limit: int = 1000) -> List[Dict]:
        cursor = self.execute(
            f"""
            SELECT id, title, content, source_site, source_url, published_at, scraped_at, archived_at,
                   is_marked_important, site_importance_flag, source_item_id, event_id, content_type
            FROM {ARCHIVE_TABLE}
            WHERE archived_at >= ? AND archive_status = ? AND content_type = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (start_time, ARCHIVE_STATUS_READY, content_kind, limit),
        )
        return [dict(row) for row in cursor.fetchall()]

    def list_status_batch(self, archive_status: str, content_kind: str, limit: int = 1000) -> List[Dict]:
        cursor = self.execute(
            f"""
            SELECT id, title, content, source_site, source_url, published_at, scraped_at, archived_at,
                   is_marked_important, site_importance_flag, archive_status, content_type,
                   source_item_id, event_id, restored_from_blocklist, block_reason
            FROM {ARCHIVE_TABLE}
            WHERE archive_status = ? AND content_type = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (archive_status, content_kind, limit),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_source_url(self, entry_id: int) -> Optional[str]:
        cursor = self.execute(f"SELECT source_url FROM {ARCHIVE_TABLE} WHERE id = ?", (entry_id,))
        row = cursor.fetchone()
        return row["source_url"] if row else None

    def get_event_id(self, entry_id: int) -> Optional[int]:
        cursor = self.execute(f"SELECT event_id FROM {ARCHIVE_TABLE} WHERE id = ?", (entry_id,))
        row = cursor.fetchone()
        return int(row["event_id"]) if row and row["event_id"] is not None else None
