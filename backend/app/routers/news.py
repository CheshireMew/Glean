from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from shared.content_contract import ContentKind, ExportScope, EXPORT_SCOPE_INCOMING, ReviewDecision
from ..core.exceptions import NotFoundError
from ..core.response import APIEnvelope, APIResponse, ErrorEnvelope
from ..models.responses import ContentItem, DashboardOverviewData, EventGroupsData, SourceStatsData
from ..composition import app_services
from .auth import get_current_user

router = APIRouter(responses={400: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}})


@router.get("/content/overview", response_model=APIEnvelope[DashboardOverviewData])
def get_content_overview(kind: ContentKind = "news", user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.content.get_dashboard_overview(kind))


@router.get("/content/stats", response_model=APIEnvelope[SourceStatsData])
def get_content_stats(kind: ContentKind = "news", user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.content.get_source_stats(kind), message="统计查询成功")


@router.get("/content/incoming", response_model=APIEnvelope[list[ContentItem]])
def get_incoming_content(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    source: Optional[str] = None,
    keyword: Optional[str] = None,
    kind: ContentKind = "news",
    user: str = Depends(get_current_user),
):
    data = app_services.content.list_incoming(page, limit, source, keyword, kind)
    return APIResponse.paginated(data=data["results"], total=data["total"], page=data["page"], limit=data["limit"])


@router.get("/content/events", response_model=APIEnvelope[EventGroupsData])
def get_content_events(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    source: Optional[str] = None,
    keyword: Optional[str] = None,
    kind: ContentKind = "news",
    user: str = Depends(get_current_user),
):
    return APIResponse.success(data=app_services.content.list_source_groups(page, limit, source, keyword, kind))


@router.delete("/content/source/{entry_id}", response_model=APIEnvelope[None])
def delete_source_content(entry_id: int, user: str = Depends(get_current_user)):
    if not app_services.content_lifecycle.delete_incoming_entry(entry_id):
        raise NotFoundError("内容不存在")
    return APIResponse.success(message="删除成功")


@router.get("/content/archive", response_model=APIEnvelope[list[ContentItem]])
def get_archive_content(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    source: Optional[str] = None,
    keyword: Optional[str] = None,
    kind: ContentKind = "news",
    user: str = Depends(get_current_user),
):
    data = app_services.content.list_archive(page, limit, source, keyword, kind)
    return APIResponse.paginated(data=data["results"], total=data["total"], page=data["page"], limit=data["limit"])


@router.delete("/content/archive/{entry_id}", response_model=APIEnvelope[None])
def delete_archive_entry(entry_id: int, user: str = Depends(get_current_user)):
    if not app_services.content_lifecycle.delete_archive_entry(entry_id):
        raise NotFoundError("内容不存在")
    return APIResponse.success(message="删除成功")


@router.get("/content/blocked", response_model=APIEnvelope[list[ContentItem]])
def get_blocked_content(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    keyword: Optional[str] = None,
    kind: ContentKind = "news",
    user: str = Depends(get_current_user),
):
    data = app_services.content.list_blocked(page, limit, keyword, kind)
    return APIResponse.paginated(data=data["results"], total=data["total"], page=data["page"], limit=data["limit"])


@router.get("/content/review", response_model=APIEnvelope[list[ContentItem]])
def get_review_queue(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    source: Optional[str] = None,
    keyword: Optional[str] = None,
    kind: ContentKind = "news",
    user: str = Depends(get_current_user),
):
    data = app_services.content.list_review_queue(page, limit, source, keyword, kind)
    return APIResponse.paginated(data=data["results"], total=data["total"], page=data["page"], limit=data["limit"])


@router.get("/content/decisions", response_model=APIEnvelope[list[ContentItem]])
def get_review_decisions(
    decision: ReviewDecision,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    source: Optional[str] = None,
    keyword: Optional[str] = None,
    kind: ContentKind = "news",
    user: str = Depends(get_current_user),
):
    data = app_services.content.list_review_decisions(decision, page, limit, source, keyword, kind)
    return APIResponse.paginated(data=data["results"], total=data["total"], page=data["page"], limit=data["limit"])


@router.delete("/content/review/{entry_id}", response_model=APIEnvelope[None])
def delete_review_entry(entry_id: int, user: str = Depends(get_current_user)):
    if not app_services.content_lifecycle.delete_review_entry(entry_id):
        raise NotFoundError("内容不存在")
    return APIResponse.success(message="删除成功")


@router.post("/content/archive/{entry_id}/restore", response_model=APIEnvelope[None])
def restore_archive_entry(entry_id: int, user: str = Depends(get_current_user)):
    if not app_services.content_lifecycle.restore_archive_entry(entry_id):
        raise NotFoundError("内容不存在")
    return APIResponse.success(message="已恢复到采集池")


@router.post("/content/blocked/{entry_id}/restore", response_model=APIEnvelope[None])
def restore_blocked_entry(entry_id: int, user: str = Depends(get_current_user)):
    if not app_services.content_lifecycle.restore_blocked_entry(entry_id):
        raise NotFoundError("内容不存在")
    return APIResponse.success(message="已恢复到归档池")


@router.get(
    "/content/export",
    response_class=StreamingResponse,
    response_model=None,
    responses={
        200: {
            "description": "流式 JSON 数组导出",
            "content": {"application/json": {"schema": {"type": "array", "items": {"type": "object"}}}},
        }
    },
)
def export_content(
    scope: ExportScope = EXPORT_SCOPE_INCOMING,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    keyword: Optional[str] = None,
    source: Optional[str] = None,
    kind: Optional[ContentKind] = None,
    fields: Optional[str] = None,
    user: str = Depends(get_current_user),
):
    payload = app_services.content.stream_export_content(scope, start_date, end_date, keyword, source, kind, fields)

    def iter_json():
        import json

        yield "["
        for index, item in enumerate(payload):
            if index > 0:
                yield ","
            yield json.dumps(item, default=str, ensure_ascii=False)
        yield "]"

    return StreamingResponse(
        iter_json(),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={app_services.content.get_export_filename()}"},
    )
