from __future__ import annotations

from typing import Dict, List, Optional

from shared.content_contract import EVENT_SOURCE_TABLE, EVENT_TABLE

from ...core.time import utc_cutoff
from .base_repository import BaseRepository


class EventQueryRepository(BaseRepository):
    """Explicit cross-table event read model; it never writes aggregate state."""

    def list_recent_candidates(self, content_kind: str, time_window_hours: int) -> List[Dict]:
        params: List[object] = [content_kind]
        where = "content_type = ?"
        if time_window_hours > 0:
            where += " AND last_seen_at >= ?"
            params.append(utc_cutoff(time_window_hours))
        cursor = self.execute(
            f"SELECT id, canonical_news_id, title, content_type, published_at, source_count FROM {EVENT_TABLE} WHERE {where} ORDER BY last_seen_at DESC LIMIT 2000",
            tuple(params),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_event(self, event_id: int) -> Optional[Dict]:
        row = self.execute(f"SELECT * FROM {EVENT_TABLE} WHERE id = ?", (event_id,)).fetchone()
        return dict(row) if row else None

    def get_sources(self, event_id: int) -> List[Dict]:
        cursor = self.execute(
            f"""
            SELECT n.id, n.title, n.content, n.source_site, n.source_url, n.published_at,
                   n.scraped_at, n.is_marked_important, es.similarity, es.is_primary,
                   es.source_role, es.evidence_group, es.origin_news_id,
                   es.independence_score, es.verification_status, es.evidence_notes
            FROM {EVENT_SOURCE_TABLE} es
            JOIN news n ON n.id = es.news_id
            WHERE es.event_id = ?
            ORDER BY es.is_primary DESC, n.published_at ASC
            """,
            (event_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def list_groups(
        self,
        page: int,
        limit: int,
        source_site: Optional[str],
        keyword: Optional[str],
        content_kind: str,
    ) -> Dict:
        where = ["e.content_type = ?"]
        params: List[object] = [content_kind]
        if source_site:
            where.append(
                f"EXISTS (SELECT 1 FROM {EVENT_SOURCE_TABLE} fs JOIN news sn ON sn.id = fs.news_id WHERE fs.event_id = e.id AND sn.source_site = ?)"
            )
            params.append(source_site)
        if keyword:
            where.append("(e.title LIKE ? OR e.content LIKE ?)")
            term = f"%{keyword}%"
            params.extend([term, term])
        where_sql = " AND ".join(where)
        count = self.execute(
            f"SELECT COUNT(*) AS total FROM {EVENT_TABLE} e WHERE {where_sql}", tuple(params)
        ).fetchone()["total"]
        grouped = self.execute(
            f"SELECT COUNT(*) AS total FROM {EVENT_TABLE} e WHERE {where_sql} AND e.source_count > 1",
            tuple(params),
        ).fetchone()["total"]
        cursor = self.execute(
            f"""
            SELECT e.* FROM {EVENT_TABLE} e
            WHERE {where_sql}
            ORDER BY e.published_at DESC
            LIMIT ? OFFSET ?
            """,
            tuple([*params, limit, (page - 1) * limit]),
        )
        events = [dict(row) for row in cursor.fetchall()]
        event_ids = [int(event["id"]) for event in events]
        sources_by_event = {event_id: [] for event_id in event_ids}
        if event_ids:
            placeholders = ",".join("?" for _ in event_ids)
            source_rows = self.execute(
                f"""
                SELECT es.event_id, n.id, n.title, n.content, n.source_site, n.source_url,
                       n.published_at, es.similarity, es.is_primary, es.source_role,
                       es.evidence_group, es.origin_news_id, es.independence_score,
                       es.verification_status, es.evidence_notes
                FROM {EVENT_SOURCE_TABLE} es JOIN news n ON n.id = es.news_id
                WHERE es.event_id IN ({placeholders})
                ORDER BY es.event_id, es.is_primary DESC, n.published_at ASC
                """,
                tuple(event_ids),
            ).fetchall()
            for source_row in source_rows:
                source = dict(source_row)
                sources_by_event[int(source.pop("event_id"))].append(source)
        results = []
        for event in events:
            sources = sources_by_event.get(int(event["id"]), [])
            primary = next(
                (source for source in sources if source["is_primary"]),
                sources[0] if sources else event,
            )
            alternatives = [source for source in sources if not source["is_primary"]]
            results.append(
                {
                    "event": event,
                    "primary": primary,
                    "sources": sources,
                    "alternatives": alternatives,
                    "type": "event",
                }
            )
        return {
            "results": results,
            "total": count,
            "page": page,
            "limit": limit,
            "summary": {"multi_source": grouped, "single_source": max(count - grouped, 0)},
        }
