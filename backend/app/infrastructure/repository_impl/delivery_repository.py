from __future__ import annotations

from typing import Dict, Iterable, List
import json

from shared.content_contract import (
    DELIVERY_LEASE_SECONDS,
    DELIVERY_OPERATION_STATUS_PENDING,
    DELIVERY_PART_STATUS_PENDING,
    EXPORT_SCOPE_DISCARDED,
    EXPORT_SCOPE_REVIEW,
    EXPORT_SCOPE_SELECTED,
)

from .base_repository import BaseRepository


class DeliveryOperationRepository(BaseRepository):
    """Owns delivery-operation identity, immutable plans, entry references and leases."""
    def create_operation(
        self,
        operation_key: str,
        operation_type: str,
        content_kind: str | None,
        payload_hash: str,
        messages: List[str],
        entry_ids: Iterable[int],
        metadata: Dict | None = None,
        entry_refs: Iterable[Dict] | None = None,
        channel_slug: str = "telegram-default",
    ) -> Dict:
        existing = self.get_operation(operation_key)
        if existing:
            if existing["payload_hash"] != payload_hash:
                raise ValueError("交付操作键已被不同内容使用")
            return existing
        cursor = self.execute(
            """
            INSERT OR IGNORE INTO delivery_operations (
                operation_key, operation_type, content_kind, payload_hash, metadata, status, total_parts, sent_parts, channel_slug
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                operation_key,
                operation_type,
                content_kind,
                payload_hash,
                json.dumps(metadata or {}, ensure_ascii=False),
                DELIVERY_OPERATION_STATUS_PENDING,
                len(messages),
                channel_slug,
            ),
        )
        if cursor.rowcount == 0:
            concurrent = self.get_operation(operation_key)
            if not concurrent or concurrent["payload_hash"] != payload_hash:
                raise ValueError("交付操作键已被不同内容使用")
            return concurrent
        operation_id = cursor.lastrowid
        for index, message in enumerate(messages):
            import hashlib

            self.execute(
                """
                INSERT INTO delivery_parts (operation_id, part_index, content_hash, content, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    operation_id,
                    index,
                    hashlib.sha256(message.encode("utf-8")).hexdigest(),
                    message,
                    DELIVERY_PART_STATUS_PENDING,
                ),
            )
        normalized_refs = list(
            entry_refs
            or ({"scope": EXPORT_SCOPE_SELECTED, "id": int(value)} for value in entry_ids)
        )
        seen_refs: set[str] = set()
        for ref in normalized_refs:
            normalized = {"scope": str(ref["scope"]), "id": int(ref["id"])}
            serialized_ref = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            if serialized_ref in seen_refs:
                continue
            seen_refs.add(serialized_ref)
            review_entry_id = (
                normalized["id"]
                if normalized["scope"]
                in {EXPORT_SCOPE_REVIEW, EXPORT_SCOPE_SELECTED, EXPORT_SCOPE_DISCARDED}
                else None
            )
            self.execute(
                "INSERT OR IGNORE INTO delivery_operation_entries (operation_id, entry_ref, review_entry_id) VALUES (?, ?, ?)",
                (operation_id, serialized_ref, review_entry_id),
            )
        return self.get_operation(operation_key)

    def list_operations(self, limit: int = 50, status: str | None = None) -> List[Dict]:
        where = "WHERE status = ?" if status else ""
        params: tuple = (status, limit) if status else (limit,)
        cursor = self.execute(
            f"SELECT * FROM delivery_operations {where} ORDER BY id DESC LIMIT ?",
            params,
        )
        return [self._hydrate_operation(row) for row in cursor.fetchall()]

    def acquire_operation_lease(
        self,
        operation_id: int,
        owner_token: str,
        lease_seconds: int = DELIVERY_LEASE_SECONDS,
    ) -> bool:
        cursor = self.execute(
            """
            UPDATE delivery_operations
            SET owner_token = ?, lease_expires_at = datetime('now', ?), updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND (
                owner_token IS NULL OR lease_expires_at IS NULL OR lease_expires_at <= CURRENT_TIMESTAMP OR owner_token = ?
            )
            """,
            (owner_token, f"+{lease_seconds} seconds", operation_id, owner_token),
        )
        return cursor.rowcount == 1

    def renew_operation_lease(
        self,
        operation_id: int,
        owner_token: str,
        lease_seconds: int = DELIVERY_LEASE_SECONDS,
    ) -> bool:
        cursor = self.execute(
            """
            UPDATE delivery_operations
            SET lease_expires_at = datetime('now', ?), updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND owner_token = ? AND lease_expires_at > CURRENT_TIMESTAMP
            """,
            (f"+{lease_seconds} seconds", operation_id, owner_token),
        )
        return cursor.rowcount == 1

    def release_operation_lease(self, operation_id: int, owner_token: str) -> None:
        self.execute(
            "UPDATE delivery_operations SET owner_token = NULL, lease_expires_at = NULL WHERE id = ? AND owner_token = ?",
            (operation_id, owner_token),
        )

    def get_operation(self, operation_key: str) -> Dict | None:
        cursor = self.execute("SELECT * FROM delivery_operations WHERE operation_key = ?", (operation_key,))
        row = cursor.fetchone()
        return self._hydrate_operation(row)

    def get_operation_by_id(self, operation_id: int) -> Dict | None:
        cursor = self.execute("SELECT * FROM delivery_operations WHERE id = ?", (operation_id,))
        row = cursor.fetchone()
        return self._hydrate_operation(row)

    @staticmethod
    def _hydrate_operation(row) -> Dict | None:
        if not row:
            return None
        operation = dict(row)
        try:
            operation["metadata"] = json.loads(operation.get("metadata") or "{}")
        except Exception:
            operation["metadata"] = {}
        return operation

    def entry_ids(self, operation_id: int) -> List[int]:
        cursor = self.execute(
            "SELECT review_entry_id FROM delivery_operation_entries WHERE operation_id = ? ORDER BY review_entry_id",
            (operation_id,),
        )
        return [int(row["review_entry_id"]) for row in cursor.fetchall() if row["review_entry_id"] is not None]

    def entry_refs(self, operation_id: int) -> List[Dict]:
        cursor = self.execute(
            "SELECT entry_ref FROM delivery_operation_entries WHERE operation_id = ? ORDER BY entry_ref",
            (operation_id,),
        )
        result = []
        for row in cursor.fetchall():
            try:
                result.append(json.loads(row["entry_ref"]))
            except Exception:
                continue
        return result
