from __future__ import annotations

from typing import Dict, List, Optional

from shared.content_contract import INCOMING_STAGE
from .base_repository import BaseRepository


class NewsAdminRepository(BaseRepository):
    def get_incoming_news(
        self,
        page: int = 1,
        limit: int = 50,
        source_site: Optional[str] = None,
        keyword: Optional[str] = None,
        type_filter: str = "news",
    ) -> Dict:
        offset = (page - 1) * limit
        query = """
            SELECT n.*
            FROM news n
            WHERE n.stage = ? AND n.type = ?
        """
        params: List[object] = [INCOMING_STAGE, type_filter]

        if source_site:
            query += " AND n.source_site = ?"
            params.append(source_site)
        if keyword:
            query += " AND (n.title LIKE ? OR n.content LIKE ?)"
            term = f"%{keyword}%"
            params.extend([term, term])

        data_query = query + " ORDER BY n.published_at DESC LIMIT ? OFFSET ?"
        cursor = self.execute(data_query, tuple(params + [limit, offset]))
        rows = cursor.fetchall()
        count_cursor = self.execute(f"SELECT count(*) as total FROM ({query})", tuple(params))
        total = count_cursor.fetchone()["total"]
        return {"results": [dict(row) for row in rows], "total": total, "page": page, "limit": limit}

    def get_stats(self, type_filter: str = "news") -> Dict:
        cursor = self.execute(
            "SELECT source_site, COUNT(*) as count FROM news WHERE type = ? AND stage = ? GROUP BY source_site",
            (type_filter, INCOMING_STAGE),
        )
        rows = cursor.fetchall()
        return {"stats": [{"source": row["source_site"], "count": row["count"]} for row in rows]}
