from __future__ import annotations

import json
from typing import Dict

from shared.content_contract import EVENT_SOURCE_TABLE, REVIEW_STATUS_SELECTED, REVIEW_TABLE
from .base_repository import BaseRepository
from .public_visibility import published_entry_sql


class ReviewPublicRepository(BaseRepository):
    def get_public_revision(self, content_kind: str, profile_slug: str) -> str:
        days = 3 if content_kind == "news" else 7
        row = self.execute(
            f"""
            SELECT p.revision,
                   COUNT(r.id) AS visible_count,
                   COALESCE(SUM(r.id), 0) AS visible_sum,
                   COALESCE(MAX(r.id), 0) AS visible_max
            FROM public_content_revisions p
            LEFT JOIN {REVIEW_TABLE} r
              ON r.content_type = p.content_type
             AND r.profile_slug = ?
             AND r.review_status = ?
             AND {published_entry_sql()}
             AND r.published_at >= datetime('now', ?)
            WHERE p.content_type = ?
            GROUP BY p.revision
            """,
            (
                profile_slug,
                REVIEW_STATUS_SELECTED,
                f"-{days} days",
                content_kind,
            ),
        ).fetchone()
        if not row:
            return f"{content_kind}:0:0:0:0"
        return (
            f"{content_kind}:{int(row['revision'])}:{int(row['visible_count'])}:"
            f"{int(row['visible_sum'])}:{int(row['visible_max'])}"
        )

    def _hydrate(self, rows) -> list[Dict]:
        items = [dict(row) for row in rows]
        event_ids = list({int(item["event_id"]) for item in items if item.get("event_id")})
        sources_by_event: Dict[int, list[Dict]] = {event_id: [] for event_id in event_ids}
        if event_ids:
            placeholders = ",".join("?" for _ in event_ids)
            sources = self.execute(
                f"""
                SELECT es.event_id, n.id, n.title, n.source_site, n.source_url, n.published_at, es.is_primary
                FROM {EVENT_SOURCE_TABLE} es JOIN news n ON n.id = es.news_id
                WHERE es.event_id IN ({placeholders})
                ORDER BY es.event_id, es.is_primary DESC, n.published_at ASC
                """,
                tuple(event_ids),
            ).fetchall()
            for source in sources:
                source_item = dict(source)
                sources_by_event[int(source_item.pop("event_id"))].append(source_item)
        hydrated = []
        for item in items:
            try:
                item["citations"] = json.loads(item.pop("enrichment_citations", "[]") or "[]")
            except Exception:
                item["citations"] = []
            item["sources"] = sources_by_event.get(int(item["event_id"]), []) if item.get("event_id") else []
            hydrated.append(item)
        return hydrated

    def list_public_entries(
        self,
        content_kind: str,
        profile_slug: str,
        limit: int = 20,
        offset: int = 0,
        cursor: tuple[str, int] | None = None,
    ) -> Dict:
        days = 3 if content_kind == "news" else 7
        count_cursor = self.execute(
            f"""
            SELECT COUNT(*) as total FROM {REVIEW_TABLE} r
            WHERE content_type = ? AND profile_slug = ? AND review_status = ? AND {published_entry_sql()}
              AND published_at >= datetime('now', ?)
            """,
            (content_kind, profile_slug, REVIEW_STATUS_SELECTED, f"-{days} days"),
        )
        total = count_cursor.fetchone()["total"]
        cursor_clause = ""
        cursor_params: list[object] = []
        if cursor:
            cursor_clause = "AND (r.published_at < ? OR (r.published_at = ? AND r.id < ?))"
            cursor_params.extend([cursor[0], cursor[0], cursor[1]])
        result_cursor = self.execute(
            f"""
            SELECT r.id, r.event_id, r.title, r.source_url, r.published_at, r.source_site,
                   r.review_category, r.review_reason, r.review_summary, r.review_score,
                   r.enriched_summary, r.enriched_impact, r.enriched_background, r.enrichment_citations,
                   COALESCE(e.source_count, 1) AS source_count
            FROM {REVIEW_TABLE} r LEFT JOIN content_events e ON e.id = r.event_id
            WHERE r.content_type = ? AND r.profile_slug = ? AND r.review_status = ? AND {published_entry_sql()}
              AND r.published_at >= datetime('now', ?)
              {cursor_clause}
            ORDER BY r.published_at DESC, r.id DESC LIMIT ? OFFSET ?
            """,
            tuple([content_kind, profile_slug, REVIEW_STATUS_SELECTED, f"-{days} days", *cursor_params, limit, 0 if cursor else offset]),
        )
        items = self._hydrate(result_cursor.fetchall())
        next_cursor = None
        if len(items) == limit:
            last = items[-1]
            next_cursor = (last["published_at"], last["id"])
        return {"items": items, "total": total, "limit": limit, "offset": offset, "next_cursor_data": next_cursor}

    def search_public_entries(self, query_text: str, content_kind: str, profile_slugs: Dict[str, str], limit: int = 20, offset: int = 0) -> Dict:
        use_fts = len(query_text) >= 3
        search_term = f'"{query_text.replace(chr(34), chr(34) * 2)}"' if use_fts else f"%{query_text}%"
        params = [REVIEW_STATUS_SELECTED]
        where_parts = ["r.review_status = ?", published_entry_sql()]

        if content_kind == "news":
            where_parts.append("r.content_type = 'news'")
            where_parts.append("r.profile_slug = ?")
            params.append(profile_slugs["news"])
            where_parts.append("r.published_at >= datetime('now', '-3 days')")
        elif content_kind == "article":
            where_parts.append("r.content_type = 'article'")
            where_parts.append("r.profile_slug = ?")
            params.append(profile_slugs["article"])
            where_parts.append("r.published_at >= datetime('now', '-7 days')")
        else:
            kind_clauses = []
            if "news" in profile_slugs:
                kind_clauses.append("(r.content_type = 'news' AND r.profile_slug = ? AND r.published_at >= datetime('now', '-3 days'))")
                params.append(profile_slugs["news"])
            if "article" in profile_slugs:
                kind_clauses.append("(r.content_type = 'article' AND r.profile_slug = ? AND r.published_at >= datetime('now', '-7 days'))")
                params.append(profile_slugs["article"])
            where_parts.append(f"({' OR '.join(kind_clauses)})")

        if use_fts:
            where_parts.append(
                "r.id IN (SELECT rowid FROM review_entries_fts WHERE review_entries_fts MATCH ?)"
            )
            params.append(search_term)
        else:
            where_parts.append("(r.title LIKE ? OR r.content LIKE ? OR r.review_summary LIKE ? OR r.enriched_summary LIKE ?)")
            params.extend([search_term] * 4)
        where_clause = " AND ".join(where_parts)

        count_cursor = self.execute(
            f"SELECT COUNT(*) as total FROM {REVIEW_TABLE} r WHERE {where_clause}",
            tuple(params),
        )
        total = count_cursor.fetchone()["total"]
        cursor = self.execute(
            f"""
            SELECT r.id, r.event_id, r.title, r.content, r.source_url, r.published_at, r.source_site, r.content_type,
                   r.review_summary, r.review_score, r.enriched_summary, r.enriched_impact, r.enriched_background,
                   r.enrichment_citations, COALESCE(e.source_count, 1) AS source_count
            FROM {REVIEW_TABLE} r
            LEFT JOIN content_events e ON e.id = r.event_id
            WHERE {where_clause}
            ORDER BY r.published_at DESC LIMIT ? OFFSET ?
            """,
            tuple(params + [limit, offset]),
        )
        return {"items": self._hydrate(cursor.fetchall()), "total": total, "limit": limit, "offset": offset, "query": query_text}
