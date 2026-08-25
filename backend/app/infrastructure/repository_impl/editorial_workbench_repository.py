from __future__ import annotations

import json
from typing import Dict, Iterable, Optional

from shared.content_contract import REVIEW_TABLE

from .base_repository import BaseRepository


class EditorialWorkbenchRepository(BaseRepository):
    EDITABLE_FIELDS = (
        "title",
        "review_summary",
        "review_reason",
        "review_score",
        "review_category",
        "review_tags",
        "enriched_summary",
        "enriched_impact",
        "enriched_background",
        "enrichment_citations",
    )

    def get_entry(self, entry_id: int) -> Optional[Dict]:
        row = self.execute(f"SELECT * FROM {REVIEW_TABLE} WHERE id = ?", (entry_id,)).fetchone()
        return dict(row) if row else None

    def update_entry(self, entry_id: int, fields: Dict, actor: str, version: int) -> bool:
        changes = {key: value for key, value in fields.items() if key in self.EDITABLE_FIELDS}
        if not changes:
            return False
        assignments = [f"{field} = ?" for field in changes]
        assignments.extend(
            [
                "editorial_version = ?",
                "editorial_updated_at = CURRENT_TIMESTAMP",
                "editorial_updated_by = ?",
            ]
        )
        cursor = self.execute(
            f"UPDATE {REVIEW_TABLE} SET {', '.join(assignments)} WHERE id = ?",
            tuple([*changes.values(), version, actor, entry_id]),
        )
        return cursor.rowcount > 0

    def save_revision(
        self,
        entry: Dict,
        revision_number: int,
        actor: str,
        changed_fields: Iterable[str],
        note: str | None,
    ) -> int:
        snapshot = {field: entry.get(field) for field in self.EDITABLE_FIELDS}
        snapshot.update(
            {
                "id": entry.get("id"),
                "event_id": entry.get("event_id"),
                "profile_slug": entry.get("profile_slug"),
                "content_type": entry.get("content_type"),
                "source_site": entry.get("source_site"),
                "source_url": entry.get("source_url"),
                "published_at": entry.get("published_at"),
            }
        )
        cursor = self.execute(
            """
            INSERT INTO content_revisions(
                review_entry_id, event_id, revision_number, snapshot_json,
                changed_fields_json, change_note, actor
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry["id"],
                entry.get("event_id"),
                revision_number,
                json.dumps(snapshot, ensure_ascii=False, default=str),
                json.dumps(sorted(set(changed_fields)), ensure_ascii=False),
                note,
                actor,
            ),
        )
        return int(cursor.lastrowid)

    def list_revisions(self, entry_id: int) -> list[Dict]:
        rows = self.execute(
            """
            SELECT id, review_entry_id, event_id, revision_number, snapshot_json,
                   changed_fields_json, change_note, actor, created_at
            FROM content_revisions
            WHERE review_entry_id = ?
            ORDER BY revision_number DESC
            """,
            (entry_id,),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["snapshot"] = json.loads(item.pop("snapshot_json") or "{}")
            item["changed_fields"] = json.loads(item.pop("changed_fields_json") or "[]")
            result.append(item)
        return result

    def get_revision(self, entry_id: int, revision_number: int) -> Optional[Dict]:
        row = self.execute(
            """
            SELECT * FROM content_revisions
            WHERE review_entry_id = ? AND revision_number = ?
            """,
            (entry_id, revision_number),
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["snapshot"] = json.loads(result.pop("snapshot_json") or "{}")
        result["changed_fields"] = json.loads(result.pop("changed_fields_json") or "[]")
        return result

    def add_feedback(
        self,
        entry_id: int,
        outcome: str,
        actor: str,
        quality_score: int | None,
        changed_fields: Iterable[str],
        notes: str | None,
        invocation_id: int | None = None,
    ) -> int:
        cursor = self.execute(
            """
            INSERT INTO ai_feedback(
                invocation_id, review_entry_id, outcome, quality_score,
                changed_fields_json, notes, actor
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                invocation_id,
                entry_id,
                outcome,
                quality_score,
                json.dumps(sorted(set(changed_fields)), ensure_ascii=False),
                notes,
                actor,
            ),
        )
        return int(cursor.lastrowid)

    def list_feedback(self, entry_id: int) -> list[Dict]:
        rows = self.execute(
            "SELECT * FROM ai_feedback WHERE review_entry_id = ? ORDER BY created_at DESC, id DESC",
            (entry_id,),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["changed_fields"] = json.loads(item.pop("changed_fields_json") or "[]")
            result.append(item)
        return result

    def create_draft(
        self,
        draft_key: str,
        publication_id: int,
        content_type: str,
        title: str,
        actor: str,
    ) -> int:
        cursor = self.execute(
            """
            INSERT INTO publication_drafts(
                draft_key, publication_id, content_type, title, created_by
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (draft_key, publication_id, content_type, title, actor),
        )
        return int(cursor.lastrowid)

    def get_publication(self, publication_id: int) -> Optional[Dict]:
        row = self.execute(
            """
            SELECT p.*, e.content_type, e.enabled AS profile_enabled
            FROM profile_publications p
            JOIN editorial_profiles e ON e.slug = p.profile_slug
            WHERE p.id = ?
            """,
            (publication_id,),
        ).fetchone()
        return dict(row) if row else None

    def replace_draft_items(self, draft_id: int, items: Iterable[Dict]) -> None:
        self.execute("DELETE FROM publication_draft_items WHERE draft_id = ?", (draft_id,))
        for index, item in enumerate(items):
            requested_position = item.get("position")
            self.execute(
                """
                INSERT INTO publication_draft_items(
                    draft_id, review_entry_id, position, section, included, overrides_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    draft_id,
                    item["review_entry_id"],
                    int(index if requested_position is None else requested_position),
                    item.get("section") or "其他",
                    bool(item.get("included", True)),
                    json.dumps(item.get("overrides") or {}, ensure_ascii=False),
                ),
            )

    def get_draft(self, draft_id: int) -> Optional[Dict]:
        row = self.execute(
            """
            SELECT d.*, p.profile_slug, p.public_slug, p.display_name AS publication_name
            FROM publication_drafts d
            JOIN profile_publications p ON p.id = d.publication_id
            WHERE d.id = ?
            """,
            (draft_id,),
        ).fetchone()
        if not row:
            return None
        draft = dict(row)
        draft["items"] = self.list_draft_items(draft_id)
        return draft

    def get_draft_by_key(self, draft_key: str) -> Optional[Dict]:
        row = self.execute("SELECT id FROM publication_drafts WHERE draft_key = ?", (draft_key,)).fetchone()
        return self.get_draft(int(row["id"])) if row else None

    def list_due_drafts(self, limit: int = 100) -> list[Dict]:
        rows = self.execute(
            """
            SELECT id FROM publication_drafts
            WHERE status = 'scheduled' AND datetime(scheduled_at) <= CURRENT_TIMESTAMP
            ORDER BY datetime(scheduled_at), id LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self.get_draft(int(row["id"])) for row in rows]

    def list_draft_items(self, draft_id: int) -> list[Dict]:
        rows = self.execute(
            f"""
            SELECT di.draft_id, di.review_entry_id, di.position, di.section, di.included,
                   di.overrides_json, r.title, r.source_site, r.source_url, r.published_at,
                   r.review_summary, r.review_reason, r.review_score, r.review_category,
                   r.enriched_summary, r.enriched_impact, r.enriched_background,
                   r.enrichment_citations, r.event_id, r.profile_slug, r.content_type
            FROM publication_draft_items di
            JOIN {REVIEW_TABLE} r ON r.id = di.review_entry_id
            WHERE di.draft_id = ?
            ORDER BY di.position
            """,
            (draft_id,),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["overrides"] = json.loads(item.pop("overrides_json") or "{}")
            try:
                item["citations"] = json.loads(item.pop("enrichment_citations") or "[]")
            except (TypeError, json.JSONDecodeError):
                item["citations"] = []
            result.append(item)
        return result

    def list_drafts(self, status: str | None = None, limit: int = 100) -> list[Dict]:
        where = "WHERE d.status = ?" if status else ""
        params = (status, limit) if status else (limit,)
        rows = self.execute(
            f"""
            SELECT d.*, p.profile_slug, p.public_slug, p.display_name AS publication_name,
                   (SELECT COUNT(*) FROM publication_draft_items i WHERE i.draft_id = d.id AND i.included = 1) AS item_count
            FROM publication_drafts d
            JOIN profile_publications p ON p.id = d.publication_id
            {where}
            ORDER BY d.updated_at DESC, d.id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def update_draft(
        self,
        draft_id: int,
        *,
        title: str | None = None,
        status: str | None = None,
        scheduled_at: str | None = None,
        published_report_id: int | None = None,
    ) -> bool:
        fields: Dict[str, object] = {}
        if title is not None:
            fields["title"] = title
        if status is not None:
            fields["status"] = status
        if scheduled_at is not None or status == "draft":
            fields["scheduled_at"] = scheduled_at
        if published_report_id is not None:
            fields["published_report_id"] = published_report_id
        if not fields:
            return False
        assignments = [f"{key} = ?" for key in fields]
        assignments.append("updated_at = CURRENT_TIMESTAMP")
        result = self.execute(
            f"UPDATE publication_drafts SET {', '.join(assignments)} WHERE id = ?",
            tuple([*fields.values(), draft_id]),
        )
        return result.rowcount > 0

    def add_correction(
        self,
        correction_type: str,
        message: str,
        actor: str,
        *,
        report_id: int | None,
        review_entry_id: int | None,
        event_id: int | None,
    ) -> int:
        cursor = self.execute(
            """
            INSERT INTO publication_corrections(
                report_id, review_entry_id, event_id, correction_type, message, actor
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (report_id, review_entry_id, event_id, correction_type, message, actor),
        )
        return int(cursor.lastrowid)

    def get_correction(self, correction_id: int) -> Optional[Dict]:
        row = self.execute(
            f"""
            SELECT c.*, d.publication_id AS report_publication_id, d.title AS report_title,
                   r.profile_slug AS entry_profile_slug, r.title AS entry_title
            FROM publication_corrections c
            LEFT JOIN daily_reports d ON d.id = c.report_id
            LEFT JOIN {REVIEW_TABLE} r ON r.id = c.review_entry_id
            WHERE c.id = ?
            """,
            (correction_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_corrections(self, published: bool | None = None, limit: int = 200) -> list[Dict]:
        where = "WHERE c.published_at IS NOT NULL" if published is True else "WHERE c.published_at IS NULL" if published is False else ""
        rows = self.execute(
            f"""
            SELECT c.*, d.title AS report_title, r.title AS entry_title, e.title AS event_title
            FROM publication_corrections c
            LEFT JOIN daily_reports d ON d.id = c.report_id
            LEFT JOIN {REVIEW_TABLE} r ON r.id = c.review_entry_id
            LEFT JOIN content_events e ON e.id = c.event_id
            {where} ORDER BY c.created_at DESC, c.id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def mark_correction_published(self, correction_id: int) -> bool:
        return self.execute(
            "UPDATE publication_corrections SET published_at = CURRENT_TIMESTAMP WHERE id = ?",
            (correction_id,),
        ).rowcount > 0
