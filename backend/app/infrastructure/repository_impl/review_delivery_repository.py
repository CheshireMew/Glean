from __future__ import annotations

from typing import Dict, List

from shared.content_contract import ENRICHMENT_STATUS_COMPLETED, REVIEW_STATUS_SELECTED, REVIEW_TABLE
from .base_repository import BaseRepository
from .content_scope import CONTENT_SCOPE_PLANS, content_scope_plan


class ReviewDeliveryRepository(BaseRepository):
    OUTPUT_SCOPES = frozenset(CONTENT_SCOPE_PLANS)

    def get_ranked_entries(self, start_time: str, content_kind: str, profile_slug: str) -> List[Dict]:
        cursor = self.execute(
            f"""
            SELECT r.id, r.event_id, r.title, r.source_url, r.source_site, r.published_at,
                   r.review_reason, r.review_summary, r.review_score, r.review_category, r.review_status,
                   r.enriched_summary, r.enriched_impact, r.enriched_background, r.enrichment_citations,
                   COALESCE(e.source_count, 1) AS source_count
            FROM {REVIEW_TABLE} r
            LEFT JOIN content_events e ON e.id = r.event_id
            WHERE r.published_at >= ? AND r.content_type = ? AND r.profile_slug = ?
              AND r.review_status = ? AND r.enrichment_status = ?
            ORDER BY COALESCE(r.review_score, 0) DESC, r.published_at DESC
            """,
            (start_time, content_kind, profile_slug, REVIEW_STATUS_SELECTED, ENRICHMENT_STATUS_COMPLETED),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_entries_by_ids(self, entry_ids: List[int]) -> List[Dict]:
        if not entry_ids:
            return []
        placeholders = ",".join(["?" for _ in entry_ids])
        cursor = self.execute(
            f"""
            SELECT id, title, source_url, content, content_type, enriched_summary, enriched_impact
            FROM {REVIEW_TABLE}
            WHERE id IN ({placeholders}) AND review_status = ?
            """,
            tuple([*entry_ids, REVIEW_STATUS_SELECTED]),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_entries_by_refs(self, refs: List[Dict]) -> List[Dict]:
        normalized = [
            {"scope": str(ref.get("scope") or ""), "id": int(ref.get("id"))}
            for ref in refs
        ]
        if any(ref["scope"] not in self.OUTPUT_SCOPES for ref in normalized):
            raise ValueError("输出列表包含未知内容来源")
        grouped: Dict[str, List[int]] = {}
        for ref in normalized:
            grouped.setdefault(ref["scope"], []).append(ref["id"])

        resolved: Dict[tuple[str, int], Dict] = {}
        for scope, raw_ids in grouped.items():
            plan = content_scope_plan(scope)
            ids = list(dict.fromkeys(raw_ids))
            placeholders = ",".join("?" for _ in ids)
            enrichment_clause = " AND enrichment_status = ?" if plan.required_enrichment_status else ""
            if plan.record_kind == "incoming":
                rows = self.execute(
                    f"""
                    SELECT id, title, source_url, source_site, content, type AS content_type,
                           published_at, NULL AS review_summary, NULL AS enriched_summary,
                           NULL AS enriched_impact, NULL AS enriched_background, '[]' AS enrichment_citations
                    FROM {plan.table} WHERE id IN ({placeholders}) AND {plan.status_column} = ?
                    """,
                    tuple([*ids, plan.status]),
                ).fetchall()
            elif plan.record_kind == "archive":
                rows = self.execute(
                    f"""
                    SELECT id, title, source_url, source_site, content, content_type, published_at,
                           NULL AS review_summary, NULL AS enriched_summary, NULL AS enriched_impact,
                           NULL AS enriched_background, '[]' AS enrichment_citations
                    FROM {plan.table} WHERE id IN ({placeholders}) AND {plan.status_column} = ?
                    """,
                    tuple([*ids, plan.status]),
                ).fetchall()
            else:
                rows = self.execute(
                    f"""
                    SELECT id, title, source_url, source_site, content, content_type, published_at,
                           review_summary, enriched_summary, enriched_impact, enriched_background,
                           enrichment_citations
                    FROM {plan.table} WHERE id IN ({placeholders}) AND {plan.status_column} = ? {enrichment_clause}
                    """,
                    tuple(
                        [*ids, plan.status]
                        + ([plan.required_enrichment_status] if plan.required_enrichment_status else [])
                    ),
                ).fetchall()
            for row in rows:
                item = dict(row)
                item["output_ref"] = {"scope": scope, "id": int(item["id"])}
                resolved[(scope, int(item["id"]))] = item
        return [resolved[(ref["scope"], ref["id"])] for ref in normalized if (ref["scope"], ref["id"]) in resolved]
