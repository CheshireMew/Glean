from __future__ import annotations

import sqlite3
from typing import Dict, List, Optional

from shared.content_contract import (
    DELIVERY_STATUS_SENT,
    ENRICHMENT_STATUS_COMPLETED,
    ENRICHMENT_STATUS_FAILED,
    ENRICHMENT_STATUS_NOT_APPLICABLE,
    ENRICHMENT_STATUS_PENDING,
    REVIEW_STATUS_DISCARDED,
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_SELECTED,
    REVIEW_TABLE,
)
from .base_repository import BaseRepository


class ReviewRepository(BaseRepository):
    def requeue_entry(self, entry_id: int) -> bool:
        cursor = self.execute(
                f"""
                UPDATE {REVIEW_TABLE}
                SET review_status = ?, review_reason = NULL, review_summary = NULL,
                    review_score = NULL, review_category = NULL, review_tags = NULL,
                    review_error = NULL, review_attempts = 0, enrichment_status = ?,
                    review_claim_token = NULL, review_claim_expires_at = NULL,
                    enrichment_attempts = 0, enrichment_claim_token = NULL, enrichment_claim_expires_at = NULL,
                    enriched_summary = NULL, enriched_impact = NULL, enriched_background = NULL,
                    enrichment_citations = '[]', enrichment_error = NULL, enriched_at = NULL
                WHERE id = ?
                """,
                (REVIEW_STATUS_PENDING, ENRICHMENT_STATUS_PENDING, entry_id),
        )
        return cursor.rowcount > 0

    def requeue_reviewed_entries(self, content_kind: str = "news") -> int:
        cursor = self.execute(
                f"""
                UPDATE {REVIEW_TABLE}
                SET review_status = ?, review_reason = NULL, review_summary = NULL,
                    review_score = NULL, review_category = NULL, review_tags = NULL,
                    review_error = NULL, review_attempts = 0, enrichment_status = ?,
                    review_claim_token = NULL, review_claim_expires_at = NULL,
                    enrichment_attempts = 0, enrichment_claim_token = NULL, enrichment_claim_expires_at = NULL,
                    enriched_summary = NULL, enriched_impact = NULL, enriched_background = NULL,
                    enrichment_citations = '[]', enrichment_error = NULL, enriched_at = NULL
                WHERE content_type = ? AND review_status IN (?, ?)
                """,
                (
                    REVIEW_STATUS_PENDING,
                    ENRICHMENT_STATUS_PENDING,
                    content_kind,
                    REVIEW_STATUS_SELECTED,
                    REVIEW_STATUS_DISCARDED,
                ),
        )
        return cursor.rowcount

    def clear_review_results(self, content_kind: str = "news") -> int:
        return self.requeue_reviewed_entries(content_kind)

    def save_review_result(
        self,
        entry_id: int,
        review_status: str,
        review_reason: str,
        review_score: Optional[int] = None,
        review_category: Optional[str] = None,
        review_summary: Optional[str] = None,
        review_tags: Optional[str] = None,
        claim_token: Optional[str] = None,
    ) -> bool:
        claim_clause = " AND review_claim_token = ?" if claim_token else ""
        params = [
            review_status, review_reason, review_score, review_category, review_summary, review_tags,
            ENRICHMENT_STATUS_PENDING
            if review_status == REVIEW_STATUS_SELECTED
            else ENRICHMENT_STATUS_NOT_APPLICABLE,
            entry_id,
        ]
        if claim_token:
            params.append(claim_token)
        cursor = self.execute(
            f"""
            UPDATE {REVIEW_TABLE}
            SET review_status = ?, review_reason = ?, review_score = ?, review_category = ?,
                review_summary = ?, review_tags = ?, review_error = NULL,
                enrichment_status = ?, review_claim_token = NULL, review_claim_expires_at = NULL
            WHERE id = ?{claim_clause}
            """,
            tuple(params),
        )
        return cursor.rowcount > 0

    def save_review_error(self, entry_id: int, error: str, claim_token: Optional[str] = None) -> bool:
        claim_clause = " AND review_claim_token = ?" if claim_token else ""
        params = [REVIEW_STATUS_PENDING, error[:1000], entry_id]
        if claim_token:
            params.append(claim_token)
        cursor = self.execute(
            f"""
            UPDATE {REVIEW_TABLE}
            SET review_status = ?, review_error = ?, review_attempts = COALESCE(review_attempts, 0) + 1,
                review_claim_token = NULL, review_claim_expires_at = NULL
            WHERE id = ?{claim_clause}
            """,
            tuple(params),
        )
        return cursor.rowcount > 0

    def save_enrichment_result(
        self, entry_id: int, result: Dict, claim_token: Optional[str] = None
    ) -> bool:
        import json

        claim_clause = " AND enrichment_claim_token = ?" if claim_token else ""
        params = [
            result.get("summary") or "",
            result.get("why_it_matters") or "",
            result.get("background") or "",
            json.dumps(result.get("citations") or [], ensure_ascii=False),
            entry_id,
        ]
        if claim_token:
            params.append(claim_token)
        cursor = self.execute(
            f"""
            UPDATE {REVIEW_TABLE}
            SET enrichment_status = ?, enriched_summary = ?, enriched_impact = ?,
                enriched_background = ?, enrichment_citations = ?, enrichment_error = NULL,
                enriched_at = CURRENT_TIMESTAMP, enrichment_claim_token = NULL,
                enrichment_claim_expires_at = NULL
            WHERE id = ?{claim_clause}
            """,
            tuple([ENRICHMENT_STATUS_COMPLETED, *params]),
        )
        return cursor.rowcount > 0

    def save_enrichment_error(self, entry_id: int, error: str, claim_token: Optional[str] = None) -> bool:
        claim_clause = " AND enrichment_claim_token = ?" if claim_token else ""
        params = [error[:1000], entry_id]
        if claim_token:
            params.append(claim_token)
        cursor = self.execute(
            f"""
            UPDATE {REVIEW_TABLE}
            SET enrichment_status = ?, enrichment_error = ?,
                enrichment_attempts = COALESCE(enrichment_attempts, 0) + 1,
                enrichment_claim_token = NULL, enrichment_claim_expires_at = NULL
            WHERE id = ?{claim_clause}
            """,
            tuple([ENRICHMENT_STATUS_FAILED, *params]),
        )
        return cursor.rowcount > 0

    def delete_by_source_url(self, source_url: str) -> bool:
        cursor = self.execute(f"DELETE FROM {REVIEW_TABLE} WHERE source_url = ?", (source_url,))
        return cursor.rowcount > 0

    def delete_entry(self, entry_id: int) -> bool:
        cursor = self.execute(f"DELETE FROM {REVIEW_TABLE} WHERE id = ?", (entry_id,))
        return cursor.rowcount > 0

    def delete_by_event(self, event_id: int) -> int:
        return self.execute(f"DELETE FROM {REVIEW_TABLE} WHERE event_id = ?", (event_id,)).rowcount

    def replace_event_source(self, event_id: int, replacement: Dict) -> int:
        return self.execute(
            f"""
            UPDATE {REVIEW_TABLE}
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

    def create_pending_entry(self, archive_row: Dict, queued_at: str, profile_slug: str) -> bool:
        try:
            self.execute(
                f"""
                INSERT INTO {REVIEW_TABLE} (
                    title, content, source_site, source_url, published_at, scraped_at, archived_at,
                    queued_at, is_marked_important, site_importance_flag, review_status, content_type,
                    source_item_id, event_id, profile_slug
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    archive_row["title"],
                    archive_row["content"],
                    archive_row["source_site"],
                    archive_row["source_url"],
                    archive_row["published_at"],
                    archive_row["scraped_at"],
                    archive_row["archived_at"],
                    queued_at,
                    archive_row["is_marked_important"],
                    archive_row["site_importance_flag"],
                    REVIEW_STATUS_PENDING,
                    archive_row["content_type"],
                    archive_row["source_item_id"],
                    archive_row["event_id"],
                    profile_slug,
                ),
            )
            return True
        except sqlite3.IntegrityError:
            return False

    def mark_delivered(self, entry_ids: List[int]) -> None:
        if not entry_ids:
            return
        placeholders = ",".join(["?" for _ in entry_ids])
        self.execute(
            f"UPDATE {REVIEW_TABLE} SET delivery_status = ?, delivered_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders})",
            tuple([DELIVERY_STATUS_SENT, *entry_ids]),
        )
