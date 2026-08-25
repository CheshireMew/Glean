from __future__ import annotations

from typing import Dict

from shared.content_contract import DELIVERY_OPERATION_STATUS_SENT

from ..core.exceptions import NotFoundError


class DeliveryRetryService:
    """Dispatches retry finalization to the owner of the original operation type."""

    def __init__(self, operation_repository, delivery_operations, daily_delivery, manual_entry_delivery):
        self._operation_repository = operation_repository
        self._delivery_operations = delivery_operations
        self._daily_delivery = daily_delivery
        self._manual_entry_delivery = manual_entry_delivery

    async def retry(self, operation_key: str) -> Dict:
        operation = self._operation_repository().get_operation(operation_key)
        if not operation:
            raise NotFoundError("交付操作不存在")
        result = await self._delivery_operations.retry_operation(operation_key)
        if result["status"] != DELIVERY_OPERATION_STATUS_SENT:
            return result
        if operation["operation_type"].startswith("daily_"):
            report_id, entry_count = self._daily_delivery.finalize_success(operation_key)
            return {**result, "report_id": report_id, "count": entry_count}
        self._manual_entry_delivery.finalize_success(operation_key)
        return result
