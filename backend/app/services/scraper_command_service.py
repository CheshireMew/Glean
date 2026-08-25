from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from logging import getLogger
from typing import Dict

from ..core.exceptions import ConflictError, NotFoundError, ServiceUnavailableError
from ..core.runtime_keys import WORKER_READY_STATUSES

logger = getLogger("uvicorn")


class ScraperCommandService:
    def __init__(
        self,
        scraper_command_repository,
        scraper_runs,
        runtime_state,
        transaction,
        expected_worker_version,
    ):
        self._scraper_command_repository = scraper_command_repository
        self._scraper_runs = scraper_runs
        self._runtime_state = runtime_state
        self._transaction = transaction
        self._expected_worker_version = expected_worker_version
        self.worker_id: str | None = None

    async def request_run(self, name: str, items: int) -> Dict:
        with self._transaction() as tx_repos:
            worker = tx_repos.runtime_leases.get("worker")
            if (
                not worker
                or not worker.get("active")
                or worker.get("owner_version") != self._expected_worker_version
                or worker.get("runtime_status") not in WORKER_READY_STATUSES
            ):
                raise ServiceUnavailableError("后台 Worker 未运行，暂时不能接受爬虫任务")
            self._runtime_state.ensure_runtime_initialized()
            self._runtime_state.require_scraper(name)
            state = self._runtime_state.get_scraper_state(name)
            if state.get("status") in {"queued", "running"} or tx_repos.scraper_commands.has_pending_command(name, "run"):
                raise ConflictError(f"爬虫 {name} 已在排队或运行")
            command_id = tx_repos.scraper_commands.enqueue_command(name, "run", {"items": items})
            self._runtime_state.set_scraper_state(
                name,
                {"status": "queued", "queued_at": datetime.now(timezone.utc).isoformat(), "items_scraped": 0},
            )
            self._runtime_state.append_log(name, f"Run requested with limit {items}")
            logger.info(f"Queued run request for {name}")
            return {"status": "accepted", "command_id": command_id, "message": f"Scraper {name} queued"}

    async def request_stop(self, name: str) -> Dict:
        with self._transaction() as tx_repos:
            self._runtime_state.ensure_runtime_initialized()
            self._runtime_state.require_scraper(name)
            state = self._runtime_state.get_scraper_state(name)
            if tx_repos.scraper_commands.has_pending_command(name, "stop"):
                raise ConflictError(f"爬虫 {name} 已有停止命令")
            if state.get("status") not in {"queued", "running"} and not tx_repos.scraper_commands.has_pending_command(name, "run"):
                raise ConflictError("爬虫当前未运行")
            command_id = tx_repos.scraper_commands.enqueue_command(name, "stop")
            self._runtime_state.append_log(name, "Stop requested")
            logger.info(f"Queued stop request for {name}")
            return {"status": "accepted", "command_id": command_id, "message": f"Stop signal queued for {name}"}

    def get_command(self, command_id: int) -> Dict:
        command = self._scraper_command_repository().get_command(command_id)
        if not command:
            raise NotFoundError("爬虫命令不存在")
        return command

    async def command_loop(self) -> None:
        if not self.worker_id:
            raise RuntimeError("scraper command service 尚未绑定 worker")
        self._runtime_state.ensure_runtime_initialized()
        logger.info("Starting Scraper Command Loop")
        while True:
            try:
                command = self._scraper_command_repository().claim_next_command(
                    self.worker_id,
                    allow_run=self._scraper_runs.available_launch_slots() > 0,
                )
                if not command:
                    await asyncio.sleep(1)
                    continue
                await self._handle_command(command)
            except Exception as exc:
                logger.error(f"Scraper command loop error: {exc}", exc_info=True)
                await asyncio.sleep(1)

    async def _handle_command(self, command: Dict) -> None:
        scraper_name = command["scraper_name"]
        command_id = command["id"]
        command_type = command["command_type"]
        try:
            with self._transaction() as tx_repos:
                if command_type == "run":
                    if not self._scraper_runs.is_running(scraper_name):
                        items = int(
                            command.get("payload", {}).get("items")
                            or self._runtime_state.get_scraper_config(scraper_name).get("limit", 5)
                        )
                        launched = self._scraper_runs.launch_scraper(scraper_name, items)
                        if not launched:
                            tx_repos.scraper_commands.fail_command(command_id, "Scraper state could not be claimed")
                            return
                    tx_repos.scraper_commands.complete_command(command_id, "Run request started")
                    return

                if command_type == "stop":
                    cancelled = tx_repos.scraper_commands.cancel_pending_run_commands(scraper_name)
                    if self._scraper_runs.cancel_running_scraper(scraper_name):
                        tx_repos.scraper_commands.complete_command(command_id, "Running scraper cancelled")
                    elif cancelled:
                        self._runtime_state.set_scraper_state(
                            scraper_name,
                            {"status": "idle", "queued_at": None, "start_time": None, "last_result": "Cancelled before start"},
                        )
                        self._runtime_state.append_log(scraper_name, "Pending run cancelled")
                        tx_repos.scraper_commands.complete_command(command_id, "Pending run cancelled")
                    else:
                        tx_repos.scraper_commands.complete_command(command_id, "Scraper already idle")
                    return

                tx_repos.scraper_commands.fail_command(command_id, f"Unknown command: {command_type}")
        except Exception as exc:
            with self._transaction() as tx_repos:
                tx_repos.scraper_commands.fail_command(command_id, str(exc))
            raise

    def prepare_worker(self, worker_id: str) -> Dict:
        self.worker_id = worker_id
        with self._transaction() as tx_repos:
            recovered_commands = tx_repos.scraper_commands.recover_expired_commands()
            recovered_states = tx_repos.scraper_state.recover_interrupted_states()
        logger.info(
            "Worker recovery completed: commands=%s states=%s",
            recovered_commands,
            recovered_states,
        )
        return {"recovered_commands": recovered_commands, "recovered_states": recovered_states}
