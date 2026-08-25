from __future__ import annotations

from collections.abc import Iterable, Mapping

from shared.content_contract import (
    DELIVERY_MAX_ATTEMPTS,
    DELIVERY_OPERATION_STATUS_FAILED,
    DELIVERY_OPERATION_STATUS_NEEDS_ATTENTION,
    DELIVERY_OPERATION_STATUS_PENDING,
    DELIVERY_OPERATION_STATUS_SENDING,
    DELIVERY_OPERATION_STATUS_SENT,
    DELIVERY_PART_STATUS_FAILED,
    DELIVERY_PART_STATUS_SENDING,
    DELIVERY_PART_STATUS_SENT,
    DELIVERY_PART_STATUS_UNKNOWN,
)


def derive_delivery_operation_status(
    parts: Iterable[Mapping[str, object]],
    max_attempts: int = DELIVERY_MAX_ATTEMPTS,
) -> tuple[str, int]:
    """Return the aggregate operation status and sent-part count from persisted parts."""
    rows = list(parts)
    statuses = [str(part["status"]) for part in rows]
    sent_parts = sum(status == DELIVERY_PART_STATUS_SENT for status in statuses)
    if statuses and sent_parts == len(statuses):
        return DELIVERY_OPERATION_STATUS_SENT, sent_parts
    if DELIVERY_PART_STATUS_UNKNOWN in statuses:
        return DELIVERY_OPERATION_STATUS_NEEDS_ATTENTION, sent_parts
    if DELIVERY_PART_STATUS_SENDING in statuses:
        return DELIVERY_OPERATION_STATUS_SENDING, sent_parts
    if any(
        part["status"] == DELIVERY_PART_STATUS_FAILED
        and int(part.get("attempt_count") or 0) >= max_attempts
        for part in rows
    ):
        return DELIVERY_OPERATION_STATUS_FAILED, sent_parts
    return DELIVERY_OPERATION_STATUS_PENDING, sent_parts
