from __future__ import annotations

import json
from typing import Dict

from shared.content_contract import DELIVERY_OPERATION_STATUS_SENT

from ..core.exceptions import NotFoundError, ValidationError


class AnalystSubscriptionService:
    def __init__(
        self,
        repository,
        publication_repository,
        event_repository,
        catalog_repository,
        tag_repository,
        delivery_operations,
        transaction,
    ):
        self._repository = repository
        self._publication_repository = publication_repository
        self._event_repository = event_repository
        self._catalog_repository = catalog_repository
        self._tag_repository = tag_repository
        self._delivery_operations = delivery_operations
        self._transaction = transaction

    def list_subscriptions(self) -> list[Dict]:
        return self._repository().list_subscriptions()

    def _validate_channel(self, channel_id: int) -> Dict:
        channel = self._publication_repository().get_channel(channel_id)
        if not channel:
            raise NotFoundError("投递渠道不存在")
        if channel["channel_type"] != "webhook":
            raise ValidationError("分析师变更订阅必须使用 Webhook 渠道")
        return channel

    def create(self, values: Dict) -> Dict:
        self._validate_channel(values["channel_id"])
        initial_cursor = self._repository().current_cursor() if values.pop("start_from", "now") == "now" else 0
        subscription_id = self._repository().save_subscription(values, initial_cursor=initial_cursor)
        return self._repository().get_subscription(subscription_id)

    def update(self, subscription_id: int, values: Dict) -> Dict:
        if values.get("channel_id") is not None:
            self._validate_channel(values["channel_id"])
        if not self._repository().save_subscription(values, subscription_id):
            raise NotFoundError("分析师变更订阅不存在")
        return self._repository().get_subscription(subscription_id)

    def _hydrate_change(self, change: Dict) -> Dict:
        object_type = change["object_type"]
        object_id = int(change["object_id"])
        if change["action"] == "deleted":
            data = None
        elif object_type == "event":
            data = self._event_repository().get_detail(object_id)
        elif object_type == "correction":
            data = self._repository().get_correction(object_id)
        elif object_type == "entity":
            data = self._catalog_repository().get_entity(object_id)
        elif object_type == "narrative":
            data = self._catalog_repository().get_narrative(object_id)
        else:
            data = self._tag_repository().get_tag(object_id)
        return {**change, "data": data}

    @staticmethod
    def _matches(subscription: Dict, change: Dict) -> bool:
        if change["object_type"] not in subscription["object_types"]:
            return False
        data = change.get("data")
        content_types = set(subscription.get("content_types") or [])
        profile_slugs = set(subscription.get("profile_slugs") or [])
        if change["object_type"] == "event" and data:
            if not any(review.get("review_status") == "selected" for review in data.get("reviews") or []):
                return False
            if content_types and data["event"].get("content_type") not in content_types:
                return False
            if profile_slugs and not profile_slugs.intersection(
                review.get("profile_slug") for review in data.get("reviews") or []
            ):
                return False
        elif change["object_type"] == "correction" and data:
            if content_types and data.get("content_type") not in content_types:
                return False
            if profile_slugs and data.get("profile_slug") not in profile_slugs:
                return False
        return True

    def _collect(self, subscription: Dict) -> tuple[list[Dict], int, bool]:
        start_cursor = int(subscription["cursor"])
        scan_limit = min(max(int(subscription["batch_size"]) * 20, 200), 2000)
        rows = self._repository().list_changes(start_cursor, scan_limit)
        matched = []
        scanned_cursor = start_cursor
        for row in rows:
            hydrated = self._hydrate_change(row)
            scanned_cursor = int(row["cursor"])
            if self._matches(subscription, hydrated):
                matched.append(hydrated)
                if len(matched) >= int(subscription["batch_size"]):
                    break
        return matched, scanned_cursor, self._repository().current_cursor() > scanned_cursor

    async def deliver(self, subscription_id: int | None = None) -> Dict:
        subscriptions = self._repository().list_subscriptions(enabled_only=True)
        if subscription_id is not None:
            subscriptions = [item for item in subscriptions if int(item["id"]) == subscription_id]
            if not subscriptions:
                raise NotFoundError("启用的分析师变更订阅不存在")
        results = []
        for subscription in subscriptions:
            try:
                changes, scanned_cursor, has_more = self._collect(subscription)
                start_cursor = int(subscription["cursor"])
                if scanned_cursor == start_cursor:
                    results.append({"subscription_id": subscription["id"], "status": "idle", "cursor": start_cursor})
                    continue
                if not changes:
                    self._repository().advance_cursor(subscription["id"], scanned_cursor, False)
                    results.append({"subscription_id": subscription["id"], "status": "filtered", "cursor": scanned_cursor, "has_more": has_more})
                    continue
                payload = {
                    "event": "ainews.analyst.changes",
                    "schema_version": 1,
                    "subscription": {"id": subscription["id"], "name": subscription["name"]},
                    "cursor": {"from": start_cursor, "to": scanned_cursor, "has_more": has_more},
                    "changes": changes,
                }
                operation_key = f"analyst-subscription:{subscription['id']}:{start_cursor}-{scanned_cursor}"
                self._delivery_operations.prepare(
                    operation_key,
                    "analyst_subscription",
                    None,
                    [json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)],
                    [],
                    {"subscription_id": subscription["id"], "cursor_from": start_cursor, "cursor_to": scanned_cursor},
                    channel_slug=subscription["channel_slug"],
                )
                outcome = await self._delivery_operations.send(operation_key)
                if outcome["status"] == DELIVERY_OPERATION_STATUS_SENT:
                    self._repository().advance_cursor(subscription["id"], scanned_cursor, True)
                results.append({"subscription_id": subscription["id"], "cursor": scanned_cursor, "change_count": len(changes), "has_more": has_more, "operation": outcome, "status": outcome["status"]})
            except Exception as exc:
                results.append({"subscription_id": subscription["id"], "status": "failed", "error": str(exc)})
        return {"subscriptions": len(subscriptions), "results": results}
