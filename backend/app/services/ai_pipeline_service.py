from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Dict
import uuid
import json

from shared.content_contract import (
    REVIEW_STATUS_DISCARDED,
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_SELECTED,
)
from ..core.exceptions import BusinessError, ValidationError
from ..core.time import utc_cutoff
from .llm import EditorialAIService


class AIPipelineService:
    CLAIM_LEASE_SECONDS = 300
    MASKED_SECRET = "••••••••"

    def __init__(
        self,
        ai_provider_settings,
        automation_settings,
        editorial_profile_repository,
        event_query_repository,
        review_repository,
        review_admin_repository,
        ai_quality_repository,
        transaction,
        budget=None,
    ):
        self._ai_provider_settings = ai_provider_settings
        self._automation_settings = automation_settings
        self._editorial_profile_repository = editorial_profile_repository
        self._event_query_repository = event_query_repository
        self._review_repository = review_repository
        self._review_admin_repository = review_admin_repository
        self._ai_quality_repository = ai_quality_repository
        self._transaction = transaction
        self._budget = budget

    def _build_service(self, phase: str, config: Dict | None = None) -> EditorialAIService:
        config = config if config is not None else self._ai_provider_settings.get_config(include_secrets=True)
        providers = config["providers"]
        if not providers:
            raise ValidationError("请先配置至少一个 AI 端点")
        concurrency_key = "enrichment_concurrency" if phase == "enrichment" else "analysis_concurrency"
        return EditorialAIService(
            providers,
            config[concurrency_key],
            config["throttle_seconds"],
            self._record_ai_invocation,
            self._budget,
        )

    def _record_ai_invocation(self, event: Dict) -> None:
        self._ai_quality_repository().record_invocation(event)

    def _resolve_test_config(self, config: Dict | None) -> Dict | None:
        if config is None:
            return None
        persisted = self._ai_provider_settings.get_config(include_secrets=True)
        persisted_by_name = {
            provider.get("name"): provider
            for provider in persisted.get("providers") or []
        }
        providers = []
        for provider in config.get("providers") or []:
            resolved = dict(provider)
            if resolved.get("api_key") == self.MASKED_SECRET:
                resolved["api_key"] = (persisted_by_name.get(resolved.get("name")) or {}).get("api_key") or ""
            providers.append(resolved)
        return {**config, "providers": providers}

    @asynccontextmanager
    async def _keep_claim_alive(self, renew_claim, claim_token: str):
        claim_lost = asyncio.Event()
        holder_task = asyncio.current_task()

        async def heartbeat():
            try:
                while True:
                    await asyncio.sleep(self.CLAIM_LEASE_SECONDS / 3)
                    renewed = await asyncio.to_thread(
                        renew_claim,
                        claim_token,
                        self.CLAIM_LEASE_SECONDS,
                    )
                    if renewed <= 0:
                        claim_lost.set()
                        if holder_task is not None:
                            holder_task.cancel()
                        return
            except asyncio.CancelledError:
                raise
            except Exception:
                claim_lost.set()
                if holder_task is not None:
                    holder_task.cancel()

        task = asyncio.create_task(heartbeat(), name=f"ai-claim:{claim_token[:8]}")
        try:
            try:
                yield
            except asyncio.CancelledError as exc:
                if claim_lost.is_set():
                    raise BusinessError("AI 任务领取权已失效，已停止写入本批结果") from exc
                raise
            if claim_lost.is_set():
                raise BusinessError("AI 任务领取权已失效，已停止写入本批结果")
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def run_content_review(self, hours: int, content_kind: str = "news") -> Dict:
        cutoff_time = "1970-01-01 00:00:00" if hours <= 0 else utc_cutoff(hours)
        claim_token = uuid.uuid4().hex
        batch_size = self._automation_settings.get_runtime()["review_batch_size"]
        with self._transaction() as tx_repos:
            rows = tx_repos.review_admin.claim_pending_entries(
                cutoff_time, content_kind, claim_token, batch_size
            )
        attempted_count = len(rows)
        results = []

        async def review_one(row: Dict) -> Dict:
            profiles = self._editorial_profile_repository()
            profile = profiles.get(row.get("profile_slug") or "") or profiles.get_default(content_kind)
            if not profile:
                return {"row": row, "error": "找不到内容档案"}
            prompt = (profile.get("review_prompt") or "").strip()
            if not prompt:
                return {"row": row, "error": f"内容档案 {profile['name']} 尚未配置审核标准"}
            try:
                decision = await service.review_event(
                    row["title"],
                    prompt,
                    row.get("content", ""),
                    {
                        "operation_id": claim_token,
                        "review_entry_id": row["id"],
                        "event_id": row.get("event_id"),
                        "profile_slug": profile["slug"],
                    },
                )
                score = min(max(int(decision.get("score") or 0), 0), 10)
                selected = bool(decision.get("passed")) and score >= int(profile.get("min_score") or 5)
                return {"row": row, "profile": profile, "decision": {**decision, "score": score}, "selected": selected}
            except Exception as exc:
                return {"row": row, "error": str(exc)}

        review_results = []
        if rows:
            try:
                service = self._build_service("analysis")
            except Exception as exc:
                with self._transaction() as tx_repos:
                    tx_repos.review_admin.release_review_claim(claim_token, str(exc))
                raise
            try:
                async with self._keep_claim_alive(
                    self._review_admin_repository().renew_review_claim,
                    claim_token,
                ):
                    review_results = await asyncio.gather(*(review_one(row) for row in rows))
            finally:
                await service.close()

        selected_rows = []
        failed = 0
        for outcome in review_results:
            row = outcome["row"]
            if outcome.get("error"):
                failed += 1
                self._review_repository().save_review_error(row["id"], outcome["error"], claim_token)
                results.append({"id": row["id"], "title": row["title"], "review_status": REVIEW_STATUS_PENDING, "error": outcome["error"]})
                continue
            decision = outcome["decision"]
            review_status = REVIEW_STATUS_SELECTED if outcome["selected"] else REVIEW_STATUS_DISCARDED
            category = (decision.get("category") or "").strip()
            tags = [category] if category else []
            with self._transaction() as tx_repos:
                saved = tx_repos.review.save_review_result(
                    row["id"], review_status, decision.get("reason", ""), decision["score"],
                    category or None, decision.get("summary"),
                    json.dumps(tags, ensure_ascii=False), claim_token=claim_token,
                )
                if saved and category and row.get("source_item_id"):
                    tag_id = tx_repos.tags.insert_or_get_tag(category, "AI 审核分类")
                    tx_repos.tags.associate_tags(int(row["source_item_id"]), [tag_id])
            if not saved:
                failed += 1
                results.append({
                    "id": row["id"], "title": row["title"], "review_status": REVIEW_STATUS_PENDING,
                    "error": "审核任务执行权已失效，结果未写入",
                })
                continue
            result = {
                "id": row["id"], "event_id": row.get("event_id"), "title": row["title"],
                "profile": outcome["profile"], "review_status": review_status, "score": decision["score"],
            }
            results.append(result)
            if outcome["selected"]:
                selected_rows.append(result)

        enrichment = await self._enrich_pending(content_kind)
        selected_count = len(selected_rows)
        discarded_count = attempted_count - selected_count - failed
        remaining = self._review_admin_repository().count_claimable_entries(cutoff_time, content_kind)

        return {
            "processed": attempted_count - failed,
            "attempted": attempted_count,
            "failed": failed,
            "discarded": discarded_count,
            "selected": selected_count,
            "enriched": enrichment["completed"],
            "enrichment_failed": enrichment["failed"],
            "enrichment_remaining": enrichment["remaining"],
            "total": attempted_count + remaining,
            "remaining": remaining,
            "results": results,
        }

    async def _enrich_pending(self, content_kind: str) -> Dict:
        claim_token = uuid.uuid4().hex
        batch_size = self._automation_settings.get_runtime()["enrichment_batch_size"]
        with self._transaction() as tx_repos:
            selected_rows = tx_repos.review_admin.claim_enrichment_entries(
                content_kind, claim_token, batch_size
            )
        if not selected_rows:
            return {
                "completed": 0,
                "failed": 0,
                "remaining": self._review_admin_repository().count_claimable_enrichment_entries(content_kind),
            }
        try:
            service = self._build_service("enrichment")
        except Exception as exc:
            with self._transaction() as tx_repos:
                tx_repos.review_admin.release_enrichment_claim(claim_token, str(exc))
            raise

        async def enrich_one(row: Dict) -> Dict:
            profile = self._editorial_profile_repository().get(row.get("profile_slug") or "")
            if not profile:
                return {"id": row["id"], "error": "找不到内容档案"}
            event_id = row.get("event_id")
            events = self._event_query_repository()
            event = events.get_event(event_id) if event_id else None
            sources = events.get_sources(event_id) if event_id else []
            if not event or not sources:
                return {"id": row["id"], "error": "事件缺少可引用来源"}
            try:
                result = await service.enrich_event(
                    event["title"],
                    sources,
                    profile.get("enrichment_prompt") or "",
                    {
                        "operation_id": claim_token,
                        "review_entry_id": row["id"],
                        "event_id": event_id,
                        "profile_slug": profile["slug"],
                    },
                )
                return {"id": row["id"], "result": result}
            except Exception as exc:
                return {"id": row["id"], "error": str(exc)}

        try:
            async with self._keep_claim_alive(
                self._review_admin_repository().renew_enrichment_claim,
                claim_token,
            ):
                outcomes = await asyncio.gather(*(enrich_one(row) for row in selected_rows))
        finally:
            await service.close()
        completed = 0
        failed = 0
        for outcome in outcomes:
            if outcome.get("error"):
                failed += 1
                self._review_repository().save_enrichment_error(outcome["id"], outcome["error"], claim_token)
            else:
                if self._review_repository().save_enrichment_result(outcome["id"], outcome["result"], claim_token):
                    completed += 1
                else:
                    failed += 1
        remaining = self._review_admin_repository().count_claimable_enrichment_entries(content_kind)
        return {"completed": completed, "failed": failed, "remaining": remaining}

    async def test_ai_connection(self, config: Dict | None = None) -> Dict:
        service = self._build_service("analysis", self._resolve_test_config(config))
        try:
            result = await service.test_connection()
        finally:
            await service.close()
        if not result["ok"]:
            raise BusinessError(f"连接失败: {result.get('error')}")
        return result
