from __future__ import annotations

from typing import Dict

from shared.content_contract import DELIVERY_OPERATION_STATUS_SENT

from ..core.exceptions import NotFoundError, ValidationError


class DeliveryRetryService:
    """Dispatches retry finalization to the owner of the original operation type."""

    def __init__(self, operation_repository, delivery_operations, daily_delivery, manual_entry_delivery,
                 publication_workflow=None, analyst_subscriptions=None):
        self._operation_repository = operation_repository
        self._delivery_operations = delivery_operations
        self._daily_delivery = daily_delivery
        self._manual_entry_delivery = manual_entry_delivery
        self._publication_workflow = publication_workflow
        self._analyst_subscriptions = analyst_subscriptions

    async def retry(self, operation_key: str) -> Dict:
        operation = self._operation_repository().get_operation(operation_key)
        if not operation:
            raise NotFoundError("交付操作不存在")
        operation_type = operation['operation_type']
        if operation_type not in {'daily_auto', 'daily_manual', 'entry_auto', 'entry_manual',
                                  'publication_draft', 'publication_correction', 'publication_realtime',
                                  'event_alert', 'analyst_subscription'}:
            raise ValidationError("交付类型没有登记恢复所有者")
        result = await self._delivery_operations.retry_operation(operation_key)
        if result["status"] != DELIVERY_OPERATION_STATUS_SENT:
            return result
        if operation_type.startswith("daily_"):
            report_id, entry_count = self._daily_delivery.finalize_success(operation_key)
            return {**result, "report_id": report_id, "count": entry_count}
        if operation_type == 'analyst_subscription':
            self._analyst_subscriptions.finalize_success(operation_key)
        elif operation_type in {'publication_draft', 'publication_correction', 'publication_realtime', 'event_alert'}:
            business = self._publication_workflow.finalize_success(operation_key)
            result = {**result, 'business': business}
        else:
            self._manual_entry_delivery.finalize_success(operation_key)
        return result
