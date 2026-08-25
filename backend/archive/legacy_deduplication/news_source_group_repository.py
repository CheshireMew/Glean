from __future__ import annotations

from typing import Dict, List, Optional

from shared.content_contract import DUPLICATE_STAGE, INCOMING_STAGE
from .base_repository import BaseRepository


class NewsSourceGroupRepository(BaseRepository):
    def _build_source_pool_filters(
        self,
        alias: str,
        source_site: Optional[str],
        keyword: Optional[str],
        type_filter: str,
    ) -> tuple[str, List[object]]:
        where_parts = [f"{alias}.type = ?", f"{alias}.stage IN (?, ?)"]
        params: List[object] = [type_filter, INCOMING_STAGE, DUPLICATE_STAGE]

        if source_site:
            where_parts.append(f"{alias}.source_site = ?")
            params.append(source_site)
        if keyword:
            term = f"%{keyword}%"
            where_parts.append(f"({alias}.title LIKE ? OR {alias}.content LIKE ?)")
            params.extend([term, term])

        return " AND ".join(where_parts), params

    def get_source_groups(
        self,
        page: int = 1,
        limit: int = 20,
        source_site: Optional[str] = None,
        keyword: Optional[str] = None,
        type_filter: str = "news",
    ) -> Dict:
        try:
            offset = (page - 1) * limit
            master_where, master_params = self._build_source_pool_filters("m", source_site, keyword, type_filter)
            duplicate_where, duplicate_params = self._build_source_pool_filters("d", source_site, keyword, type_filter)

            total_cursor = self.execute(
                f"SELECT COUNT(*) as total FROM news m WHERE {master_where} AND m.duplicate_of IS NULL",
                tuple(master_params),
            )
            total = total_cursor.fetchone()["total"]

            grouped_cursor = self.execute(
                f"""
                SELECT COUNT(*) as total
                FROM news m
                WHERE {master_where} AND m.duplicate_of IS NULL
                  AND EXISTS (
                      SELECT 1 FROM news d
                      WHERE d.duplicate_of = m.id AND {duplicate_where}
                  )
                """,
                tuple(master_params + duplicate_params),
            )
            grouped_total = grouped_cursor.fetchone()["total"]

            masters_cursor = self.execute(
                f"""
                SELECT m.*
                FROM news m
                WHERE {master_where} AND m.duplicate_of IS NULL
                ORDER BY m.published_at DESC
                LIMIT ? OFFSET ?
                """,
                tuple(master_params + [limit, offset]),
            )
            masters = [dict(row) for row in masters_cursor.fetchall()]
            if not masters:
                return {
                    "results": [],
                    "total": total,
                    "page": page,
                    "limit": limit,
                    "summary": {"groups": grouped_total, "independent": max(total - grouped_total, 0)},
                }

            master_ids = [master["id"] for master in masters]
            placeholders = ",".join(["?" for _ in master_ids])
            duplicates_cursor = self.execute(
                f"""
                SELECT d.*
                FROM news d
                WHERE {duplicate_where}
                  AND d.duplicate_of IN ({placeholders})
                ORDER BY d.published_at DESC
                """,
                tuple(duplicate_params + master_ids),
            )
            duplicates_by_master: Dict[int, List[Dict]] = {}
            for row in duplicates_cursor.fetchall():
                item = dict(row)
                duplicates_by_master.setdefault(item["duplicate_of"], []).append(item)

            results = []
            for master in masters:
                duplicates = duplicates_by_master.get(master["id"], [])
                results.append(
                    {
                        "master": master,
                        "duplicates": duplicates,
                        "type": "group" if duplicates else "independent",
                    }
                )

            return {
                "results": results,
                "total": total,
                "page": page,
                "limit": limit,
                "summary": {"groups": grouped_total, "independent": max(total - grouped_total, 0)},
            }
        except Exception as exc:
            print(f"Get source groups failed: {exc}")
            return {"results": [], "total": 0, "page": page, "limit": limit, "summary": {"groups": 0, "independent": 0}}
