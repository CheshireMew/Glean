from __future__ import annotations

import json
from typing import Dict

from shared.content_contract import DELIVERY_OPERATION_STATUS_SENT

from ..core.exceptions import ConflictError, NotFoundError, ValidationError


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

    def finalize_success(self, operation_key: str) -> Dict:
        with self._transaction() as repos:
            operation = repos.delivery_operations.get_operation(operation_key)
            if not operation or operation["operation_type"] != "analyst_subscription":
                raise NotFoundError("订阅交付操作不存在")
            metadata = operation["metadata"]
            plan = repos.delivery_operations.plan_for_operation(operation_key)
            if plan and plan["finalized_at"]:
                return plan["result"]
            if operation["status"] != DELIVERY_OPERATION_STATUS_SENT:
                return {"status": operation["status"]}
            if not repos.analyst_subscriptions.complete_batch(metadata["subscription_id"], metadata["cursor_from"], metadata["cursor_to"]):
                raise ConflictError("订阅游标与原交付区间不一致，不能跳过未完成变更")
            result = {"subscription_id": metadata["subscription_id"], "cursor": metadata["cursor_to"], "status": "sent"}
            if plan:
                repos.delivery_operations.finalize_plan(plan["plan_key"], result)
            return result

    async def _deliver_plan(self, plan: Dict) -> Dict:
        outcome = (await self._delivery_operations.send_plan(plan))[0]
        payload = plan["payload"]
        if outcome["status"] == DELIVERY_OPERATION_STATUS_SENT:
            self.finalize_success(outcome["operation_key"])
        return {"subscription_id": plan["owner_id"], "cursor": payload["cursor"]["to"],
                "change_count": len(payload["changes"]), "has_more": payload["cursor"]["has_more"],
                "operation": outcome, "status": outcome["status"]}

    @staticmethod
    def _recover_legacy_batch(repos, subscription: Dict) -> Dict | None:
        operation = repos.delivery_operations.legacy_subscription_operation(subscription['id'], subscription['cursor'])
        if not operation:
            return None
        parts = repos.delivery_execution.list_parts(operation['id'])
        if len(parts) != 1:
            raise ConflictError('原订阅批次缺少完整 JSON 消息，不能按当前对象重建')
        payload = json.loads(parts[0]['content'])
        metadata = operation['metadata']
        if payload['subscription']['id'] != subscription['id'] or payload['cursor']['from'] != metadata['cursor_from'] or payload['cursor']['to'] != metadata['cursor_to']:
            raise ConflictError('原订阅消息与已保存游标区间不一致')
        return repos.delivery_operations.create_plan(operation['operation_key'], 'analyst_subscription', subscription['id'], payload, [operation['operation_key']])

    async def deliver(self, subscription_id: int | None = None) -> Dict:
        active = self._delivery_operations.active_plans("analyst_subscription")
        active_ids = {plan["owner_id"] for plan in active}
        subscriptions = [item for item in self._repository().list_subscriptions()
                         if item["enabled"] or item["id"] in active_ids]
        if subscription_id is not None:
            subscriptions = [item for item in subscriptions if int(item["id"]) == subscription_id]
            if not subscriptions:
                raise NotFoundError("启用的分析师变更订阅不存在")
        results = []
        for subscription in subscriptions:
            try:
                with self._transaction() as repos:
                    # All readers and acceptors use the same write transaction;
                    # another worker cannot accept a later batch before this one.
                    pending = self._delivery_operations.active_plans("analyst_subscription", subscription["id"])
                    if pending:
                        frozen = pending[0]
                    else:
                        current = self._repository().get_subscription(subscription["id"])
                        frozen = self._recover_legacy_batch(repos, current)
                    if not frozen:
                        changes, scanned_cursor, has_more = self._collect(current)
                        start_cursor = int(current["cursor"])
                        if scanned_cursor == start_cursor:
                            results.append({"subscription_id": subscription["id"], "status": "idle", "cursor": start_cursor})
                            continue
                        if not changes:
                            self._repository().advance_cursor(subscription["id"], scanned_cursor, False)
                            results.append({"subscription_id": subscription["id"], "status": "filtered", "cursor": scanned_cursor, "has_more": has_more})
                            continue
                        payload = {
                            "event": "ainews.analyst.changes", "schema_version": 1,
                            "subscription": {"id": subscription["id"], "name": current["name"]},
                            "cursor": {"from": start_cursor, "to": scanned_cursor, "has_more": has_more},
                            "changes": changes,
                        }
                        operation_key = f"analyst-subscription:{subscription['id']}:{start_cursor}-{scanned_cursor}"
                        frozen = self._delivery_operations.accept_plan(operation_key, "analyst_subscription", subscription["id"], payload, [{
                            "operation_key": operation_key, "channel_slug": current["channel_slug"],
                            "messages": [json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)],
                            "metadata": {"subscription_id": subscription["id"], "cursor_from": start_cursor, "cursor_to": scanned_cursor},
                        }])
                results.append(await self._deliver_plan(frozen))
            except Exception as exc:
                results.append({"subscription_id": subscription["id"], "status": "failed", "error": str(exc)})
        return {"subscriptions": len(subscriptions), "results": results}
