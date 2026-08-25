from __future__ import annotations

import sqlite3

from ..core.exceptions import BusinessError
from ..core.operation_context import current_operation_lease


def assert_current_operation_lease(conn: sqlite3.Connection) -> None:
    """Reject a commit when the operation executing it no longer owns its lease."""

    lease = current_operation_lease()
    if lease is None:
        return
    owned = conn.execute(
        """
        SELECT 1
        FROM runtime_leases
        WHERE name = ? AND owner_id = ?
        """,
        (lease.name, lease.owner_id),
    ).fetchone()
    if owned is None:
        raise BusinessError("内容流水线执行权已失效，已拒绝提交过期任务的结果")
