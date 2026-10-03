from __future__ import annotations

from typing import Dict, Optional

from shared.content_contract import EVENT_SOURCE_TABLE, EVENT_TABLE, REVIEW_TABLE

from .base_repository import BaseRepository
from .public_visibility import published_entry_sql


class EventIntelligenceRepository(BaseRepository):
    def list_selected_event_ids(
        self,
        page: int,
        limit: int,
        content_kind: str | None = None,
        updated_after: str | None = None,
    ) -> Dict:
        where = ["r.review_status = 'selected'"]
        params: list[object] = []
        if content_kind:
            where.append("e.content_type = ?")
            params.append(content_kind)
        if updated_after:
            where.append(
                "MAX(datetime(e.updated_at), datetime(COALESCE(r.editorial_updated_at, r.queued_at)), "
                "datetime(COALESCE((SELECT MAX(u.updated_at) FROM event_updates u WHERE u.event_id = e.id), e.updated_at)), "
                "datetime(COALESCE((SELECT MAX(f.updated_at) FROM event_key_facts f WHERE f.event_id = e.id), e.updated_at)), "
                "datetime(COALESCE((SELECT MAX(er.updated_at) FROM event_relations er WHERE er.event_id = e.id OR er.related_event_id = e.id), e.updated_at))) > datetime(?)"
            )
            params.append(updated_after)
        where_sql = " AND ".join(where)
        total = self.execute(
            f"SELECT COUNT(DISTINCT e.id) AS total FROM {EVENT_TABLE} e JOIN {REVIEW_TABLE} r ON r.event_id = e.id WHERE {where_sql}",
            tuple(params),
        ).fetchone()["total"]
        rows = self.execute(
            f"""
            SELECT e.id, MAX(datetime(e.updated_at),
                   MAX(datetime(COALESCE(r.editorial_updated_at, r.queued_at))),
                   datetime(COALESCE((SELECT MAX(u.updated_at) FROM event_updates u WHERE u.event_id = e.id), e.updated_at)),
                   datetime(COALESCE((SELECT MAX(f.updated_at) FROM event_key_facts f WHERE f.event_id = e.id), e.updated_at)),
                   datetime(COALESCE((SELECT MAX(er.updated_at) FROM event_relations er WHERE er.event_id = e.id OR er.related_event_id = e.id), e.updated_at))) AS changed_at
            FROM {EVENT_TABLE} e JOIN {REVIEW_TABLE} r ON r.event_id = e.id
            WHERE {where_sql}
            GROUP BY e.id ORDER BY changed_at DESC, e.id DESC LIMIT ? OFFSET ?
            """,
            (*params, limit, (page - 1) * limit),
        ).fetchall()
        return {"ids": [int(row["id"]) for row in rows], "total": int(total), "page": page, "limit": limit}

    def delta(self, since: str, limit: int) -> Dict:
        event_page = self.list_selected_event_ids(1, limit, None, since)
        corrections = [
            dict(row) for row in self.execute(
                "SELECT * FROM publication_corrections WHERE datetime(created_at) > datetime(?) OR datetime(published_at) > datetime(?) ORDER BY created_at LIMIT ?",
                (since, since, limit),
            ).fetchall()
        ]
        entities = [dict(row) for row in self.execute("SELECT * FROM entities WHERE datetime(updated_at) > datetime(?) ORDER BY updated_at LIMIT ?", (since, limit)).fetchall()]
        narratives = [dict(row) for row in self.execute("SELECT * FROM narratives WHERE datetime(updated_at) > datetime(?) ORDER BY updated_at LIMIT ?", (since, limit)).fetchall()]
        return {
            "event_ids": event_page["ids"],
            "event_total": event_page["total"],
            "corrections": corrections,
            "entities": entities,
            "narratives": narratives,
        }
    def get_detail(self, event_id: int, public_only: bool = False) -> Optional[Dict]:
        event_row = self.execute(f"SELECT * FROM {EVENT_TABLE} WHERE id = ?", (event_id,)).fetchone()
        if not event_row:
            return None
        event = dict(event_row)
        source_rows = self.execute(
            f"""
            SELECT n.id, n.title, n.content, n.source_site, n.source_url, n.author,
                   n.published_at, n.scraped_at, es.similarity, es.is_primary,
                   es.source_role, es.evidence_group, es.origin_news_id,
                   es.independence_score, es.verification_status, es.evidence_notes
            FROM {EVENT_SOURCE_TABLE} es
            JOIN news n ON n.id = es.news_id
            WHERE es.event_id = ?
            ORDER BY es.is_primary DESC, n.published_at ASC
            """,
            (event_id,),
        ).fetchall()
        sources = [dict(row) for row in source_rows]
        independent_groups = {
            source.get("evidence_group") or f"source:{source['id']}"
            for source in sources
            if float(source.get("independence_score") or 0) > 0
        }
        update_where = "event_id = ? AND is_public = 1" if public_only else "event_id = ?"
        updates = [
            dict(row)
            for row in self.execute(
                f"SELECT * FROM event_updates WHERE {update_where} ORDER BY occurred_at ASC, id ASC",
                (event_id,),
            ).fetchall()
        ]
        fact_visibility = "AND f.is_public = 1" if public_only else ""
        facts = [
            dict(row)
            for row in self.execute(
                f"""
                SELECT f.*, n.title AS source_title, n.source_site, n.source_url
                FROM event_key_facts f
                LEFT JOIN news n ON n.id = f.source_news_id
                WHERE f.event_id = ? {fact_visibility}
                ORDER BY f.verification_status = 'verified' DESC, f.id ASC
                """,
                (event_id,),
            ).fetchall()
        ]
        relation_visibility = "AND er.is_public = 1" if public_only else ""
        related_public = (
            f"AND EXISTS (SELECT 1 FROM {REVIEW_TABLE} rr WHERE rr.event_id = related.id "
            f"AND rr.review_status = 'selected' AND {published_entry_sql('rr')})"
            if public_only
            else ""
        )
        relations = [
            dict(row)
            for row in self.execute(
                f"""
                SELECT er.id, er.event_id, er.related_event_id, er.relation_type,
                       er.notes, er.is_public, er.actor, er.created_at, er.updated_at,
                       CASE WHEN er.event_id = ? THEN 'outgoing' ELSE 'incoming' END AS direction,
                       related.id AS related_id, related.title AS related_title,
                       related.content_type AS related_content_type,
                       related.last_seen_at AS related_last_seen_at
                FROM event_relations er
                JOIN {EVENT_TABLE} related ON related.id = CASE
                    WHEN er.event_id = ? THEN er.related_event_id ELSE er.event_id END
                WHERE (er.event_id = ? OR er.related_event_id = ?)
                  {relation_visibility} {related_public}
                ORDER BY related.last_seen_at DESC, er.id DESC
                """,
                (event_id, event_id, event_id, event_id),
            ).fetchall()
        ]
        entities = [
            dict(row)
            for row in self.execute(
                """
                SELECT e.id, e.entity_type, e.slug, e.name, e.symbol, e.description,
                       ee.role, ee.confidence, ee.source
                FROM event_entities ee JOIN entities e ON e.id = ee.entity_id
                WHERE ee.event_id = ? ORDER BY ee.role, e.name
                """,
                (event_id,),
            ).fetchall()
        ]
        narratives = [
            dict(row)
            for row in self.execute(
                """
                SELECT n.id, n.slug, n.name, n.description, en.confidence, en.source
                FROM event_narratives en JOIN narratives n ON n.id = en.narrative_id
                WHERE en.event_id = ? AND n.enabled = 1 ORDER BY en.confidence DESC, n.name
                """,
                (event_id,),
            ).fetchall()
        ]
        review_where = "event_id = ?"
        if public_only:
            review_where += f" AND review_status = 'selected' AND {published_entry_sql(REVIEW_TABLE)}"
        reviews = [
            dict(row)
            for row in self.execute(
                f"""
                SELECT id, profile_slug, review_status, delivery_status, review_summary,
                       review_reason, review_score, review_category, review_tags,
                       enriched_summary, enriched_impact, enriched_background,
                       enrichment_citations, editorial_version
                FROM {REVIEW_TABLE} WHERE {review_where}
                ORDER BY review_score DESC, id DESC
                """,
                (event_id,),
            ).fetchall()
        ]
        correction_visibility = "AND published_at IS NOT NULL" if public_only else ""
        corrections = [
            dict(row)
            for row in self.execute(
                f"""
                SELECT id, report_id, review_entry_id, event_id, correction_type,
                       message, actor, published_at, created_at
                FROM publication_corrections
                WHERE (event_id = ? OR review_entry_id IN (
                    SELECT id FROM review_entries WHERE event_id = ?
                )) {correction_visibility}
                ORDER BY created_at DESC, id DESC
                """,
                (event_id, event_id),
            ).fetchall()
        ]
        return {
            "event": event,
            "sources": sources,
            "independent_source_count": len(independent_groups),
            "updates": updates,
            "facts": facts,
            "relations": relations,
            "entities": entities,
            "narratives": narratives,
            "reviews": reviews,
            "corrections": corrections,
        }

    def update_source_evidence(self, event_id: int, news_id: int, values: Dict) -> bool:
        allowed = {
            "source_role",
            "evidence_group",
            "origin_news_id",
            "independence_score",
            "verification_status",
            "evidence_notes",
        }
        changes = {key: value for key, value in values.items() if key in allowed}
        if not changes:
            return False
        assignments = [f"{key} = ?" for key in changes]
        cursor = self.execute(
            f"UPDATE {EVENT_SOURCE_TABLE} SET {', '.join(assignments)} WHERE event_id = ? AND news_id = ?",
            tuple([*changes.values(), event_id, news_id]),
        )
        if cursor.rowcount > 0:
            self.execute(f"UPDATE {EVENT_TABLE} SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (event_id,))
        return cursor.rowcount > 0

    def add_update(self, event_id: int, values: Dict, actor: str) -> int:
        cursor = self.execute(
            """
            INSERT INTO event_updates(
                event_id, update_type, title, summary, occurred_at,
                source_news_id, is_public, actor
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                values.get("update_type", "development"),
                values["title"],
                values.get("summary", ""),
                values["occurred_at"],
                values.get("source_news_id"),
                values.get("is_public", True),
                actor,
            ),
        )
        return int(cursor.lastrowid)

    def update_event_update(self, update_id: int, values: Dict, actor: str) -> bool:
        allowed = {"update_type", "title", "summary", "occurred_at", "source_news_id", "is_public"}
        changes = {key: value for key, value in values.items() if key in allowed}
        if not changes:
            return False
        assignments = [f"{key} = ?" for key in changes]
        assignments.extend(["actor = ?", "updated_at = CURRENT_TIMESTAMP"])
        cursor = self.execute(
            f"UPDATE event_updates SET {', '.join(assignments)} WHERE id = ?",
            tuple([*changes.values(), actor, update_id]),
        )
        return cursor.rowcount > 0

    def add_fact(self, event_id: int, values: Dict, actor: str) -> int:
        cursor = self.execute(
            """
            INSERT INTO event_key_facts(
                event_id, fact_text, source_news_id, confidence,
                verification_status, is_public, actor
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                values["fact_text"],
                values.get("source_news_id"),
                values.get("confidence", 1),
                values.get("verification_status", "unverified"),
                values.get("is_public", True),
                actor,
            ),
        )
        self.execute(f"UPDATE {EVENT_TABLE} SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (event_id,))
        return int(cursor.lastrowid)

    def get_fact(self, fact_id: int) -> Optional[Dict]:
        row = self.execute(
            "SELECT * FROM event_key_facts WHERE id = ?", (fact_id,)
        ).fetchone()
        return dict(row) if row else None

    def update_fact(self, fact_id: int, values: Dict, actor: str) -> bool:
        allowed = {
            "fact_text", "source_news_id", "confidence", "verification_status", "is_public"
        }
        changes = {key: value for key, value in values.items() if key in allowed}
        if not changes:
            return False
        assignments = [f"{key} = ?" for key in changes]
        assignments.extend(["actor = ?", "updated_at = CURRENT_TIMESTAMP"])
        cursor = self.execute(
            f"UPDATE event_key_facts SET {', '.join(assignments)} WHERE id = ?",
            tuple([*changes.values(), actor, fact_id]),
        )
        if cursor.rowcount > 0:
            fact = self.get_fact(fact_id)
            if fact:
                self.execute(
                    f"UPDATE {EVENT_TABLE} SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (int(fact["event_id"]),),
                )
        return cursor.rowcount > 0

    def add_relation(self, event_id: int, values: Dict, actor: str) -> int:
        self.execute(
            """
            INSERT INTO event_relations(
                event_id, related_event_id, relation_type, notes, is_public, actor
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id, related_event_id, relation_type) DO UPDATE SET
                notes = excluded.notes, is_public = excluded.is_public,
                actor = excluded.actor, updated_at = CURRENT_TIMESTAMP
            """,
            (
                event_id,
                values["related_event_id"],
                values.get("relation_type", "related"),
                values.get("notes", ""),
                values.get("is_public", True),
                actor,
            ),
        )
        row = self.execute(
            """
            SELECT id FROM event_relations
            WHERE event_id = ? AND related_event_id = ? AND relation_type = ?
            """,
            (
                event_id,
                values["related_event_id"],
                values.get("relation_type", "related"),
            ),
        ).fetchone()
        self.execute(f"UPDATE {EVENT_TABLE} SET updated_at = CURRENT_TIMESTAMP WHERE id IN (?, ?)", (
            event_id, values["related_event_id"]
        ))
        return int(row["id"])
