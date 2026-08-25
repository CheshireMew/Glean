from __future__ import annotations

from fastapi import APIRouter, Depends

from ..composition import app_services
from ..core.response import APIEnvelope, APIResponse, ErrorEnvelope
from ..models.responses import BlacklistData, PipelineActionData, QueueMutationData
from ..models.operations import (
    AddBlacklistRequest,
    BlocklistRunRequest,
    CheckSimilarityRequest,
    ContentKind,
    EventClusterRequest,
    ReviewRunRequest,
)
from .auth import get_current_user

router = APIRouter(responses={400: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}})


@router.post("/content/events/cluster", response_model=APIEnvelope[PipelineActionData])
async def cluster_events(req: EventClusterRequest, user: str = Depends(get_current_user)):
    return APIResponse.success(
        data=await app_services.pipeline.cluster_content(req.time_window_hours, req.threshold, req.kind)
    )


@router.post("/content/events/check-similarity", response_model=APIEnvelope[PipelineActionData])
async def check_news_similarity(req: CheckSimilarityRequest, user: str = Depends(get_current_user)):
    return APIResponse.success(
        data=await app_services.event_clustering.check_event_similarity(req.news_id_1, req.news_id_2)
    )


@router.get("/content/blocklist", response_model=APIEnvelope[BlacklistData])
def get_blacklist(kind: ContentKind = "news", user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.blacklist.get_blacklist(kind))


@router.post("/content/blocklist", response_model=APIEnvelope[None])
def add_blacklist(req: AddBlacklistRequest, user: str = Depends(get_current_user)):
    return APIResponse.success(
        message=app_services.blacklist.add_blacklist(req.keyword, req.match_type, req.kind)["message"]
    )


@router.delete("/content/blocklist/{entry_id}", response_model=APIEnvelope[None])
def delete_blacklist(entry_id: int, user: str = Depends(get_current_user)):
    return APIResponse.success(message=app_services.blacklist.delete_blacklist(entry_id)["message"])


@router.post("/content/blocked/apply", response_model=APIEnvelope[PipelineActionData])
async def filter_news(req: BlocklistRunRequest, user: str = Depends(get_current_user)):
    return APIResponse.success(data=await app_services.pipeline.apply_blocklist(req.time_range_hours, req.kind))


@router.post("/content/review/run", response_model=APIEnvelope[PipelineActionData])
async def run_content_review(req: ReviewRunRequest, user: str = Depends(get_current_user)):
    return APIResponse.success(data=await app_services.pipeline.run_review(req.hours, req.kind))


@router.post("/content/review/{entry_id}/requeue", response_model=APIEnvelope[None])
def reset_review_item(entry_id: int, user: str = Depends(get_current_user)):
    return APIResponse.success(message=app_services.content_lifecycle.reset_review_item(entry_id)["message"])


@router.post("/content/review/requeue", response_model=APIEnvelope[QueueMutationData])
def reset_review_queue(kind: ContentKind = "news", user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.content_lifecycle.reset_review_queue(kind))


@router.post("/content/review/clear", response_model=APIEnvelope[QueueMutationData])
def clear_review_results(kind: ContentKind = "news", user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.content_lifecycle.clear_review_results(kind))


@router.post("/content/blocked/restore", response_model=APIEnvelope[QueueMutationData])
def restore_blocked_queue(kind: ContentKind = "news", user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.content_lifecycle.restore_blocked_queue(kind))
