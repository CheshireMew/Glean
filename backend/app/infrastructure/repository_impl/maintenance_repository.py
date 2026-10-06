from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from shared.content_contract import ARCHIVE_TABLE, EVENT_TABLE, REVIEW_TABLE

from .base_repository import BaseRepository
from ..lease_fencing import assert_current_operation_lease
from ..sqlite.editorial_retention_schema import protected_review_sql


class MaintenanceRepository(BaseRepository):
    TERMINAL_COMMAND_STATUSES = ("completed", "failed", "cancelled")
    TERMINAL_REVIEW_STATUSES = ("selected", "discarded")

    def _delete_batch(self, table: str, where: str, params: tuple, limit: int) -> int:
        cursor = self.execute(
            f"DELETE FROM {table} WHERE rowid IN (SELECT rowid FROM {table} WHERE {where} LIMIT ?)",
            (*params, limit),
        )
        return cursor.rowcount

    def prune_operational_batch(self, cutoff: str, limit: int) -> dict[str, int]:
        return {
            "processing_logs": self._delete_batch("processing_logs", "created_at < ?", (cutoff,), limit),
            "push_logs": self._delete_batch("push_logs", "pushed_at < ?", (cutoff,), limit),
            "scraper_commands": self._delete_batch(
                "scraper_runtime_commands",
                "status IN (?, ?, ?) AND updated_at < ?",
                (*self.TERMINAL_COMMAND_STATUSES, cutoff),
                limit,
            ),
            "delivery_operations": self._delete_batch(
                "delivery_operations",
                """status = 'sent' AND updated_at < ? AND NOT EXISTS (
                    SELECT 1 FROM delivery_plans p, json_each(p.operation_keys_json) k
                    WHERE p.finalized_at IS NULL AND k.value = delivery_operations.operation_key
                )""",
                (cutoff,),
                limit,
            ),
        }

    def prune_event_batch(self, cutoff: str, limit: int) -> int:
        managed_conn = self.conn is None
        conn = self.conn or self.db.connect()
        started_transaction = False
        try:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
                started_transaction = True
            rows = conn.execute(
                f"""SELECT id FROM {EVENT_TABLE} WHERE last_seen_at < ? AND NOT EXISTS (
                    SELECT 1 FROM {REVIEW_TABLE} r WHERE r.event_id={EVENT_TABLE}.id AND {protected_review_sql('r')}
                ) ORDER BY last_seen_at, id LIMIT ?""",
                (cutoff, limit),
            ).fetchall()
            event_ids = [int(row["id"] if isinstance(row, sqlite3.Row) else row[0]) for row in rows]
            if not event_ids:
                if started_transaction:
                    conn.commit()
                return 0
            placeholders = ",".join("?" for _ in event_ids)
            conn.execute(
                f"UPDATE news SET event_id = NULL, event_similarity = NULL, is_event_primary = 0 WHERE event_id IN ({placeholders})",
                tuple(event_ids),
            )
            deleted = conn.execute(
                f"DELETE FROM {EVENT_TABLE} WHERE id IN ({placeholders})",
                tuple(event_ids),
            ).rowcount
            if started_transaction:
                assert_current_operation_lease(conn)
                conn.commit()
            return deleted
        except Exception:
            if started_transaction and conn.in_transaction:
                conn.rollback()
            raise
        finally:
            if managed_conn:
                conn.close()

    def prune_content_batch(self, cutoff: str, limit: int) -> dict[str, int]:
        return {
            "news": self._delete_batch(
                "news",
                "stage = 'archived' AND event_id IS NULL AND published_at < ?",
                (cutoff,),
                limit,
            ),
            "orphan_reviews": self._delete_batch(
                REVIEW_TABLE,
                f"event_id IS NULL AND review_status IN (?, ?) AND published_at < ? AND NOT {protected_review_sql(REVIEW_TABLE)}",
                (*self.TERMINAL_REVIEW_STATUSES, cutoff),
                limit,
            ),
            "orphan_archive": self._delete_batch(
                ARCHIVE_TABLE,
                "event_id IS NULL AND source_item_id IS NULL AND archived_at < ?",
                (cutoff,),
                limit,
            ),
            "daily_reports": self._delete_batch(
                "daily_reports",
                "created_at < ?",
                (cutoff,),
                limit,
            ),
        }

    def optimize_storage(self) -> dict[str, int | bool]:
        conn = self.db.connect() if self.conn is None else self.conn
        managed_conn = self.conn is None
        try:
            conn.execute("PRAGMA optimize")
            conn.execute("INSERT INTO review_entries_fts(review_entries_fts) VALUES ('optimize')")
            checkpoint = conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
            page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
            free_pages = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
            auto_vacuum = int(conn.execute("PRAGMA auto_vacuum").fetchone()[0])
            if auto_vacuum == 2 and free_pages:
                conn.execute(f"PRAGMA incremental_vacuum({min(free_pages, 2000)})")
            checkpoint_busy = int(checkpoint[0]) if checkpoint else 0
        finally:
            if managed_conn:
                conn.close()

        vacuumed = False
        db_path = Path(self.db.db_path) if self.conn is None else None
        free_ratio = free_pages / page_count if page_count else 0.0
        if (
            db_path
            and auto_vacuum == 0
            and page_count >= 8192
            and free_ratio >= 0.25
            and db_path.exists()
            and shutil.disk_usage(db_path.parent).free >= db_path.stat().st_size * 3
        ):
            vacuum_conn = sqlite3.connect(str(db_path), timeout=30.0, isolation_level=None)
            try:
                vacuum_conn.execute("PRAGMA busy_timeout=30000")
                vacuum_conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
                vacuum_conn.execute("VACUUM")
                vacuumed = True
            finally:
                vacuum_conn.close()
        return {
            "page_count": page_count,
            "free_pages": free_pages,
            "checkpoint_busy": checkpoint_busy,
            "vacuumed": vacuumed,
        }
