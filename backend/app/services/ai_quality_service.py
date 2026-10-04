from __future__ import annotations

import uuid
from typing import Dict

from ..core.exceptions import NotFoundError, ValidationError
from .llm import EditorialAIService


class AIQualityService:
    def __init__(self, repository, ai_provider_settings, budget=None):
        self._repository = repository
        self._ai_provider_settings = ai_provider_settings
        self._budget = budget

    def summary(self, days: int) -> Dict:
        return self._repository().get_summary(days)

    def list_invocations(
        self,
        page: int,
        limit: int,
        days: int,
        stage: str | None,
        provider_name: str | None,
        profile_slug: str | None,
        success: bool | None,
    ) -> Dict:
        return self._repository().list_invocations(
            page, limit, days, stage, provider_name, profile_slug, success
        )

    def list_cases(self, enabled: bool | None = None) -> list[Dict]:
        return self._repository().list_evaluation_cases(enabled)

    def save_case(self, values: Dict, case_id: int | None = None) -> Dict:
        if values["stage"] == "review":
            required = {"title", "review_prompt"}
        else:
            required = {"title", "sources", "enrichment_prompt"}
        missing = sorted(required - set(values["input"]))
        if missing:
            raise ValidationError(f"评测输入缺少字段：{', '.join(missing)}")
        saved_id = self._repository().save_evaluation_case(values, case_id)
        if not saved_id:
            raise NotFoundError("评测样例不存在")
        return self._repository().get_evaluation_case(saved_id)

    @staticmethod
    def _evaluate(result: Dict, expected: Dict) -> tuple[bool, Dict]:
        checks: Dict[str, bool] = {}
        for key, value in expected.items():
            if key in {"score_min", "score_max", "required_nonempty"}:
                continue
            checks[f"equals:{key}"] = result.get(key) == value
        if "score_min" in expected:
            checks["score_min"] = float(result.get("score") or 0) >= float(expected["score_min"])
        if "score_max" in expected:
            checks["score_max"] = float(result.get("score") or 0) <= float(expected["score_max"])
        for field in expected.get("required_nonempty") or []:
            checks[f"nonempty:{field}"] = bool(result.get(field))
        return all(checks.values()) if checks else True, {"checks": checks}

    async def run_evaluation(
        self,
        case_ids: list[int] | None = None,
        provider_name: str | None = None,
    ) -> Dict:
        cases = self._repository().list_evaluation_cases(enabled=True)
        if case_ids is not None:
            requested = set(case_ids)
            cases = [case for case in cases if int(case["id"]) in requested]
        if not cases:
            raise ValidationError("没有可执行的评测样例")
        config = self._ai_provider_settings.get_config(include_secrets=True)
        providers = config.get("providers") or []
        if provider_name:
            providers = [provider for provider in providers if provider.get("name") == provider_name]
        if not providers:
            raise ValidationError("没有匹配的 AI 端点")
        telemetry: list[Dict] = []

        def observer(event: Dict) -> None:
            event = {**event, "stage": "evaluation"}
            telemetry.append(event)
            self._repository().record_invocation(event)

        service = EditorialAIService(providers, 1, config.get("throttle_seconds", 0), observer, self._budget)
        run_key = f"evaluation:{uuid.uuid4().hex}"
        results = []
        try:
            for case in cases:
                case_telemetry_start = len(telemetry)
                try:
                    inputs = case["input"]
                    context = {"operation_id": run_key, "stage": "evaluation"}
                    if case["stage"] == "review":
                        result = await service.review_event(
                            inputs["title"],
                            inputs["review_prompt"],
                            inputs.get("content", ""),
                            context,
                        )
                    else:
                        result = await service.enrich_event(
                            inputs["title"],
                            inputs["sources"],
                            inputs["enrichment_prompt"],
                            context,
                        )
                    passed, metrics = self._evaluate(result, case["expected"])
                    error = None
                except Exception as exc:
                    result = {}
                    passed = False
                    metrics = {"checks": {}, "error_type": type(exc).__name__}
                    error = str(exc)
                case_events = telemetry[case_telemetry_start:]
                successful = next((event for event in reversed(case_events) if event.get("success")), None)
                endpoint = successful or (case_events[-1] if case_events else {})
                self._repository().save_evaluation_run(
                    run_key,
                    case["id"],
                    endpoint.get("provider_name") or providers[0]["name"],
                    endpoint.get("model") or providers[0]["model"],
                    endpoint.get("prompt_version") or "unknown",
                    result,
                    {**metrics, "error": error},
                    passed,
                )
                results.append({
                    "case_id": case["id"],
                    "case_name": case["name"],
                    "passed": passed,
                    "result": result,
                    "metrics": metrics,
                    "error": error,
                })
        finally:
            await service.close()
        passed_count = sum(1 for result in results if result["passed"])
        return {
            "run_key": run_key,
            "total": len(results),
            "passed": passed_count,
            "failed": len(results) - passed_count,
            "results": results,
        }

    def list_runs(self, run_key: str | None, limit: int) -> list[Dict]:
        return self._repository().list_evaluation_runs(run_key, limit)
