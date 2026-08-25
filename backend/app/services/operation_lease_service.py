from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, contextmanager
import os
import sqlite3
import socket
import threading
import uuid

from ..core.exceptions import BusinessError
from ..core.operation_context import bind_operation_lease


class OperationLeaseService:
    def __init__(self, runtime_lease_repository):
        self._runtime_lease_repository = runtime_lease_repository

    def _owner(self) -> str:
        return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex}"

    @staticmethod
    def _is_transient_database_lock(exc: Exception) -> bool:
        return isinstance(exc, sqlite3.OperationalError) and any(
            marker in str(exc).lower() for marker in ("locked", "busy")
        )

    @asynccontextmanager
    async def hold(self, name: str, ttl_seconds: int = 120):
        owner = self._owner()
        repo = self._runtime_lease_repository()
        if not await asyncio.to_thread(repo.acquire, name, owner, ttl_seconds):
            raise BusinessError("内容流水线正在执行，请等待当前任务完成后重试")
        lease_lost = asyncio.Event()
        holder_task = asyncio.current_task()

        async def renew_loop():
            try:
                while True:
                    await asyncio.sleep(max(0.5, ttl_seconds / 3))
                    while True:
                        try:
                            renewed = await asyncio.to_thread(
                                self._runtime_lease_repository().renew, name, owner, ttl_seconds
                            )
                            break
                        except Exception as exc:
                            if not self._is_transient_database_lock(exc):
                                raise
                            await asyncio.sleep(0.1)
                    if not renewed:
                        lease_lost.set()
                        if holder_task is not None:
                            holder_task.cancel()
                        return
            except asyncio.CancelledError:
                raise
            except Exception:
                lease_lost.set()
                if holder_task is not None:
                    holder_task.cancel()

        task = asyncio.create_task(renew_loop(), name=f"lease:{name}")
        try:
            with bind_operation_lease(name, owner):
                try:
                    yield lease_lost
                except asyncio.CancelledError as exc:
                    if lease_lost.is_set():
                        raise BusinessError("内容流水线执行权已失效，任务已停止") from exc
                    raise
                if lease_lost.is_set():
                    raise BusinessError("内容流水线执行权已失效，任务已停止")
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await asyncio.to_thread(self._runtime_lease_repository().release, name, owner)

    @contextmanager
    def hold_sync(self, name: str, ttl_seconds: int = 120):
        owner = self._owner()
        repo = self._runtime_lease_repository()
        if not repo.acquire(name, owner, ttl_seconds):
            raise BusinessError("内容流水线正在执行，请等待当前任务完成后重试")
        stop = threading.Event()
        lease_lost = threading.Event()

        def renew_loop():
            while not stop.wait(max(0.5, ttl_seconds / 3)):
                renewed = True
                while not stop.is_set():
                    try:
                        renewed = self._runtime_lease_repository().renew(name, owner, ttl_seconds)
                        break
                    except Exception as exc:
                        if not self._is_transient_database_lock(exc):
                            renewed = False
                            break
                        stop.wait(0.1)
                if stop.is_set():
                    return
                if not renewed:
                    lease_lost.set()
                    return

        task = threading.Thread(target=renew_loop, name=f"lease:{name}", daemon=True)
        task.start()
        try:
            with bind_operation_lease(name, owner):
                yield lease_lost
                if lease_lost.is_set():
                    raise BusinessError("内容流水线执行权已失效，任务已停止")
        finally:
            stop.set()
            task.join(timeout=max(1.0, ttl_seconds / 3 + 1))
            self._runtime_lease_repository().release(name, owner)

    def is_active(self, name: str) -> bool:
        lease = self._runtime_lease_repository().get(name)
        return bool(lease and lease.get("active"))
