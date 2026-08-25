from __future__ import annotations

from typing import Dict, List
import uuid

from shared.content_contract import (
    CONTENT_KIND_ARTICLE,
    CONTENT_KIND_NEWS,
    DELIVERY_OPERATION_STATUS_SENT,
    DELIVERY_STATUS_PENDING,
    DELIVERY_STATUS_SENT,
    EXPORT_SCOPE_SELECTED,
    PUSH_LOG_STATUS_SUCCESS,
)

from ..core.exceptions import ValidationError


class AutomaticEntryDeliveryService:
    """Owns the automatic selected-entry delivery workflow."""

    def __init__(
        self,
        editorial_profile_repository,
        push_repository,
        review_repository,
        telegram_gateway,
        telegram_messages,
        delivery_operations,
    ):
        self._editorial_profile_repository = editorial_profile_repository
        self._push_repository = push_repository
        self._review_repository = review_repository
        self._telegram_gateway = telegram_gateway
        self._telegram_messages = telegram_messages
        self._delivery_operations = delivery_operations

    async def send_pending(self) -> Dict | None:
        if not self._telegram_gateway.has_bot_config():
            return None
        sent_ids: List[int] = []
        operation_results: List[Dict] = []
        for content_kind in (CONTENT_KIND_NEWS, CONTENT_KIND_ARTICLE):
            profile = self._editorial_profile_repository().get_default(content_kind)
            if not profile:
                continue
            pending_entries = self._push_repository().get_pending_review_entries(
                content_kind, profile["slug"]
            )
            for entry in pending_entries:
                key = f"auto-entry:{content_kind}:{entry['id']}"
                messages = self._telegram_messages.format_entry_parts(entry)
                self._delivery_operations.prepare(
                    key, "entry_auto", content_kind, messages, [entry["id"]]
                )
                result = await self._delivery_operations.send(key)
                operation_results.append(result)
                self._push_repository().log_push_status(
                    entry["id"],
                    "telegram",
                    PUSH_LOG_STATUS_SUCCESS
                    if result["status"] == DELIVERY_OPERATION_STATUS_SENT
                    else result["status"],
                    result.get("last_error"),
                    key,
                )
                if result["status"] == DELIVERY_OPERATION_STATUS_SENT:
                    sent_ids.append(entry["id"])
        self._review_repository().mark_delivered(sent_ids)
        return {"sent_count": len(sent_ids), "operations": operation_results}


class ManualEntryDeliveryService:
    """Owns validation, formatting and finalization of manually selected entries."""

    def __init__(
        self,
        review_delivery_repository,
        review_repository,
        operation_repository,
        telegram_messages,
        delivery_operations,
    ):
        self._review_delivery_repository = review_delivery_repository
        self._review_repository = review_repository
        self._operation_repository = operation_repository
        self._telegram_messages = telegram_messages
        self._delivery_operations = delivery_operations

    @staticmethod
    def _normalize_refs(entry_refs: List[Dict]) -> List[Dict]:
        normalized = [
            {"scope": EXPORT_SCOPE_SELECTED, "id": int(ref)}
            if isinstance(ref, int)
            else {"scope": str(ref["scope"]), "id": int(ref["id"])}
            for ref in entry_refs
        ]
        return list({(ref["scope"], ref["id"]): ref for ref in normalized}.values())

    def finalize_success(self, operation_key: str) -> None:
        operation = self._operation_repository().get_operation(operation_key)
        if not operation:
            raise ValidationError("交付操作不存在")
        self._review_repository().mark_delivered(
            self._operation_repository().entry_ids(operation["id"])
        )

    async def send(self, entry_refs: List[Dict], operation_key: str | None = None) -> Dict:
        if not entry_refs:
            raise ValidationError("请选择要发送的内容")
        try:
            requested_refs = self._normalize_refs(entry_refs)
            entries = self._review_delivery_repository().get_entries_by_refs(requested_refs)
        except (TypeError, ValueError, KeyError) as exc:
            raise ValidationError(str(exc) or "输出列表格式无效") from exc
        if not entries:
            raise ValidationError("未找到要发送的内容")
        found_refs = {
            (entry["output_ref"]["scope"], int(entry["output_ref"]["id"]))
            for entry in entries
        }
        missing_refs = [
            ref
            for ref in requested_refs
            if (str(ref["scope"]), int(ref["id"])) not in found_refs
        ]
        if missing_refs:
            raise ValidationError(f"有 {len(missing_refs)} 条内容已离开原内容池，请刷新列表后重试")
        content_kinds = {entry.get("content_type") for entry in entries}
        if len(content_kinds) != 1:
            raise ValidationError("一次发送只能包含同一种内容类型")

        messages = [
            part
            for entry in entries
            for part in self._telegram_messages.format_entry_parts(entry)
        ]
        key = operation_key or f"manual-entry:{uuid.uuid4().hex}"
        self._delivery_operations.prepare(
            key,
            "entry_manual",
            entries[0].get("content_type"),
            messages,
            [],
            entry_refs=requested_refs,
        )
        result = await self._delivery_operations.send(key)
        if result["status"] == DELIVERY_OPERATION_STATUS_SENT:
            self.finalize_success(key)
            return {
                **result,
                "sent_count": len(entries),
                "delivery_status": DELIVERY_STATUS_SENT,
            }
        return {
            **result,
            "sent_count": 0,
            "delivery_status": DELIVERY_STATUS_PENDING,
        }
