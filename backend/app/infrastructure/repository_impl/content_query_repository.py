from __future__ import annotations

from collections.abc import Iterator, Sequence

from shared.content_contract import (
    ARCHIVE_STATUS_BLOCKED,
    ARCHIVE_STATUS_READY,
    ARCHIVE_TABLE,
    INCOMING_STAGE,
    REVIEW_STATUS_DISCARDED,
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_SELECTED,
    REVIEW_TABLE,
)

from .base_repository import BaseRepository
from .content_scope import content_scope_plan


class ContentQueryRepository(BaseRepository):
    """Owns cross-table read models and the single content export query path."""

    def __init__(self, db_or_conn, export_connection_factory):
        super().__init__(db_or_conn)
        self._export_connection_factory = export_connection_factory

    def get_dashboard_overview(self, content_kind: str) -> dict:
        row = self.execute(
            f"""
            SELECT
                (SELECT COUNT(*) FROM news WHERE stage = ? AND type = ?) AS incoming,
                (SELECT COUNT(*) FROM {ARCHIVE_TABLE} WHERE content_type = ? AND archive_status = ?) AS archive,
                (SELECT COUNT(*) FROM {ARCHIVE_TABLE} WHERE content_type = ? AND archive_status = ?) AS blocked,
                (SELECT COUNT(*) FROM {REVIEW_TABLE} WHERE content_type = ? AND review_status = ?) AS review,
                (SELECT COUNT(*) FROM {REVIEW_TABLE} WHERE content_type = ? AND review_status = ?) AS selected,
                (SELECT COUNT(*) FROM {REVIEW_TABLE} WHERE content_type = ? AND review_status = ?) AS discarded
            """,
            (
                INCOMING_STAGE,
                content_kind,
                content_kind,
                ARCHIVE_STATUS_READY,
                content_kind,
                ARCHIVE_STATUS_BLOCKED,
                content_kind,
                REVIEW_STATUS_PENDING,
                content_kind,
                REVIEW_STATUS_SELECTED,
                content_kind,
                REVIEW_STATUS_DISCARDED,
            ),
        ).fetchone()
        if not row:
            return {"incoming": 0, "archive": 0, "blocked": 0, "review": 0, "selected": 0, "discarded": 0}
        return {key: row[key] for key in ("incoming", "archive", "blocked", "review", "selected", "discarded")}

    def stream_export(
        self,
        scope: str,
        start_date: str | None,
        end_date: str | None,
        keyword: str | None,
        source: str | None,
        content_kind: str | None,
        fields: Sequence[str],
    ) -> Iterator[dict]:
        plan = content_scope_plan(scope)
        where = [f"{plan.status_column} = ?"]
        query_params: list[object] = [plan.status]
        if plan.required_enrichment_status:
            where.append("enrichment_status = ?")
            query_params.append(plan.required_enrichment_status)
        if start_date:
            where.append("published_at >= ?")
            query_params.append(start_date)
        if end_date:
            where.append("published_at <= ?")
            query_params.append(end_date)
        if source:
            where.append("source_site = ?")
            query_params.append(source)
        if content_kind:
            where.append(f"{plan.kind_column} = ?")
            query_params.append(content_kind)
        if keyword:
            where.append("(title LIKE ? OR content LIKE ?)")
            term = f"%{keyword}%"
            query_params.extend([term, term])
        sql = f"SELECT * FROM {plan.table} WHERE {' AND '.join(where)} ORDER BY published_at DESC, id DESC"

        connection = self._export_connection_factory()
        cursor = connection.cursor()
        try:
            cursor.execute(sql, tuple(query_params))
            while rows := cursor.fetchmany(500):
                for row in rows:
                    item = dict(row)
                    yield {key: item[key] for key in fields if key in item} if fields else item
        finally:
            cursor.close()
            connection.close()
