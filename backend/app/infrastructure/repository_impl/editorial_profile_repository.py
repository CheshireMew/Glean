from __future__ import annotations

from typing import Dict, List, Optional

from .base_repository import BaseRepository


class EditorialProfileRepository(BaseRepository):
    def list_profiles(self, content_kind: str | None = None, enabled_only: bool = False) -> List[Dict]:
        where = []
        params: list[object] = []
        if content_kind:
            where.append("content_type = ?")
            params.append(content_kind)
        if enabled_only:
            where.append("enabled = 1")
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        cursor = self.execute(
            f"SELECT * FROM editorial_profiles {where_sql} ORDER BY content_type, is_default DESC, name",
            tuple(params),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_default(self, content_kind: str) -> Optional[Dict]:
        cursor = self.execute(
            "SELECT * FROM editorial_profiles WHERE content_type = ? AND enabled = 1 AND is_default = 1 LIMIT 1",
            (content_kind,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get(self, slug: str) -> Optional[Dict]:
        cursor = self.execute("SELECT * FROM editorial_profiles WHERE slug = ?", (slug,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def save(self, payload: Dict) -> Dict:
        if payload.get("is_default"):
            self.execute("UPDATE editorial_profiles SET is_default = 0 WHERE content_type = ?", (payload["content_type"],))
        self.execute(
            """
            INSERT INTO editorial_profiles (
                slug, name, content_type, review_prompt, enrichment_prompt, min_score,
                max_items, max_per_category, max_per_source, enabled, is_default
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                name = excluded.name,
                content_type = excluded.content_type,
                review_prompt = excluded.review_prompt,
                enrichment_prompt = excluded.enrichment_prompt,
                min_score = excluded.min_score,
                max_items = excluded.max_items,
                max_per_category = excluded.max_per_category,
                max_per_source = excluded.max_per_source,
                enabled = excluded.enabled,
                is_default = excluded.is_default,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                payload["slug"], payload["name"], payload["content_type"],
                payload.get("review_prompt") or "", payload.get("enrichment_prompt") or "",
                int(payload.get("min_score") or 5), int(payload.get("max_items") or 12),
                int(payload.get("max_per_category") or 4), int(payload.get("max_per_source") or 4),
                int(bool(payload.get("enabled", True))),
                int(bool(payload.get("is_default", False))),
            ),
        )
        return self.get(payload["slug"])
