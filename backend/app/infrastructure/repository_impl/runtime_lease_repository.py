from __future__ import annotations

from typing import Dict, Optional

from .base_repository import BaseRepository


class RuntimeLeaseRepository(BaseRepository):
    def acquire(
        self,
        name: str,
        owner_id: str,
        ttl_seconds: int,
        *,
        owner_version: str | None = None,
        runtime_status: str = "ready",
        status_details: str | None = None,
    ) -> bool:
        cursor = self.execute(
            """
            INSERT INTO runtime_leases (
                name, owner_id, lease_expires_at, owner_version, runtime_status,
                status_details, updated_at
            )
            VALUES (?, ?, datetime('now', ?), ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(name) DO UPDATE SET
                owner_id = excluded.owner_id,
                lease_expires_at = excluded.lease_expires_at,
                owner_version = excluded.owner_version,
                runtime_status = excluded.runtime_status,
                status_details = excluded.status_details,
                updated_at = CURRENT_TIMESTAMP
            WHERE runtime_leases.owner_id = excluded.owner_id
               OR runtime_leases.lease_expires_at <= CURRENT_TIMESTAMP
            """,
            (
                name,
                owner_id,
                f"+{ttl_seconds} seconds",
                owner_version,
                runtime_status,
                status_details,
            ),
        )
        return cursor.rowcount > 0

    def renew(
        self,
        name: str,
        owner_id: str,
        ttl_seconds: int,
        *,
        owner_version: str | None = None,
        runtime_status: str | None = None,
        status_details: str | None = None,
    ) -> bool:
        cursor = self.execute(
            """
            UPDATE runtime_leases
            SET lease_expires_at = datetime('now', ?),
                owner_version = COALESCE(?, owner_version),
                runtime_status = COALESCE(?, runtime_status),
                status_details = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE name = ? AND owner_id = ?
            """,
            (
                f"+{ttl_seconds} seconds",
                owner_version,
                runtime_status,
                status_details,
                name,
                owner_id,
            ),
        )
        return cursor.rowcount > 0

    def update_status(
        self,
        name: str,
        owner_id: str,
        runtime_status: str,
        status_details: str | None = None,
    ) -> bool:
        cursor = self.execute(
            """
            UPDATE runtime_leases
            SET runtime_status = ?, status_details = ?, updated_at = CURRENT_TIMESTAMP
            WHERE name = ? AND owner_id = ?
            """,
            (runtime_status, status_details, name, owner_id),
        )
        return cursor.rowcount > 0

    def release(self, name: str, owner_id: str) -> bool:
        cursor = self.execute("DELETE FROM runtime_leases WHERE name = ? AND owner_id = ?", (name, owner_id))
        return cursor.rowcount > 0

    def get(self, name: str) -> Optional[Dict]:
        cursor = self.execute(
            """
            SELECT name, owner_id, lease_expires_at, owner_version, runtime_status,
                   status_details, updated_at,
                   CASE WHEN lease_expires_at > CURRENT_TIMESTAMP THEN 1 ELSE 0 END AS active
            FROM runtime_leases
            WHERE name = ?
            """,
            (name,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
