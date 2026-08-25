from __future__ import annotations

import json
from datetime import datetime
from typing import Dict

from shared.content_contract import (
    SCRAPER_COMMAND_STATUS_PENDING,
    SCRAPER_COMMAND_TYPE_RUN,
    SCRAPER_RUNTIME_STATUS_ERROR,
    SCRAPER_RUNTIME_STATUS_IDLE,
    SCRAPER_RUNTIME_STATUS_QUEUED,
    SCRAPER_RUNTIME_STATUS_RUNNING,
)

from .base_repository import BaseRepository


class ScraperStateRepository(BaseRepository):
    def ensure_state(self, scraper_name: str) -> None:
        self.execute(
            """
            INSERT INTO scraper_runtime_state (scraper_name, status, logs, updated_at)
            VALUES (?, ?, '[]', CURRENT_TIMESTAMP)
            ON CONFLICT(scraper_name) DO NOTHING
            """,
            (scraper_name, SCRAPER_RUNTIME_STATUS_IDLE),
        )

    def get_state(self, scraper_name: str) -> Dict:
        cursor = self.execute(
            """
            SELECT scraper_name, status, queued_at, start_time, last_run, last_result,
                   last_error, items_scraped, logs, run_id, worker_id, heartbeat_at, updated_at
            FROM scraper_runtime_state
            WHERE scraper_name = ?
            """,
            (scraper_name,),
        )
        row = cursor.fetchone()
        return self._normalize_state(dict(row) if row else {"scraper_name": scraper_name})

    def list_states(self) -> Dict[str, Dict]:
        cursor = self.execute(
            """
            SELECT scraper_name, status, queued_at, start_time, last_run, last_result,
                   last_error, items_scraped, logs, run_id, worker_id, heartbeat_at, updated_at
            FROM scraper_runtime_state
            """
        )
        return {row["scraper_name"]: self._normalize_state(dict(row)) for row in cursor.fetchall()}

    def update_state(self, scraper_name: str, payload: Dict) -> Dict:
        current = self.get_state(scraper_name)
        state = {**current, **payload, "scraper_name": scraper_name}
        logs = state.get("logs", [])
        state["logs"] = logs if isinstance(logs, list) else []
        self.execute(
            """
            INSERT INTO scraper_runtime_state (
                scraper_name, status, queued_at, start_time, last_run, last_result,
                last_error, items_scraped, logs, run_id, worker_id, heartbeat_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(scraper_name) DO UPDATE SET
                status = excluded.status,
                queued_at = excluded.queued_at,
                start_time = excluded.start_time,
                last_run = excluded.last_run,
                last_result = excluded.last_result,
                last_error = excluded.last_error,
                items_scraped = excluded.items_scraped,
                logs = excluded.logs,
                run_id = excluded.run_id,
                worker_id = excluded.worker_id,
                heartbeat_at = excluded.heartbeat_at,
                updated_at = excluded.updated_at
            """,
            (
                scraper_name,
                state.get("status", SCRAPER_RUNTIME_STATUS_IDLE),
                state.get("queued_at"),
                state.get("start_time"),
                state.get("last_run"),
                state.get("last_result"),
                state.get("last_error"),
                state.get("items_scraped", 0),
                json.dumps(state["logs"], ensure_ascii=False),
                state.get("run_id"),
                state.get("worker_id"),
                state.get("heartbeat_at"),
            ),
        )
        return state

    def append_log(self, scraper_name: str, message: str) -> Dict:
        current = self.get_state(scraper_name)
        logs = current.get("logs", [])
        full_message = f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
        logs.append(full_message)
        current["logs"] = logs[-100:]
        return self.update_state(scraper_name, current)

    def append_logs(self, scraper_name: str, messages: list[str]) -> Dict:
        current = self.get_state(scraper_name)
        logs = current.get("logs", [])
        timestamp = datetime.now().strftime("%H:%M:%S")
        logs.extend(f"[{timestamp}] {message}" for message in messages if message)
        current["logs"] = logs[-100:]
        return self.update_state(scraper_name, current)

    def claim_run(self, scraper_name: str, run_id: str, worker_id: str) -> bool:
        self.ensure_state(scraper_name)
        cursor = self.execute(
            """
            UPDATE scraper_runtime_state
            SET status = ?, run_id = ?, worker_id = ?, heartbeat_at = CURRENT_TIMESTAMP,
                queued_at = NULL, start_time = CURRENT_TIMESTAMP, items_scraped = 0,
                last_error = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE scraper_name = ? AND status IN (?, ?, ?)
            """,
            (
                SCRAPER_RUNTIME_STATUS_RUNNING,
                run_id,
                worker_id,
                scraper_name,
                SCRAPER_RUNTIME_STATUS_IDLE,
                SCRAPER_RUNTIME_STATUS_ERROR,
                SCRAPER_RUNTIME_STATUS_QUEUED,
            ),
        )
        return cursor.rowcount > 0

    def heartbeat(self, scraper_name: str, run_id: str, worker_id: str) -> bool:
        cursor = self.execute(
            """
            UPDATE scraper_runtime_state
            SET heartbeat_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE scraper_name = ? AND run_id = ? AND worker_id = ? AND status = ?
            """,
            (scraper_name, run_id, worker_id, SCRAPER_RUNTIME_STATUS_RUNNING),
        )
        return cursor.rowcount > 0

    def finish_run(self, scraper_name: str, run_id: str, payload: Dict) -> bool:
        cursor = self.execute(
            """
            UPDATE scraper_runtime_state
            SET status = ?, queued_at = NULL, start_time = NULL, last_run = ?, last_result = ?,
                last_error = ?, items_scraped = ?, run_id = NULL, worker_id = NULL,
                heartbeat_at = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE scraper_name = ? AND run_id = ?
            """,
            (
                payload["status"], payload.get("last_run"), payload.get("last_result"),
                payload.get("last_error"), payload.get("items_scraped", 0), scraper_name, run_id,
            ),
        )
        return cursor.rowcount > 0

    def recover_interrupted_states(self) -> int:
        running = self.execute(
            """
            UPDATE scraper_runtime_state
            SET status = ?, queued_at = NULL, start_time = NULL,
                last_result = 'Worker interrupted',
                last_error = 'worker 在采集完成前退出；本次运行未被标记为成功',
                run_id = NULL, worker_id = NULL, heartbeat_at = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE status = ?
            """,
            (SCRAPER_RUNTIME_STATUS_ERROR, SCRAPER_RUNTIME_STATUS_RUNNING),
        ).rowcount
        abandoned_queued = self.execute(
            """
            UPDATE scraper_runtime_state
            SET status = ?, queued_at = NULL,
                last_result = 'Queue entry lost',
                last_error = '未找到对应的待处理运行命令', updated_at = CURRENT_TIMESTAMP
            WHERE status = ?
              AND NOT EXISTS (
                  SELECT 1 FROM scraper_runtime_commands c
                  WHERE c.scraper_name = scraper_runtime_state.scraper_name
                    AND c.command_type = ? AND c.status = ?
              )
            """,
            (
                SCRAPER_RUNTIME_STATUS_ERROR,
                SCRAPER_RUNTIME_STATUS_QUEUED,
                SCRAPER_COMMAND_TYPE_RUN,
                SCRAPER_COMMAND_STATUS_PENDING,
            ),
        ).rowcount
        return running + abandoned_queued

    def rename_state(self, old_name: str, new_name: str) -> None:
        self.execute(
            "UPDATE scraper_runtime_state SET scraper_name = ?, updated_at = CURRENT_TIMESTAMP WHERE scraper_name = ?",
            (new_name, old_name),
        )

    def is_active(self, scraper_name: str) -> bool:
        cursor = self.execute(
            "SELECT 1 FROM scraper_runtime_state WHERE scraper_name = ? AND status IN (?, ?)",
            (
                scraper_name,
                SCRAPER_RUNTIME_STATUS_QUEUED,
                SCRAPER_RUNTIME_STATUS_RUNNING,
            ),
        )
        return cursor.fetchone() is not None

    def delete_state(self, scraper_name: str) -> None:
        self.execute("DELETE FROM scraper_runtime_state WHERE scraper_name = ?", (scraper_name,))

    @staticmethod
    def _normalize_state(state: Dict) -> Dict:
        logs = state.get("logs")
        if isinstance(logs, str):
            try:
                state["logs"] = json.loads(logs)
            except Exception:
                state["logs"] = []
        elif not isinstance(logs, list):
            state["logs"] = []
        state.setdefault("status", SCRAPER_RUNTIME_STATUS_IDLE)
        state.setdefault("items_scraped", 0)
        state.setdefault("run_id", None)
        state.setdefault("worker_id", None)
        state.setdefault("heartbeat_at", None)
        return state
