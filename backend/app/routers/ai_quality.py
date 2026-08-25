from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..composition import app_services
from ..core.response import APIEnvelope, APIResponse, ErrorEnvelope
from ..models.intelligence import AIEvaluationCaseRequest, AIEvaluationRunRequest
from ..models.responses import (
    AIEvaluationCaseData,
    AIEvaluationRunData,
    AIInvocationData,
    AIQualitySummaryData,
)
from .auth import get_current_user


router = APIRouter(
    responses={400: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}}
)


@router.get("/ai-quality/summary", response_model=APIEnvelope[AIQualitySummaryData])
def get_ai_quality_summary(
    days: int = Query(default=30, ge=1, le=3650),
    user: str = Depends(get_current_user),
):
    return APIResponse.success(data=app_services.ai_quality.summary(days))


@router.get("/ai-quality/invocations", response_model=APIEnvelope[list[AIInvocationData]])
def list_ai_invocations(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    days: int = Query(default=30, ge=1, le=3650),
    stage: str | None = None,
    provider_name: str | None = None,
    profile_slug: str | None = None,
    success: bool | None = None,
    user: str = Depends(get_current_user),
):
    data = app_services.ai_quality.list_invocations(
        page, limit, days, stage, provider_name, profile_slug, success
    )
    return APIResponse.paginated(data["results"], data["total"], data["page"], data["limit"])


@router.get("/ai-quality/cases", response_model=APIEnvelope[list[AIEvaluationCaseData]])
def list_ai_evaluation_cases(
    enabled: bool | None = None,
    user: str = Depends(get_current_user),
):
    return APIResponse.success(data=app_services.ai_quality.list_cases(enabled))


@router.post("/ai-quality/cases", response_model=APIEnvelope[AIEvaluationCaseData])
def create_ai_evaluation_case(
    request: AIEvaluationCaseRequest,
    user: str = Depends(get_current_user),
):
    return APIResponse.success(data=app_services.ai_quality.save_case(request.model_dump()))


@router.put("/ai-quality/cases/{case_id}", response_model=APIEnvelope[AIEvaluationCaseData])
def update_ai_evaluation_case(
    case_id: int,
    request: AIEvaluationCaseRequest,
    user: str = Depends(get_current_user),
):
    return APIResponse.success(data=app_services.ai_quality.save_case(request.model_dump(), case_id))


@router.post("/ai-quality/runs", response_model=APIEnvelope[AIEvaluationRunData])
async def run_ai_evaluation(
    request: AIEvaluationRunRequest,
    user: str = Depends(get_current_user),
):
    return APIResponse.success(
        data=await app_services.ai_quality.run_evaluation(
            request.case_ids, request.provider_name
        )
    )


@router.get("/ai-quality/runs", response_model=APIEnvelope[list[dict]])
def list_ai_evaluation_runs(
    run_key: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    user: str = Depends(get_current_user),
):
    return APIResponse.success(data=app_services.ai_quality.list_runs(run_key, limit))
