from __future__ import annotations

from typing import Dict, List, Optional

from .base_repository import BaseRepository


class DailyReportRepository(BaseRepository):
    def save_report(
        self,
        publication_key: str,
        date: str,
        report_type: str,
        title: str,
        content: str,
        news_count: int,
        *,
        profile_slug: str | None = None,
        publication_id: int | None = None,
        draft_id: int | None = None,
    ) -> int:
        self.execute(
            """
            INSERT INTO daily_reports (
                publication_key, date, type, title, content, news_count,
                profile_slug, publication_id, draft_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(publication_key) DO NOTHING
            """,
            (publication_key, date, report_type, title, content, news_count, profile_slug, publication_id, draft_id),
        )
        row = self.execute(
            "SELECT id, date, type, title, content, news_count FROM daily_reports WHERE publication_key = ?",
            (publication_key,),
        ).fetchone()
        if not row:
            raise RuntimeError("日报写入失败")
        expected = (date, report_type, title, content, news_count)
        actual = (row["date"], row["type"], row["title"], row["content"], row["news_count"])
        if actual != expected:
            raise ValueError("日报发布键已被不同内容使用")
        return int(row["id"])

    def save_report_items(self, report_id: int, entries: List[Dict]) -> None:
        for position, entry in enumerate(entries, start=1):
            self.execute(
                """
                INSERT OR IGNORE INTO daily_report_items (
                    report_id, review_entry_id, event_id, position, section, ranking_score, source_count,
                    title, source_url, source_site, published_at, content_type, review_summary,
                    enriched_summary, enriched_impact, enriched_background, enrichment_citations
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    entry["id"],
                    entry.get("event_id"),
                    position,
                    entry.get("digest_section") or "其他",
                    entry.get("ranking_score") or 0,
                    entry.get("source_count") or 1,
                    entry.get("title") or "无标题",
                    entry.get("source_url") or "",
                    entry.get("source_site"),
                    entry.get("published_at"),
                    entry.get("content_type") or "news",
                    entry.get("review_summary"),
                    entry.get("enriched_summary"),
                    entry.get("enriched_impact"),
                    entry.get("enriched_background"),
                    entry.get("enrichment_citations") or "[]",
                ),
            )

    def list_reports(
        self,
        report_type: Optional[str],
        limit: int,
        offset: int,
        query: str | None = None,
        publication_id: int | None = None,
    ) -> Dict:
        params: List[object] = []
        where_parts: List[str] = []

        if report_type:
            where_parts.append("type = ?")
            params.append(report_type)
        if query and query.strip():
            where_parts.append("(title LIKE ? OR content LIKE ?)")
            term = f"%{query.strip()}%"
            params.extend((term, term))
        if publication_id is not None:
            where_parts.append("publication_id = ?")
            params.append(publication_id)

        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        total_cursor = self.execute(f"SELECT COUNT(*) as total FROM daily_reports {where_clause}", tuple(params))
        total = total_cursor.fetchone()["total"]
        rows_cursor = self.execute(
            f"""
            SELECT id, publication_key, date, type, title, content, news_count, created_at,
                   profile_slug, publication_id, draft_id
            FROM daily_reports
            {where_clause}
            ORDER BY date DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            tuple([*params, limit, offset]),
        )
        reports = [dict(row) for row in rows_cursor.fetchall()]
        report_ids = [int(report["id"]) for report in reports]
        items_by_report = {report_id: [] for report_id in report_ids}
        if report_ids:
            placeholders = ",".join("?" for _ in report_ids)
            item_cursor = self.execute(
                """
                SELECT i.report_id, i.position, i.section, i.ranking_score, i.source_count,
                       i.review_entry_id AS id, i.title, i.source_url, i.source_site, i.published_at,
                       i.review_summary, i.enriched_summary, i.enriched_impact,
                       i.enriched_background, i.enrichment_citations, i.content_type
                FROM daily_report_items i
                WHERE i.report_id IN (""" + placeholders + ") ORDER BY i.report_id, i.position",
                tuple(report_ids),
            )
            for item_row in item_cursor.fetchall():
                item = dict(item_row)
                items_by_report[int(item.pop("report_id"))].append(item)
        for report in reports:
            report["items"] = items_by_report[int(report["id"])]
        return {
            "items": reports,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def latest_publication_report(self, publication_id: int) -> Optional[Dict]:
        row = self.execute(
            "SELECT * FROM daily_reports WHERE publication_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
            (publication_id,),
        ).fetchone()
        return dict(row) if row else None
