from __future__ import annotations

from typing import Dict, List

from shared.content_contract import (
    ARCHIVE_STATUS_READY,
    ARCHIVE_TABLE,
)
from .base_repository import BaseRepository
from ...core.time import format_utc_time

_UNSET = object()


class ArchiveRepository(BaseRepository):
    def create_entry(self, news: Dict, event_id: int) -> None:
        self.execute(
            f"""
            INSERT OR IGNORE INTO {ARCHIVE_TABLE} (
                id, title, content, source_site, source_url, published_at, scraped_at, archived_at,
                is_marked_important, site_importance_flag, archive_status, content_type, source_item_id, event_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?)
            """,
            (
                news["id"],
                news["title"],
                news["content"],
                news["source_site"],
                news["source_url"],
                news["published_at"],
                news["scraped_at"],
                news.get("is_marked_important", False),
                news.get("site_importance_flag", ""),
                ARCHIVE_STATUS_READY,
                news.get("type", "news"),
                news["id"],
                event_id,
            ),
        )

    def update_status(
        self,
        entry_id: int,
        archive_status: str,
        *,
        block_reason=_UNSET,
        restored_from_blocklist=_UNSET,
        archived_at=_UNSET,
    ) -> bool:
        return self._update_status("id = ?", (entry_id,), archive_status, block_reason, restored_from_blocklist, archived_at)

    def update_status_by_source_url(
        self,
        source_url: str,
        archive_status: str,
        *,
        block_reason=_UNSET,
        restored_from_blocklist=_UNSET,
        archived_at=_UNSET,
    ) -> bool:
        return self._update_status("source_url = ?", (source_url,), archive_status, block_reason, restored_from_blocklist, archived_at)

    def _update_status(
        self,
        where_clause: str,
        where_params: tuple,
        archive_status: str,
        block_reason,
        restored_from_blocklist,
        archived_at,
    ) -> bool:
        updates = ["archive_status = ?"]
        params: List[object] = [archive_status]

        if block_reason is not _UNSET:
            updates.append("block_reason = ?")
            params.append(block_reason)
        if restored_from_blocklist is not _UNSET:
            updates.append("restored_from_blocklist = ?")
            params.append(restored_from_blocklist)
        if archived_at is not _UNSET:
            updates.append("archived_at = ?")
            params.append(archived_at if archived_at is not None else format_utc_time())

        cursor = self.execute(
            f"UPDATE {ARCHIVE_TABLE} SET {', '.join(updates)} WHERE {where_clause}",
            tuple([*params, *where_params]),
        )
        return cursor.rowcount > 0

    def delete_by_source_url(self, source_url: str) -> bool:
        cursor = self.execute(f"DELETE FROM {ARCHIVE_TABLE} WHERE source_url = ?", (source_url,))
        return cursor.rowcount > 0

    def delete_by_event(self, event_id: int) -> int:
        return self.execute(f"DELETE FROM {ARCHIVE_TABLE} WHERE event_id = ?", (event_id,)).rowcount

    def replace_event_source(self, event_id: int, replacement: Dict) -> int:
        return self.execute(
            f"""
            UPDATE {ARCHIVE_TABLE}
            SET title = ?, content = ?, source_site = ?, source_url = ?, published_at = ?, source_item_id = ?
            WHERE event_id = ?
            """,
            (
                replacement["title"],
                replacement.get("content") or "",
                replacement["source_site"],
                replacement["source_url"],
                replacement["published_at"],
                replacement["id"],
                event_id,
            ),
        ).rowcount
