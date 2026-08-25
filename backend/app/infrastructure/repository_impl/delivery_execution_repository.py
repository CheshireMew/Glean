from __future__ import annotations

from typing import Dict, List

from shared.content_contract import (
    DELIVERY_MAX_ATTEMPTS,
    DELIVERY_OPERATION_STATUS_SENDING,
    DELIVERY_OPERATION_STATUS_SENT,
    DELIVERY_PART_STATUS_FAILED,
    DELIVERY_PART_STATUS_PENDING,
    DELIVERY_PART_STATUS_SENDING,
    DELIVERY_PART_STATUS_SENT,
    DELIVERY_PART_STATUS_UNKNOWN,
    DELIVERY_STALE_SENDING_SECONDS,
)

from ...domain.delivery import derive_delivery_operation_status
from ..lease_fencing import assert_current_operation_lease
from .base_repository import BaseRepository


class DeliveryExecutionRepository(BaseRepository):
    """Owns atomic part claiming, execution transitions and the derived operation projection."""

    def list_parts(self, operation_id: int) -> List[Dict]:
        cursor = self.execute(
            "SELECT * FROM delivery_parts WHERE operation_id = ? ORDER BY part_index",
            (operation_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def claim_next_part(
        self,
        operation_id: int,
        owner_token: str,
        max_attempts: int = DELIVERY_MAX_ATTEMPTS,
    ) -> Dict | None:
        managed_conn = self.conn is None
        conn = self.conn or self.db.connect()
        cursor = conn.cursor()
        started_transaction = False
        try:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
                started_transaction = True
            lease = cursor.execute(
                "SELECT 1 FROM delivery_operations WHERE id = ? AND owner_token = ? AND lease_expires_at > CURRENT_TIMESTAMP",
                (operation_id, owner_token),
            ).fetchone()
            if not lease:
                if started_transaction:
                    assert_current_operation_lease(conn)
                    conn.commit()
                return None
            cursor.execute(
                """
                SELECT * FROM delivery_parts
                WHERE operation_id = ? AND status IN (?, ?) AND attempt_count < ?
                ORDER BY part_index
                LIMIT 1
                """,
                (operation_id, DELIVERY_PART_STATUS_PENDING, DELIVERY_PART_STATUS_FAILED, max_attempts),
            )
            row = cursor.fetchone()
            if not row:
                if started_transaction:
                    assert_current_operation_lease(conn)
                    conn.commit()
                return None
            part = dict(row)
            cursor.execute(
                """
                UPDATE delivery_parts
                SET status = ?, attempt_count = attempt_count + 1,
                    sending_at = CURRENT_TIMESTAMP, last_error = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE operation_id = ? AND part_index = ? AND status IN (?, ?)
                """,
                (
                    DELIVERY_PART_STATUS_SENDING,
                    operation_id,
                    part["part_index"],
                    DELIVERY_PART_STATUS_PENDING,
                    DELIVERY_PART_STATUS_FAILED,
                ),
            )
            if cursor.rowcount == 0:
                if started_transaction:
                    assert_current_operation_lease(conn)
                    conn.commit()
                return None
            cursor.execute(
                "UPDATE delivery_operations SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (DELIVERY_OPERATION_STATUS_SENDING, operation_id),
            )
            if started_transaction:
                assert_current_operation_lease(conn)
                conn.commit()
            part["status"] = DELIVERY_PART_STATUS_SENDING
            part["attempt_count"] = int(part.get("attempt_count") or 0) + 1
            return part
        except Exception:
            if started_transaction or managed_conn:
                conn.rollback()
            raise
        finally:
            cursor.close()
            if managed_conn:
                conn.close()

    def mark_part_sent(self, operation_id: int, part_index: int, remote_message_id: str | None) -> Dict:
        self.execute(
            """
            UPDATE delivery_parts
            SET status = ?, remote_message_id = ?, sent_at = CURRENT_TIMESTAMP,
                last_error = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE operation_id = ? AND part_index = ? AND status = ?
            """,
            (
                DELIVERY_PART_STATUS_SENT,
                remote_message_id,
                operation_id,
                part_index,
                DELIVERY_PART_STATUS_SENDING,
            ),
        )
        return self.refresh_operation(operation_id)

    def mark_part_failed(self, operation_id: int, part_index: int, error: str) -> Dict:
        return self._mark_part(operation_id, part_index, DELIVERY_PART_STATUS_FAILED, error)

    def mark_part_unknown(self, operation_id: int, part_index: int, error: str) -> Dict:
        return self._mark_part(operation_id, part_index, DELIVERY_PART_STATUS_UNKNOWN, error)

    def _mark_part(self, operation_id: int, part_index: int, status: str, error: str) -> Dict:
        self.execute(
            """
            UPDATE delivery_parts
            SET status = ?, last_error = ?, updated_at = CURRENT_TIMESTAMP
            WHERE operation_id = ? AND part_index = ? AND status = ?
            """,
            (status, error[:1000], operation_id, part_index, DELIVERY_PART_STATUS_SENDING),
        )
        return self.refresh_operation(operation_id)

    def mark_stale_sending_unknown(
        self,
        operation_id: int,
        max_age_seconds: int = DELIVERY_STALE_SENDING_SECONDS,
    ) -> int:
        cursor = self.execute(
            """
            UPDATE delivery_parts
            SET status = ?, last_error = '发送进程中断，远端是否收到消息无法确定',
                updated_at = CURRENT_TIMESTAMP
            WHERE operation_id = ? AND status = ?
              AND sending_at <= datetime('now', ?)
            """,
            (
                DELIVERY_PART_STATUS_UNKNOWN,
                operation_id,
                DELIVERY_PART_STATUS_SENDING,
                f"-{max_age_seconds} seconds",
            ),
        )
        if cursor.rowcount:
            self.refresh_operation(operation_id)
        return cursor.rowcount

    def retry_operation(self, operation_id: int) -> Dict:
        self.execute(
            """
            UPDATE delivery_parts
            SET status = ?, attempt_count = 0,
                last_error = '用户确认后重新尝试未完成分段', updated_at = CURRENT_TIMESTAMP
            WHERE operation_id = ? AND status IN (?, ?)
            """,
            (
                DELIVERY_PART_STATUS_PENDING,
                operation_id,
                DELIVERY_PART_STATUS_UNKNOWN,
                DELIVERY_PART_STATUS_FAILED,
            ),
        )
        return self.refresh_operation(operation_id)

    def refresh_operation(self, operation_id: int) -> Dict:
        parts = self.list_parts(operation_id)
        status, sent_parts = derive_delivery_operation_status(parts)
        self.execute(
            """
            UPDATE delivery_operations
            SET status = ?, sent_parts = ?,
                last_error = (SELECT last_error FROM delivery_parts WHERE operation_id = ? AND last_error IS NOT NULL ORDER BY part_index LIMIT 1),
                completed_at = CASE WHEN ? = ? THEN CURRENT_TIMESTAMP ELSE NULL END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, sent_parts, operation_id, status, DELIVERY_OPERATION_STATUS_SENT, operation_id),
        )
        row = self.execute("SELECT * FROM delivery_operations WHERE id = ?", (operation_id,)).fetchone()
        if not row:
            raise RuntimeError("交付操作在状态刷新时不存在")
        operation = dict(row)
        import json

        try:
            operation["metadata"] = json.loads(operation.get("metadata") or "{}")
        except Exception:
            operation["metadata"] = {}
        return operation
