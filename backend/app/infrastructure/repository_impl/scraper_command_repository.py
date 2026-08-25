from __future__ import annotations

import json
from typing import Dict, Optional

from shared.content_contract import (
    SCRAPER_COMMAND_STATUS_CANCELLED,
    SCRAPER_COMMAND_STATUS_COMPLETED,
    SCRAPER_COMMAND_STATUS_FAILED,
    SCRAPER_COMMAND_STATUS_PENDING,
    SCRAPER_COMMAND_STATUS_PROCESSING,
    SCRAPER_COMMAND_TYPE_RUN,
)

from .base_repository import BaseRepository
from ..lease_fencing import assert_current_operation_lease


class ScraperCommandRepository(BaseRepository):
    def get_command(self, command_id: int) -> Optional[Dict]:
        row = self.execute(
            "SELECT id, scraper_name, command_type, status, result_message, attempt_count, created_at, updated_at FROM scraper_runtime_commands WHERE id = ?",
            (command_id,),
        ).fetchone()
        return dict(row) if row else None

    def enqueue_command(self, scraper_name: str, command_type: str, payload: Optional[Dict] = None) -> int:
        cursor = self.execute(
            """
            INSERT INTO scraper_runtime_commands (scraper_name, command_type, payload, status, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                scraper_name,
                command_type,
                json.dumps(payload or {}, ensure_ascii=False),
                SCRAPER_COMMAND_STATUS_PENDING,
            ),
        )
        return cursor.lastrowid

    def has_pending_command(self, scraper_name: str, command_type: str) -> bool:
        cursor = self.execute(
            """
            SELECT 1
            FROM scraper_runtime_commands
            WHERE scraper_name = ? AND command_type = ? AND status IN (?, ?)
            LIMIT 1
            """,
            (
                scraper_name,
                command_type,
                SCRAPER_COMMAND_STATUS_PENDING,
                SCRAPER_COMMAND_STATUS_PROCESSING,
            ),
        )
        return cursor.fetchone() is not None

    def claim_next_command(
        self,
        worker_id: str,
        lease_seconds: int = 30,
        *,
        allow_run: bool = True,
    ) -> Optional[Dict]:
        managed_conn = self.conn is None
        conn = self.conn or self.db.connect()
        cursor = conn.cursor()
        started_transaction = False
        try:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
                started_transaction = True
            cursor.execute(
                """
                SELECT id, scraper_name, command_type, payload, status, created_at, updated_at,
                       attempt_count
                FROM scraper_runtime_commands
                WHERE status = ? AND (? OR command_type != ?)
                ORDER BY CASE WHEN command_type = 'stop' THEN 0 ELSE 1 END, created_at ASC, id ASC
                LIMIT 1
                """,
                (SCRAPER_COMMAND_STATUS_PENDING, int(allow_run), SCRAPER_COMMAND_TYPE_RUN),
            )
            row = cursor.fetchone()
            if not row:
                if started_transaction:
                    assert_current_operation_lease(conn)
                    conn.commit()
                return None
            command = dict(row)
            try:
                command["payload"] = self._decode_payload(command.get("payload"))
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                cursor.execute(
                    """
                    UPDATE scraper_runtime_commands
                    SET status = ?, result_message = ?, attempt_count = attempt_count + 1,
                        claimed_by = NULL, lease_expires_at = NULL, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status = ?
                    """,
                    (
                        SCRAPER_COMMAND_STATUS_FAILED,
                        f"Invalid command payload: {exc}"[:1000],
                        command["id"],
                        SCRAPER_COMMAND_STATUS_PENDING,
                    ),
                )
                if started_transaction:
                    assert_current_operation_lease(conn)
                    conn.commit()
                return None
            cursor.execute(
                """
                UPDATE scraper_runtime_commands
                SET status = ?, claimed_by = ?,
                    lease_expires_at = datetime('now', ?),
                    attempt_count = attempt_count + 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = ?
                """,
                (
                    SCRAPER_COMMAND_STATUS_PROCESSING,
                    worker_id,
                    f"+{lease_seconds} seconds",
                    command["id"],
                    SCRAPER_COMMAND_STATUS_PENDING,
                ),
            )
            if cursor.rowcount == 0:
                if started_transaction:
                    assert_current_operation_lease(conn)
                    conn.commit()
                return None
            if started_transaction:
                assert_current_operation_lease(conn)
                conn.commit()
            command["status"] = SCRAPER_COMMAND_STATUS_PROCESSING
            command["claimed_by"] = worker_id
            return command
        except Exception:
            if started_transaction or managed_conn:
                conn.rollback()
            raise
        finally:
            cursor.close()
            if managed_conn:
                conn.close()

    def complete_command(self, command_id: int, result_message: Optional[str] = None) -> None:
        self._set_command_status(command_id, SCRAPER_COMMAND_STATUS_COMPLETED, result_message)

    def fail_command(self, command_id: int, result_message: Optional[str] = None) -> None:
        self._set_command_status(command_id, SCRAPER_COMMAND_STATUS_FAILED, result_message)

    def cancel_pending_run_commands(self, scraper_name: str) -> int:
        cursor = self.execute(
            """
            UPDATE scraper_runtime_commands
            SET status = ?, result_message = 'Cancelled before execution', updated_at = CURRENT_TIMESTAMP
            WHERE scraper_name = ? AND command_type = ? AND status = ?
            """,
            (
                SCRAPER_COMMAND_STATUS_CANCELLED,
                scraper_name,
                SCRAPER_COMMAND_TYPE_RUN,
                SCRAPER_COMMAND_STATUS_PENDING,
            ),
        )
        return cursor.rowcount

    def delete_commands_for_scraper(self, scraper_name: str) -> None:
        self.execute("DELETE FROM scraper_runtime_commands WHERE scraper_name = ?", (scraper_name,))

    def recover_expired_commands(self) -> int:
        cursor = self.execute(
            """
            UPDATE scraper_runtime_commands
            SET status = ?, claimed_by = NULL, lease_expires_at = NULL,
                result_message = 'Recovered after worker interruption', updated_at = CURRENT_TIMESTAMP
            WHERE status = ? AND (lease_expires_at IS NULL OR lease_expires_at <= CURRENT_TIMESTAMP)
            """,
            (SCRAPER_COMMAND_STATUS_PENDING, SCRAPER_COMMAND_STATUS_PROCESSING),
        )
        return cursor.rowcount

    def rename_commands_for_scraper(self, old_name: str, new_name: str) -> None:
        self.execute(
            "UPDATE scraper_runtime_commands SET scraper_name = ?, updated_at = CURRENT_TIMESTAMP WHERE scraper_name = ?",
            (new_name, old_name),
        )

    def _set_command_status(self, command_id: int, status: str, result_message: Optional[str]) -> None:
        self.execute(
            """
            UPDATE scraper_runtime_commands
            SET status = ?, result_message = ?, claimed_by = NULL, lease_expires_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, result_message, command_id),
        )

    @staticmethod
    def _decode_payload(payload: Optional[str]) -> Dict:
        if not payload:
            return {}
        decoded = json.loads(payload)
        if not isinstance(decoded, dict):
            raise ValueError("爬虫命令 payload 必须是 JSON 对象")
        return decoded
