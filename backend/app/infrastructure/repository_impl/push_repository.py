from __future__ import annotations

from typing import Dict, List

from shared.content_contract import (
    DELIVERY_STATUS_PENDING,
    ENRICHMENT_STATUS_COMPLETED,
    REVIEW_STATUS_SELECTED,
    REVIEW_TABLE,
)
from .base_repository import BaseRepository


class PushRepository(BaseRepository):
    def get_pending_delivery_entries(self, content_kind: str, profile_slug: str) -> List[Dict]:
        cursor = self.execute(
            f"""
            SELECT r.* FROM {REVIEW_TABLE} r
            WHERE r.content_type = ? AND r.profile_slug = ?
              AND r.review_status = ? AND r.delivery_status = ?
              AND r.enrichment_status = ?
            ORDER BY r.queued_at ASC, r.id ASC
            """,
            (content_kind, profile_slug, REVIEW_STATUS_SELECTED, DELIVERY_STATUS_PENDING, ENRICHMENT_STATUS_COMPLETED),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_pending_review_entries(self, content_kind: str, profile_slug: str) -> List[Dict]:
        cursor = self.execute(
            f"""
                SELECT r.*
                FROM {REVIEW_TABLE} r
                LEFT JOIN push_logs p ON r.id = p.review_entry_id AND p.status = 'success'
                WHERE p.id IS NULL
                  AND r.content_type = ?
                  AND r.profile_slug = ?
                  AND r.review_status = ?
                  AND r.delivery_status = ?
                  AND r.enrichment_status = ?
                ORDER BY r.queued_at ASC
            """,
            (
                content_kind,
                profile_slug,
                REVIEW_STATUS_SELECTED,
                DELIVERY_STATUS_PENDING,
                ENRICHMENT_STATUS_COMPLETED,
            ),
        )
        return [dict(row) for row in cursor.fetchall()]

    def log_push_status(self, review_entry_id: int, platform: str, status: str, message: str = None, operation_key: str = None) -> bool:
        self.execute(
            "INSERT INTO push_logs (review_entry_id, operation_key, platform, status, message) VALUES (?, ?, ?, ?, ?)",
            (review_entry_id, operation_key, platform, status, message),
        )
        return True
