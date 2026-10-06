from __future__ import annotations

import html
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from shared.content_contract import DELIVERY_OPERATION_STATUS_SENT

from ..core.exceptions import ConflictError, NotFoundError, ValidationError
from ..core.time import format_utc_time
from ..domain.editorial import validate_draft_items
from .digest_planner_service import DigestPolicy


class PublicationWorkflowService:
    def __init__(
        self,
        editorial_repository,
        publication_repository,
        daily_report_repository,
        review_delivery_repository,
        review_repository,
        push_repository,
        intelligence_repository,
        event_repository,
        digest_planner,
        message_service,
        delivery_operations,
        channel_gateway,
        config_repository,
        transaction,
    ):
        self._editorial_repository = editorial_repository
        self._publication_repository = publication_repository
        self._daily_report_repository = daily_report_repository
        self._review_delivery_repository = review_delivery_repository
        self._review_repository = review_repository
        self._push_repository = push_repository
        self._intelligence_repository = intelligence_repository
        self._event_repository = event_repository
        self._digest_planner = digest_planner
        self._message_service = message_service
        self._delivery_operations = delivery_operations
        self._channel_gateway = channel_gateway
        self._config_repository = config_repository
        self._transaction = transaction

    @staticmethod
    def _entries(draft: Dict) -> list[Dict]:
        result = []
        for item in draft.get("items") or []:
            if not item.get("included"):
                continue
            entry = dict(item)
            entry.update(item.get("overrides") or {})
            entry["id"] = int(item["review_entry_id"])
            entry['editorial_version'] = int(item.get('editorial_version') or 0)
            entry["digest_section"] = item.get("section") or entry.get("review_category") or "其他"
            entry["content_type"] = draft["content_type"]
            result.append(entry)
        return result

    def _plan(self, draft: Dict, *, require_targets: bool = True) -> Dict:
        publication = self._publication_repository().get_publication(int(draft["publication_id"]))
        if not publication or not publication.get("enabled"):
            raise ValidationError("发布频道不存在或已停用")
        validate_draft_items(
            publication, draft["content_type"], draft.get("items") or [],
            self._editorial_repository().get_entry,
        )
        entries = self._entries(draft)
        if not entries:
            raise ValidationError("发布草稿没有可发布的内容")
        targets = [
            target for target in publication.get("targets") or []
            if target.get("enabled") and target.get("channel_enabled") and target["delivery_mode"] == "digest"
        ]
        if require_targets and not targets:
            raise ValidationError("发布频道没有启用的摘要投递目标")
        _generated_title, items = self._message_service.build_daily_report(
            entries, draft["content_type"], self._config_repository().get_system_time()
        )
        template = publication.get("template") or {}
        title = f"{template.get('title_prefix') or ''}{draft['title']}{template.get('title_suffix') or ''}"
        intro = template.get("intro")
        footer = template["footer"] if "footer" in template else None
        content = self._message_service.compose_daily_report_part(title, items, intro, footer)
        parts = self._message_service.split_daily_report_parts(title, items, intro=intro, footer=footer)
        return {
            "publication": publication,
            "entries": entries,
            "targets": targets,
            "items": items,
            "title": title,
            "content": content,
            "parts": parts,
        }

    def preview_draft(self, draft_id: int) -> Dict:
        draft = self._editorial_repository().get_draft(draft_id)
        if not draft:
            raise NotFoundError("发布草稿不存在")
        frozen = self._delivery_operations.get_plan(f"draft:{draft['draft_key']}")
        plan = frozen['payload'] if frozen else self._plan(draft, require_targets=False)
        return {
            "draft_id": draft_id,
            "title": plan["title"],
            "content": plan["content"],
            "parts": plan["parts"],
            "items": plan["items"],
            "target_count": len(plan["targets"]),
        }

    def finalize_success(self, operation_key: str) -> Dict:
        plan = self._delivery_operations.plan_for_operation(operation_key)
        if not plan:
            operation = self._delivery_operations.get_operation(operation_key)
            if operation['status'] != DELIVERY_OPERATION_STATUS_SENT:
                return {'status': 'publishing'}
            # Legacy alert operations already carry their entire owning match set.
            with self._transaction() as repos:
                original = repos.delivery_operations.get_operation(operation_key)
                if original['operation_type'] == 'event_alert':
                    metadata = original['metadata']
                    for event_id in metadata['event_ids']:
                        repos.intelligence_catalog.update_alert_match(metadata['policy_id'], event_id, 'sent', operation_key)
                    return {'status': 'sent'}
            raise ConflictError("原交付缺少业务快照，不能按当前内容推断完成；请保留原记录并重新建稿")
        return self._finalize_plan(plan["plan_key"])

    def _finalize_plan(self, plan_key: str) -> Dict:
        with self._transaction() as repos:
            plan = repos.delivery_operations.get_plan(plan_key)
            if plan["finalized_at"]:
                return plan["result"]
            results = self._delivery_operations.plan_results(plan)
            payload = plan["payload"]
            if not all(result["status"] == DELIVERY_OPERATION_STATUS_SENT for result in results):
                return {"status": "publishing", "operations": results}
            operation_type = plan["operation_type"]
            result = {"status": "published"}
            if operation_type == "publication_draft":
                draft = payload["draft"]
                repos.editorial_workbench.save_draft_snapshots(draft['id'], payload['entries'])
                report_id = repos.daily_reports.save_report(
                    draft["draft_key"], payload["report_date"], draft["content_type"],
                    payload["title"], payload["content"], len(payload["entries"]),
                    profile_slug=draft["profile_slug"], publication_id=draft["publication_id"],
                    draft_id=draft["id"],
                )
                repos.daily_reports.save_report_items(report_id, payload["entries"])
                if not payload["website_only"]:
                    repos.review.mark_delivered_versions(payload["entries"])
                repos.editorial_workbench.update_draft(draft["id"], status="published", published_report_id=report_id)
                result.update(draft_id=draft["id"], report_id=report_id)
            elif operation_type == "publication_correction":
                repos.editorial_workbench.mark_correction_published(plan["owner_id"])
                result["correction_id"] = plan["owner_id"]
            elif operation_type == "publication_realtime":
                repos.review.mark_delivered_versions([payload["entry"]])
                result["entry_id"] = payload["entry"]["id"]
            elif operation_type == "event_alert":
                for event_id in payload["event_ids"]:
                    repos.intelligence_catalog.update_alert_match(payload["policy_id"], event_id, "sent", plan["operation_keys"][0])
                result["status"] = "sent"
            else:
                raise ValidationError("交付计划不属于发布流程")
            repos.delivery_operations.finalize_plan(plan_key, result)
            return result

    async def publish_draft(self, draft_id: int, *, website_only: bool = False) -> Dict:
        draft = self._editorial_repository().get_draft(draft_id)
        if not draft:
            raise NotFoundError("发布草稿不存在")
        if draft["status"] == "cancelled":
            raise ConflictError("已取消的草稿不能发布")
        if draft["status"] == "published":
            return {"draft_id": draft_id, "status": "published", "report_id": draft.get("published_report_id"), "operations": []}
        plan_key = f"draft:{draft['draft_key']}"
        frozen = self._delivery_operations.get_plan(plan_key) if self._delivery_operations else None
        if draft["status"] == "publishing" and not frozen:
            raise ConflictError("发布中的草稿缺少原发布计划，无法重试，请重新建稿")
        if frozen and website_only != frozen["payload"]["website_only"]:
            raise ConflictError("草稿已有发布计划，请先完成原发布")
        if not frozen:
            plan = self._plan(draft, require_targets=not website_only)
            if website_only:
                if not plan["publication"].get("is_public"):
                    raise ValidationError("仅发布到网站需要选择公开频道")
                if any((self._editorial_repository().get_entry(entry["id"]) or {}).get("review_status") != "selected" for entry in plan["entries"]):
                    raise ValidationError("请先审核并入选草稿内的全部内容")
                plan["targets"] = []
            unavailable = [target["channel_name"] for target in plan["targets"] if not self._channel_gateway.channel_is_configured(target["channel_slug"])]
            if unavailable:
                raise ValidationError(f"以下投递渠道尚未配置完整：{', '.join(unavailable)}")
            payload = {**plan, "draft": draft, "website_only": website_only,
                       "report_date": self._config_repository().get_system_time().strftime("%Y-%m-%d")}
            operations = [{
                "operation_key": f"publish:{draft['draft_key']}:{target['channel_slug']}",
                "channel_slug": target["channel_slug"], "content_kind": draft["content_type"],
                "messages": plan["parts"], "entry_ids": [entry["id"] for entry in plan["entries"]],
                "metadata": {"draft_id": draft_id, "publication_id": draft["publication_id"], "profile_slug": draft["profile_slug"]},
            } for target in plan["targets"]]
            with self._transaction() as repos:
                frozen = self._delivery_operations.accept_plan(plan_key, "publication_draft", draft_id, payload, operations)
                repos.editorial_workbench.update_draft(draft_id, status="publishing")
        results = await self._delivery_operations.send_plan(frozen)
        result = self._finalize_plan(plan_key)
        return {"draft_id": draft_id, **result, "operations": results}

    async def publish_due_drafts(self, limit: int = 100) -> Dict:
        drafts = self._editorial_repository().list_due_drafts(limit)
        results = []
        for draft in drafts:
            try:
                results.append(await self.publish_draft(int(draft["id"])))
            except Exception as exc:
                results.append({"draft_id": draft["id"], "status": "failed", "error": str(exc)})
        return {"processed": len(drafts), "results": results}

    @staticmethod
    def _local_now(now: datetime, publication: Dict) -> datetime:
        timezone_name = publication.get("timezone")
        if not timezone_name:
            return now
        try:
            aware = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
            return aware.astimezone(ZoneInfo(timezone_name))
        except ZoneInfoNotFoundError:
            return now

    def _schedule_due(self, publication: Dict, now: datetime) -> tuple[bool, str, int]:
        frequency = publication.get("digest_frequency")
        if frequency not in {"daily", "weekly"}:
            return False, "", 24
        local_now = self._local_now(now, publication)
        try:
            hour, minute = map(int, publication.get("digest_time", "09:00").split(":"))
        except ValueError:
            return False, "", 24
        if (local_now.hour, local_now.minute) < (hour, minute):
            return False, "", 24
        period_key = local_now.strftime("%Y-%m-%d") if frequency == "daily" else f"{local_now.isocalendar().year}-W{local_now.isocalendar().week:02d}"
        if frequency == "weekly" and local_now.weekday() != int((publication.get("template") or {}).get("weekday", 0)):
            return False, period_key, 168
        latest = self._daily_report_repository().latest_publication_report(int(publication["id"]))
        if latest:
            created = datetime.fromisoformat(str(latest["created_at"]).replace("Z", "+00:00"))
            latest_local = self._local_now(created, publication)
            latest_key = latest_local.strftime("%Y-%m-%d") if frequency == "daily" else f"{latest_local.isocalendar().year}-W{latest_local.isocalendar().week:02d}"
            if latest_key == period_key:
                return False, period_key, 24 if frequency == "daily" else 168
        return True, period_key, 24 if frequency == "daily" else 168

    async def prepare_and_publish_scheduled(self) -> Dict:
        now = self._config_repository().get_system_time()
        created = []
        for publication in self._publication_repository().list_publications():
            if not publication.get("enabled"):
                continue
            due, period_key, hours = self._schedule_due(publication, now)
            if not due:
                continue
            targets = [target for target in publication.get("targets") or [] if target.get("enabled") and target.get("channel_enabled") and target["delivery_mode"] == "digest"]
            if not targets or not all(self._channel_gateway.channel_is_configured(target["channel_slug"]) for target in targets):
                continue
            start_time = format_utc_time(now - timedelta(hours=hours))
            eligible = [
                {**item, "content_type": publication["content_type"]}
                for item in self._review_delivery_repository().get_ranked_entries(start_time, publication["content_type"], publication["profile_slug"])
                if int(item.get("review_score") or 0) >= int(publication.get("min_score") or 0)
            ]
            entries = self._digest_planner.plan(
                eligible,
                publication["content_type"],
                DigestPolicy(
                    max_items=int(publication.get("max_items") or 12),
                    max_per_category=int(publication.get("max_per_category") or 4),
                    max_per_source=int(publication.get("max_per_source") or 4),
                ),
            )
            if not entries:
                continue
            draft_key = f"scheduled:{publication['id']}:{period_key}"
            draft = self._editorial_repository().get_draft_by_key(draft_key)
            if not draft:
                title = f"{now.strftime('%Y-%m-%d')} {publication['display_name']}"
                with self._transaction() as repos:
                    draft_id = repos.editorial_workbench.create_draft(
                        draft_key, publication["id"], publication["content_type"], title, "scheduler"
                    )
                    repos.editorial_workbench.replace_draft_items(
                        draft_id,
                        [
                            {"review_entry_id": entry["id"], "position": index, "section": entry["digest_section"], "included": True, "overrides": {}}
                            for index, entry in enumerate(entries)
                        ],
                    )
                draft = self._editorial_repository().get_draft(draft_id)
                created.append(draft_id)
            await self.publish_draft(int(draft["id"]))
        due_result = await self.publish_due_drafts()
        return {"created_drafts": created, "scheduled": due_result}

    async def publish_correction(self, correction_id: int) -> Dict:
        correction = self._editorial_repository().get_correction(correction_id)
        if not correction:
            raise NotFoundError("更正记录不存在")
        if correction.get("published_at"):
            return {"correction_id": correction_id, "status": "published", "operations": []}
        existing = self._delivery_operations.get_plan(f"correction:{correction_id}")
        if existing:
            results = await self._delivery_operations.send_plan(existing)
            return {"correction_id": correction_id, **self._finalize_plan(existing["plan_key"]), "operations": results}
        publication = None
        if correction.get("report_publication_id"):
            publication = self._publication_repository().get_publication(int(correction["report_publication_id"]))
        elif correction.get("entry_profile_slug"):
            publication = self._publication_repository().get_publication_by_profile(correction["entry_profile_slug"])
        elif correction.get("event_id"):
            detail = self._event_repository().get_detail(int(correction["event_id"]))
            profile_slug = next((item.get("profile_slug") for item in (detail or {}).get("reviews", []) if item.get("profile_slug")), None)
            publication = self._publication_repository().get_publication_by_profile(profile_slug) if profile_slug else None
        if not publication:
            raise ValidationError("无法从更正对象确定发布频道，请关联日报或已审核内容")
        targets = [target for target in publication.get("targets") or [] if target.get("enabled") and target.get("channel_enabled") and target["delivery_mode"] == "digest"]
        if not targets:
            raise ValidationError("发布频道没有启用的摘要投递目标")
        type_names = {"correction": "更正", "clarification": "澄清", "retraction": "撤回"}
        message = f"⚠️ <b>{type_names.get(correction['correction_type'], '更正')}</b>\n\n{html.escape(correction['message'])}"
        plan_key = f"correction:{correction_id}"
        frozen = self._delivery_operations.accept_plan(plan_key, "publication_correction", correction_id,
            {"correction": correction, "publication": publication, "targets": targets}, [{
                "operation_key": f"correction:{correction_id}:{target['channel_slug']}",
                "channel_slug": target["channel_slug"], "content_kind": publication["content_type"],
                "messages": [message], "metadata": {"correction_id": correction_id, "publication_id": publication["id"]},
            } for target in targets])
        results = await self._delivery_operations.send_plan(frozen)
        return {"correction_id": correction_id, **self._finalize_plan(plan_key), "operations": results}

    def list_corrections(self, published: bool | None, limit: int) -> list[Dict]:
        rows = self._editorial_repository().list_corrections(published, limit)
        for row in rows:
            plan = self._delivery_operations.get_plan(f"correction:{row['id']}")
            if plan:
                row["delivery"] = {"status": "published" if plan["finalized_at"] else "publishing",
                                   "operations": [] if plan["finalized_at"] else self._delivery_operations.plan_results(plan)}
        return rows

    async def deliver_alert_matches(self, limit: int = 200) -> Dict:
        self._intelligence_repository().recover_alert_matches()
        for key in self._intelligence_repository().legacy_pending_alert_operations():
            outcome = await self._delivery_operations.send(key)
            if outcome['status'] == DELIVERY_OPERATION_STATUS_SENT:
                self.finalize_success(key)
        self._intelligence_repository().recover_alert_matches()
        policies = [policy for policy in self._intelligence_repository().list_alert_policies()
                    if policy.get('enabled') and self._alert_due(policy)
                    and self._channel_gateway.channel_is_configured(policy['channel_slug'])]
        matches = self._intelligence_repository().pending_alert_matches([policy['id'] for policy in policies], limit)
        results = []
        for plan in self._delivery_operations.active_plans('event_alert'):
            outcomes = await self._delivery_operations.send_plan(plan)
            if all(outcome['status'] == DELIVERY_OPERATION_STATUS_SENT for outcome in outcomes):
                self._finalize_plan(plan['plan_key'])
        grouped: dict[int, list[Dict]] = {}
        for match in matches:
            grouped.setdefault(int(match["policy_id"]), []).append(match)
        for policy_id, policy_matches in grouped.items():
            policy = self._intelligence_repository().get_alert_policy(policy_id)
            if not policy or not self._channel_gateway.channel_is_configured(policy_matches[0]["channel_slug"]):
                continue
            if not self._alert_due(policy):
                continue
            details = []
            for match in policy_matches:
                detail = self._event_repository().get_detail(int(match["event_id"]))
                if detail:
                    details.append((match, detail))
                else:
                    self._intelligence_repository().update_alert_match(policy_id, match["event_id"], "failed")
            if not details:
                continue
            if policy["schedule_type"] == "instant":
                batches = [[item] for item in details]
            else:
                batches = [details]
            for batch in batches:
                if len(batch) == 1:
                    match, detail = batch[0]
                    event = detail["event"]
                    summary = next((item.get("enriched_summary") or item.get("review_summary") for item in detail.get("reviews") or [] if item.get("enriched_summary") or item.get("review_summary")), "")
                    text = f"🚨 <b>{html.escape(policy['name'])}</b>\n\n<b>{html.escape(event['title'])}</b>"
                    if summary:
                        text += f"\n\n{html.escape(summary)}"
                    operation_key = f"alert:{policy_id}:{match['event_id']}:{match['channel_slug']}"
                else:
                    event_ids = [int(item[0]["event_id"]) for item in batch]
                    digest = hashlib.sha256(",".join(map(str, event_ids)).encode()).hexdigest()[:10]
                    local_now = self._alert_local_now(policy)
                    period = local_now.strftime("%Y%m%d") if policy["schedule_type"] == "daily" else f"{local_now.isocalendar().year}W{local_now.isocalendar().week:02d}"
                    operation_key = f"alert-digest:{policy_id}:{period}:{digest}"
                    lines = [f"• <b>{html.escape(item[1]['event']['title'])}</b>" for item in batch]
                    text = f"🚨 <b>{html.escape(policy['name'])} · {len(batch)} 条提醒</b>\n\n" + "\n\n".join(lines)
                channel_slug = batch[0][0]["channel_slug"]
                event_ids = [int(item[0]["event_id"]) for item in batch]
                with self._transaction() as repos:
                    frozen = self._delivery_operations.accept_plan(operation_key, 'event_alert', policy_id,
                        {'policy_id': policy_id, 'event_ids': event_ids, 'policy': policy, 'details': [detail for _, detail in batch]}, [{
                            'operation_key': operation_key, 'content_kind': batch[0][1]['event']['content_type'],
                            'messages': [text], 'channel_slug': channel_slug,
                            'metadata': {'policy_id': policy_id, 'event_ids': event_ids},
                        }])
                    for match, _detail in batch:
                        repos.intelligence_catalog.update_alert_match(policy_id, match['event_id'], 'queued', operation_key)
                result = (await self._delivery_operations.send_plan(frozen))[0]
                status = "sent" if result["status"] == DELIVERY_OPERATION_STATUS_SENT else "failed" if result["status"] == "failed" else "queued"
                for match, _detail in batch:
                    self._intelligence_repository().update_alert_match(policy_id, match["event_id"], status, operation_key)
                    results.append({**match, "delivery": result})
                if status == 'sent':
                    self._finalize_plan(frozen['plan_key'])
        return {"processed": len(results), "results": results}

    @staticmethod
    def _alert_local_now(policy: Dict) -> datetime:
        config = policy.get("quiet_hours") or {}
        timezone_name = config.get("timezone")
        now = datetime.now(timezone.utc)
        if timezone_name:
            try:
                return now.astimezone(ZoneInfo(timezone_name))
            except ZoneInfoNotFoundError:
                pass
        return now

    @classmethod
    def _alert_due(cls, policy: Dict) -> bool:
        config = policy.get("quiet_hours") or {}
        now = cls._alert_local_now(policy)
        current = now.hour * 60 + now.minute
        def minutes(value, fallback):
            try:
                hour, minute = map(int, str(value).split(":"))
                return hour * 60 + minute
            except (TypeError, ValueError):
                return fallback
        start = minutes(config.get("start"), -1)
        end = minutes(config.get("end"), -1)
        if start >= 0 and end >= 0:
            in_quiet = start <= current < end if start <= end else current >= start or current < end
            if in_quiet:
                return False
        if policy.get("schedule_type") == "instant":
            return True
        digest_time = minutes(config.get("digest_time"), 9 * 60)
        if current < digest_time:
            return False
        if policy.get("schedule_type") == "weekly":
            return now.weekday() == int(config.get("weekday", 0))
        return True

    async def _deliver_realtime_plan(self, plan: Dict) -> Dict:
        outcomes = await self._delivery_operations.send_plan(plan)
        payload = plan["payload"]
        for target, outcome in zip(payload["targets"], outcomes):
            self._push_repository().log_push_status(
                payload["entry"]["id"], target["channel_type"],
                "success" if outcome["status"] == DELIVERY_OPERATION_STATUS_SENT else outcome["status"],
                outcome.get("last_error"), outcome["operation_key"],
            )
        result = self._finalize_plan(plan["plan_key"])
        return {"publication_id": payload["publication"]["id"], "entry_id": payload["entry"]["id"],
                "status": result["status"], "operations": outcomes}

    async def deliver_realtime_entries(self) -> Dict:
        results = []
        seen = set()
        # Original plans are recovered before considering today's publications,
        # template, membership or selected targets.
        for frozen in self._delivery_operations.active_plans("publication_realtime"):
            seen.add((frozen['payload']['publication']['id'], frozen['owner_id']))
            results.append(await self._deliver_realtime_plan(frozen))
        for publication in self._publication_repository().list_publications():
            targets = [target for target in publication.get("targets") or []
                       if target.get("enabled") and target.get("channel_enabled") and target["delivery_mode"] == "realtime"]
            if not publication.get("enabled") or not targets:
                continue
            if not all(self._channel_gateway.channel_is_configured(target["channel_slug"]) for target in targets):
                continue
            entries = self._push_repository().get_pending_delivery_entries(publication["content_type"], publication["profile_slug"])
            for entry in entries:
                if (publication['id'], entry['id']) in seen:
                    continue
                plan_key = f"realtime:{publication['id']}:{entry['id']}:v{int(entry.get('editorial_version') or 0)}"
                frozen = self._delivery_operations.get_plan(plan_key)
                if not frozen:
                    parts = self._message_service.format_entry_parts(entry)
                    frozen = self._delivery_operations.accept_plan(plan_key, "publication_realtime", entry["id"],
                        {"publication": publication, "entry": entry, "targets": targets}, [{
                            "operation_key": f"{plan_key}:{target['channel_slug']}", "messages": parts,
                            "content_kind": publication["content_type"], "entry_ids": [entry["id"]],
                            "channel_slug": target["channel_slug"],
                            "metadata": {"publication_id": publication["id"], "profile_slug": publication["profile_slug"]},
                        } for target in targets])
                if not frozen["finalized_at"]:
                    results.append(await self._deliver_realtime_plan(frozen))
        return {"sent_count": len({row["entry_id"] for row in results if row["status"] == "published"}), "results": results}

    async def run_cycle(self) -> Dict:
        classifier = getattr(self, "classification_runner", None)
        classification = classifier(168, 500) if classifier else {"scanned": 0, "classified": 0, "errors": [], "results": []}
        alert_eval = self._evaluate_alerts_safely()
        realtime = await self.deliver_realtime_entries()
        digests = await self.prepare_and_publish_scheduled()
        alerts = await self.deliver_alert_matches()
        subscription_runner = getattr(self, "analyst_subscription_runner", None)
        subscriptions = await subscription_runner() if subscription_runner else {"subscriptions": 0, "results": []}
        return {"classification": classification, "realtime": realtime, "digests": digests, "alert_evaluation": alert_eval, "alerts": alerts, "analyst_subscriptions": subscriptions}

    def _evaluate_alerts_safely(self) -> Dict:
        # The catalog service owns condition matching; this small adapter is replaced
        # at composition with its bound method to keep the workflow independent.
        evaluator = getattr(self, "alert_evaluator", None)
        return evaluator(None, 168) if evaluator else {"policies": 0, "events_scanned": 0, "new_matches": 0, "matches": []}
