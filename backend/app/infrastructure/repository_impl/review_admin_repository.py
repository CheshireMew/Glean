from __future__ import annotations

from typing import Dict, List, Optional

from shared.content_contract import (
    ENRICHMENT_STATUS_FAILED,
    ENRICHMENT_STATUS_PENDING,
    ENRICHMENT_STATUS_PROCESSING,
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_PROCESSING,
    REVIEW_MAX_ATTEMPTS,
    REVIEW_STATUS_SELECTED,
    REVIEW_TABLE,
)
from .base_repository import BaseRepository


class ReviewAdminRepository(BaseRepository):
    def list_entries(
        self,
        page: int = 1,
        limit: int = 50,
        source: Optional[str] = None,
        keyword: Optional[str] = None,
        content_kind: str = "news",
        review_status: Optional[str] = None,
    ) -> Dict:
        where = "content_type = ?"
        params = [content_kind]

        if review_status:
            where += " AND review_status = ?"
            params.append(review_status)
        if source:
            where += " AND source_site = ?"
            params.append(source)
        if keyword:
            where += " AND (title LIKE ? OR content LIKE ?)"
            term = f"%{keyword}%"
            params.extend([term, term])

        return self.paginated_query(
            table=REVIEW_TABLE,
            fields="id, title, content, source_site, source_url, published_at, scraped_at, archived_at, queued_at, is_marked_important, site_importance_flag, review_status, review_summary, review_reason, review_score, review_category, review_tags, delivery_status, delivered_at, content_type, source_item_id, event_id, profile_slug, COALESCE((SELECT name FROM editorial_profiles p WHERE p.slug = profile_slug), profile_slug) AS profile_name, review_error, enrichment_status, enriched_summary, enriched_impact, enriched_background, enrichment_citations, enrichment_error, COALESCE((SELECT source_count FROM content_events e WHERE e.id = event_id), 1) AS source_count",
            where=where,
            where_params=tuple(params),
            order_by="published_at DESC",
            page=page,
            limit=limit,
        )

    def list_pending_entries(self, cutoff_time: str, content_kind: str) -> List[Dict]:
        cursor = self.execute(
            f"""
            SELECT id, event_id, source_item_id, profile_slug, title, content
            FROM {REVIEW_TABLE}
            WHERE published_at >= ? AND review_status = ? AND content_type = ?
            ORDER BY published_at DESC
            """,
            (cutoff_time, REVIEW_STATUS_PENDING, content_kind),
        )
        return [dict(row) for row in cursor.fetchall()]

    def claim_pending_entries(
        self,
        cutoff_time: str,
        content_kind: str,
        claim_token: str,
        limit: int,
        max_attempts: int = REVIEW_MAX_ATTEMPTS,
        lease_seconds: int = 300,
    ) -> List[Dict]:
        rows = self.execute(
            f"""
            SELECT id FROM {REVIEW_TABLE}
            WHERE published_at >= ? AND content_type = ? AND review_attempts < ?
              AND (
                review_status = ? OR
                (review_status = ? AND review_claim_expires_at <= CURRENT_TIMESTAMP)
              )
            ORDER BY published_at ASC, id ASC
            LIMIT ?
            """,
            (cutoff_time, content_kind, max_attempts, REVIEW_STATUS_PENDING, REVIEW_STATUS_PROCESSING, limit),
        ).fetchall()
        ids = [int(row["id"]) for row in rows]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        self.execute(
            f"""
            UPDATE {REVIEW_TABLE}
            SET review_status = ?, review_claim_token = ?,
                review_claim_expires_at = datetime('now', ?)
            WHERE id IN ({placeholders})
            """,
            tuple([REVIEW_STATUS_PROCESSING, claim_token, f"+{lease_seconds} seconds", *ids]),
        )
        claimed = self.execute(
            f"""
            SELECT id, event_id, source_item_id, profile_slug, title, content
            FROM {REVIEW_TABLE}
            WHERE id IN ({placeholders}) AND review_claim_token = ?
            ORDER BY published_at ASC, id ASC
            """,
            tuple([*ids, claim_token]),
        )
        return [dict(row) for row in claimed.fetchall()]

    def count_claimable_entries(
        self,
        cutoff_time: str,
        content_kind: str,
        max_attempts: int = REVIEW_MAX_ATTEMPTS,
    ) -> int:
        row = self.execute(
            f"""
            SELECT COUNT(*) AS total FROM {REVIEW_TABLE}
            WHERE published_at >= ? AND content_type = ? AND review_attempts < ?
              AND (
                review_status = ? OR
                (review_status = ? AND review_claim_expires_at <= CURRENT_TIMESTAMP)
              )
            """,
            (cutoff_time, content_kind, max_attempts, REVIEW_STATUS_PENDING, REVIEW_STATUS_PROCESSING),
        ).fetchone()
        return int(row["total"] if row else 0)

    def renew_review_claim(self, claim_token: str, lease_seconds: int = 300) -> int:
        cursor = self.execute(
            f"""
            UPDATE {REVIEW_TABLE}
            SET review_claim_expires_at = datetime('now', ?)
            WHERE review_claim_token = ? AND review_status = ?
              AND review_claim_expires_at > CURRENT_TIMESTAMP
            """,
            (f"+{lease_seconds} seconds", claim_token, REVIEW_STATUS_PROCESSING),
        )
        return cursor.rowcount

    def release_review_claim(self, claim_token: str, error: str) -> int:
        cursor = self.execute(
            f"""
            UPDATE {REVIEW_TABLE}
            SET review_status = ?, review_error = ?, review_claim_token = NULL,
                review_claim_expires_at = NULL
            WHERE review_claim_token = ? AND review_status = ?
            """,
            (REVIEW_STATUS_PENDING, error[:1000], claim_token, REVIEW_STATUS_PROCESSING),
        )
        return cursor.rowcount

    def claim_enrichment_entries(
        self,
        content_kind: str,
        claim_token: str,
        limit: int,
        max_attempts: int = REVIEW_MAX_ATTEMPTS,
        lease_seconds: int = 300,
    ) -> List[Dict]:
        rows = self.execute(
            f"""
            SELECT id FROM {REVIEW_TABLE}
            WHERE content_type = ? AND review_status = ? AND enrichment_attempts < ?
              AND (
                enrichment_status IN (?, ?) OR
                (enrichment_status = ? AND enrichment_claim_expires_at <= CURRENT_TIMESTAMP)
              )
            ORDER BY published_at ASC, id ASC
            LIMIT ?
            """,
            (
                content_kind,
                REVIEW_STATUS_SELECTED,
                max_attempts,
                ENRICHMENT_STATUS_PENDING,
                ENRICHMENT_STATUS_FAILED,
                ENRICHMENT_STATUS_PROCESSING,
                limit,
            ),
        ).fetchall()
        ids = [int(row["id"]) for row in rows]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        self.execute(
            f"""
            UPDATE {REVIEW_TABLE}
            SET enrichment_status = ?, enrichment_claim_token = ?,
                enrichment_claim_expires_at = datetime('now', ?)
            WHERE id IN ({placeholders})
            """,
            tuple([ENRICHMENT_STATUS_PROCESSING, claim_token, f"+{lease_seconds} seconds", *ids]),
        )
        claimed = self.execute(
            f"""
            SELECT id, event_id, profile_slug, title, content
            FROM {REVIEW_TABLE}
            WHERE id IN ({placeholders}) AND enrichment_claim_token = ?
            ORDER BY published_at ASC, id ASC
            """,
            tuple([*ids, claim_token]),
        )
        return [dict(row) for row in claimed.fetchall()]

    def release_enrichment_claim(self, claim_token: str, error: str) -> int:
        cursor = self.execute(
            f"""
            UPDATE {REVIEW_TABLE}
            SET enrichment_status = ?, enrichment_error = ?, enrichment_claim_token = NULL,
                enrichment_claim_expires_at = NULL
            WHERE enrichment_claim_token = ? AND enrichment_status = ?
            """,
            (ENRICHMENT_STATUS_FAILED, error[:1000], claim_token, ENRICHMENT_STATUS_PROCESSING),
        )
        return cursor.rowcount

    def count_claimable_enrichment_entries(
        self,
        content_kind: str,
        max_attempts: int = REVIEW_MAX_ATTEMPTS,
    ) -> int:
        row = self.execute(
            f"""
            SELECT COUNT(*) AS total FROM {REVIEW_TABLE}
            WHERE content_type = ? AND review_status = ? AND enrichment_attempts < ?
              AND (
                enrichment_status IN (?, ?) OR
                (enrichment_status = ? AND enrichment_claim_expires_at <= CURRENT_TIMESTAMP)
              )
            """,
            (
                content_kind,
                REVIEW_STATUS_SELECTED,
                max_attempts,
                ENRICHMENT_STATUS_PENDING,
                ENRICHMENT_STATUS_FAILED,
                ENRICHMENT_STATUS_PROCESSING,
            ),
        ).fetchone()
        return int(row["total"] if row else 0)

    def renew_enrichment_claim(self, claim_token: str, lease_seconds: int = 300) -> int:
        cursor = self.execute(
            f"""
            UPDATE {REVIEW_TABLE}
            SET enrichment_claim_expires_at = datetime('now', ?)
            WHERE enrichment_claim_token = ? AND enrichment_status = ?
              AND enrichment_claim_expires_at > CURRENT_TIMESTAMP
            """,
            (f"+{lease_seconds} seconds", claim_token, ENRICHMENT_STATUS_PROCESSING),
        )
        return cursor.rowcount

    def get_source_url(self, entry_id: int) -> Optional[str]:
        cursor = self.execute(f"SELECT source_url FROM {REVIEW_TABLE} WHERE id = ?", (entry_id,))
        row = cursor.fetchone()
        return row["source_url"] if row else None

    def get_event_id(self, entry_id: int) -> Optional[int]:
        cursor = self.execute(f"SELECT event_id FROM {REVIEW_TABLE} WHERE id = ?", (entry_id,))
        row = cursor.fetchone()
        return int(row["event_id"]) if row and row["event_id"] is not None else None

    def list_recent_entries(
        self, start_time: str, content_kind: str, after_id: int = 0, limit: int = 1000
    ) -> List[Dict]:
        cursor = self.execute(
            f"""
            SELECT id, title, source_url
            FROM {REVIEW_TABLE}
            WHERE queued_at >= ? AND content_type = ? AND id > ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (start_time, content_kind, after_id, limit),
        )
        return [dict(row) for row in cursor.fetchall()]
