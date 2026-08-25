from __future__ import annotations

import asyncio
import inspect
import json
from logging import getLogger
import uuid

from shared.content_contract import CONTENT_KINDS


logger = getLogger("uvicorn")


class PipelineOrchestrator:
    """Coordinates pipeline stages; stage services own their own business rules."""

    def __init__(
        self,
        operation_leases,
        content_transitions,
        ai_pipeline,
        event_clustering,
        scraper_runs,
        publication_automation,
        automation_settings,
        processing_repository,
        editorial_profile_repository,
        source_operations=None,
        market_intelligence=None,
    ):
        self._operation_leases = operation_leases
        self._content_transitions = content_transitions
        self._ai_pipeline = ai_pipeline
        self._event_clustering = event_clustering
        self._scraper_runs = scraper_runs
        self._publication_automation = publication_automation
        self._automation_settings = automation_settings
        self._processing_repository = processing_repository
        self._editorial_profile_repository = editorial_profile_repository
        self._source_operations = source_operations
        self._market_intelligence = market_intelligence

    async def apply_blocklist(self, time_range_hours: int, content_kind: str) -> dict:
        async with self._operation_leases.hold("content-pipeline"):
            stats = await asyncio.to_thread(
                self._content_transitions.apply_blocklist, time_range_hours, content_kind
            )
            return {"stats": stats}

    async def run_review(self, hours: int, content_kind: str = "news") -> dict:
        async with self._operation_leases.hold("content-pipeline"):
            return await self._ai_pipeline.run_content_review(hours, content_kind)

    async def cluster_content(self, hours: int, threshold: float, content_kind: str) -> dict:
        async with self._operation_leases.hold("content-pipeline"):
            return await self._event_clustering.cluster_content(hours, threshold, content_kind)

    async def run_automation_cycle(self) -> dict:
        operation_id = f"pipeline-{uuid.uuid4().hex}"
        async with self._operation_leases.hold("content-pipeline", ttl_seconds=300):
            self._log("pipeline", "started", operation_id=operation_id)
            try:
                result = await self._run_automation_stages(operation_id)
            except Exception:
                self._log("pipeline", "failed", operation_id=operation_id)
                logger.exception("operation_id=%s status=failed", operation_id)
                raise
            failures = result["failures"]
            action = "completed_with_errors" if failures else "completed"
            details = json.dumps(failures, ensure_ascii=False) if failures else None
            if result["backlog_pending"]:
                backlog_details = f"backlog_remaining={result['remaining_by_kind']}"
                details = f"{details}; {backlog_details}" if details else backlog_details
            if result["backlog_unknown"]:
                details = f"{details}; backlog_remaining=unknown" if details else "backlog_remaining=unknown"
            self._log("pipeline", action, details, operation_id)
            return result

    def _log(self, stage: str, action: str, details=None, operation_id=None) -> None:
        self._processing_repository().log_processing(None, stage, action, details, operation_id)

    async def _run_automation_stages(self, operation_id: str) -> dict:
        failures: list[dict[str, str]] = []
        skipped: list[dict[str, str]] = []
        remaining_by_kind: dict[str, int] = {}
        backlog_unknown = False

        async def run_stage(stage: str, action):
            self._log(stage, "started", operation_id=operation_id)
            try:
                result = await asyncio.to_thread(action)
                if inspect.isawaitable(result):
                    result = await result
                self._log(stage, "completed", operation_id=operation_id)
                return True, result
            except Exception as exc:
                failures.append({"stage": stage, "error": str(exc), "type": type(exc).__name__})
                self._log(stage, "failed", str(exc), operation_id)
                logger.exception("operation_id=%s stage=%s status=failed", operation_id, stage)
                return False, None

        await run_stage("wait_scrapers", self._scraper_runs.wait_for_scrapers)
        runtime = self._automation_settings.get_runtime()
        max_review_batches = runtime["max_review_batches_per_cycle"]
        for content_kind in CONTENT_KINDS:
            await run_stage(
                f"cluster:{content_kind}",
                lambda kind=content_kind: self._event_clustering.auto_cluster_content(content_kind=kind),
            )
            blocklist_ok, _ = await run_stage(
                f"blocklist:{content_kind}",
                lambda kind=content_kind: self._content_transitions.apply_blocklist(
                    self._automation_settings.get_window(kind)["filter_hours"], kind
                ),
            )
            profiles = self._editorial_profile_repository().list_profiles(content_kind, enabled_only=True)
            if any((profile.get("review_prompt") or "").strip() for profile in profiles):
                if not blocklist_ok:
                    stage = f"review:{content_kind}"
                    skipped.append(
                        {"stage": stage, "reason": f"blocklist:{content_kind} failed"}
                    )
                    self._log(stage, "skipped", f"blocklist:{content_kind} failed", operation_id)
                    backlog_unknown = True
                    continue
                review_hours = self._automation_settings.get_window(content_kind)["ai_scoring_hours"]
                remaining = None
                for batch_number in range(1, max_review_batches + 1):
                    review_ok, result = await run_stage(
                        f"review:{content_kind}:batch:{batch_number}",
                        lambda kind=content_kind, hours=review_hours: self._ai_pipeline.run_content_review(hours, kind),
                    )
                    if not review_ok:
                        backlog_unknown = True
                        break
                    remaining = max(
                        int(result.get("remaining") or 0),
                        int(result.get("enrichment_remaining") or 0),
                    )
                    if remaining <= 0:
                        break
                if remaining is not None and remaining > 0:
                    remaining_by_kind[content_kind] = remaining
        await run_stage("delivery", self._publication_automation.run_cycle)
        if self._source_operations is not None:
            await run_stage("source_health", self._source_operations.snapshot_if_due)
        if self._market_intelligence is not None:
            await run_stage("market_windows", self._market_intelligence.refresh_due_events)
        logger.info("operation_id=%s status=completed", operation_id)
        return {
            "failures": failures,
            "skipped": skipped,
            "backlog_pending": bool(remaining_by_kind),
            "backlog_unknown": backlog_unknown,
            "remaining_by_kind": remaining_by_kind,
        }
