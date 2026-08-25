from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Dict, Iterable, List

from shared.content_contract import (
    DELIVERY_OPERATION_STATUS_FAILED,
    DELIVERY_OPERATION_STATUS_NEEDS_ATTENTION,
    DELIVERY_OPERATION_STATUS_SENT,
    DELIVERY_PART_STATUS_FAILED,
    DELIVERY_PART_STATUS_SENT,
    TELEGRAM_MESSAGE_LIMIT,
)

from ..core.exceptions import BusinessError, NotFoundError, ValidationError


OPERATION_KEY_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9:._-]{7,127}")


class DeliveryOperationService:
    def __init__(self, operation_repository, execution_repository, channel_gateway, transaction):
        self._operation_repository = operation_repository
        self._execution_repository = execution_repository
        self._channel_gateway = channel_gateway
        self._transaction = transaction

    @staticmethod
    def _payload_hash(
        messages: List[str],
        entry_ids: Iterable[int],
        metadata: Dict | None = None,
        entry_refs: Iterable[Dict] | None = None,
        channel_slug: str = "telegram-default",
    ) -> str:
        payload = {
            "messages": messages,
            "entry_ids": sorted(dict.fromkeys(int(value) for value in entry_ids)),
            "metadata": metadata or {},
            "entry_refs": sorted(
                ({"scope": str(ref["scope"]), "id": int(ref["id"])} for ref in (entry_refs or [])),
                key=lambda ref: (ref["scope"], ref["id"]),
            ),
            "channel_slug": channel_slug,
        }
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def validate_operation_key(operation_key: str) -> str:
        normalized = (operation_key or "").strip()
        if not OPERATION_KEY_PATTERN.fullmatch(normalized):
            raise ValidationError("交付操作键格式无效")
        return normalized

    def prepare(
        self,
        operation_key: str,
        operation_type: str,
        content_kind: str | None,
        messages: List[str],
        entry_ids: Iterable[int],
        metadata: Dict | None = None,
        entry_refs: Iterable[Dict] | None = None,
        channel_slug: str = "telegram-default",
    ) -> Dict:
        key = self.validate_operation_key(operation_key)
        prepare_messages = getattr(self._channel_gateway, "prepare_messages", None)
        if prepare_messages:
            messages = prepare_messages(channel_slug, messages)
        if not messages:
            raise ValidationError("没有可发送的消息")
        message_limit = (
            self._channel_gateway.message_limit(channel_slug)
            if hasattr(self._channel_gateway, "message_limit")
            else TELEGRAM_MESSAGE_LIMIT
        )
        if any(len(message) > message_limit for message in messages):
            raise ValidationError(f"存在超过渠道 {message_limit} 字符限制的消息分段")
        entry_id_list = list(entry_ids)
        entry_ref_list = list(entry_refs or [])
        payload_hash = self._payload_hash(messages, entry_id_list, metadata, entry_ref_list, channel_slug)
        try:
            with self._transaction() as repos:
                return repos.delivery_operations.create_operation(
                    key, operation_type, content_kind, payload_hash, messages, entry_id_list, metadata, entry_ref_list, channel_slug
                )
        except ValueError as exc:
            raise BusinessError(str(exc)) from exc

    async def send(self, operation_key: str) -> Dict:
        key = self.validate_operation_key(operation_key)
        operation_repo = self._operation_repository()
        execution_repo = self._execution_repository()
        operation = operation_repo.get_operation(key)
        if not operation:
            raise NotFoundError("交付操作不存在")
        if operation["status"] == DELIVERY_OPERATION_STATUS_SENT:
            return self._result(operation)
        if operation["status"] == DELIVERY_OPERATION_STATUS_NEEDS_ATTENTION:
            return self._result(operation)
        owner_token = uuid.uuid4().hex
        if not operation_repo.acquire_operation_lease(operation["id"], owner_token):
            return {**self._result(operation_repo.get_operation(key)), "status": "in_progress"}
        try:
            execution_repo.mark_stale_sending_unknown(operation["id"])
            operation = operation_repo.get_operation(key)
            if operation["status"] in {DELIVERY_OPERATION_STATUS_SENT, DELIVERY_OPERATION_STATUS_NEEDS_ATTENTION}:
                return self._result(operation)
            while True:
                if not operation_repo.renew_operation_lease(operation["id"], owner_token):
                    raise BusinessError("交付任务执行权已失效，请刷新状态后重试")
                part = execution_repo.claim_next_part(operation["id"], owner_token)
                if not part:
                    return self._result(execution_repo.refresh_operation(operation["id"]))
                if operation.get("operation_type") == "analyst_subscription":
                    try:
                        payload = json.loads(part["content"])
                    except json.JSONDecodeError as exc:
                        raise BusinessError("分析师订阅交付内容不是合法 JSON") from exc
                    outcome = await self._channel_gateway.send_json_result(
                        operation.get("channel_slug") or "telegram-default", payload
                    )
                else:
                    outcome = await self._channel_gateway.send_message_result(
                        operation.get("channel_slug") or "telegram-default", part["content"]
                    )
                if outcome["status"] == DELIVERY_PART_STATUS_SENT:
                    operation = execution_repo.mark_part_sent(
                        operation["id"], part["part_index"], outcome.get("remote_message_id")
                    )
                    continue
                if outcome["status"] == DELIVERY_PART_STATUS_FAILED:
                    operation = execution_repo.mark_part_failed(operation["id"], part["part_index"], outcome["error"])
                    if operation["status"] == DELIVERY_OPERATION_STATUS_FAILED:
                        return self._result(operation)
                    continue
                operation = execution_repo.mark_part_unknown(operation["id"], part["part_index"], outcome["error"])
                return self._result(operation)
        finally:
            operation_repo.release_operation_lease(operation["id"], owner_token)

    def list_operations(self, limit: int = 50, status: str | None = None) -> List[Dict]:
        return [self._result(operation) for operation in self._operation_repository().list_operations(limit, status)]

    def get_operation(self, operation_key: str) -> Dict:
        operation = self._operation_repository().get_operation(self.validate_operation_key(operation_key))
        if not operation:
            raise NotFoundError("交付操作不存在")
        return self._result(operation)

    async def retry_operation(self, operation_key: str) -> Dict:
        key = self.validate_operation_key(operation_key)
        operation = self._operation_repository().get_operation(key)
        if not operation:
            raise NotFoundError("交付操作不存在")
        self._execution_repository().retry_operation(operation["id"])
        return await self.send(key)

    @staticmethod
    def _result(operation: Dict) -> Dict:
        return {
            "operation_key": operation["operation_key"],
            "status": operation["status"],
            "parts": operation["total_parts"],
            "sent_parts": operation["sent_parts"],
            "last_error": operation.get("last_error"),
            "needs_attention": operation["status"] == DELIVERY_OPERATION_STATUS_NEEDS_ATTENTION,
            "channel_slug": operation.get("channel_slug") or "telegram-default",
        }
