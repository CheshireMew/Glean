from typing import Optional

from fastapi import APIRouter, Header, Query
from fastapi.responses import Response

from shared.content_contract import CONTENT_KINDS, PUBLIC_STREAM_MAP, ContentKind, SearchKind

from ..composition import app_services
from ..core.exceptions import ValidationError
from ..core.response import APIEnvelope, APIResponse, ErrorEnvelope
from ..models.responses import ContentItem, EntityData, EventDetailData, NarrativeData, PublicContentData, PublicReportsData, PublicSiteConfigData


router = APIRouter(responses={400: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}})


@router.get("/public/config", response_model=APIEnvelope[PublicSiteConfigData])
def get_public_config():
    return APIResponse.success(data=app_services.public_content.get_public_config())


@router.get("/public/content", response_model=APIEnvelope[PublicContentData])
def get_public_content(
    stream: str,
    limit: int = Query(default=20, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(default=None, max_length=512),
    known_revision: str | None = Query(default=None, max_length=128),
    publication: str | None = Query(default=None, max_length=100),
):
    kind = PUBLIC_STREAM_MAP.get(stream)
    if not kind:
        raise ValidationError("未知公开流类型")
    return APIResponse.success(
        data=app_services.public_content.get_public_content(
            kind, limit, offset, cursor, known_revision, publication
        )
    )


@router.get("/public/reports", response_model=APIEnvelope[PublicReportsData])
def get_public_reports(
    kind: Optional[ContentKind] = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    query: str | None = Query(default=None, max_length=200),
    publication: str | None = Query(default=None, max_length=100),
):
    return APIResponse.success(
        data=app_services.public_content.get_public_reports(kind, limit, offset, query, publication)
    )


@router.get(
    "/public/rss.xml",
    response_class=Response,
    response_model=None,
    responses={
        200: {
            "description": "RSS 2.0 XML",
            "content": {"application/rss+xml": {"schema": {"type": "string"}}},
        }
    },
)
def get_public_rss(
    kind: ContentKind = "news",
    limit: int = Query(default=20, ge=1, le=100),
    publication: str | None = Query(default=None, max_length=100),
):
    if kind not in CONTENT_KINDS:
        raise ValidationError("未知公开流类型")
    return Response(
        app_services.public_content.build_public_rss(kind, limit, publication),
        media_type="application/rss+xml; charset=utf-8",
    )


@router.get("/public/search", response_model=APIEnvelope[PublicContentData])
def search_public_content(
    query: str = Query(min_length=1, max_length=200),
    kind: SearchKind = "all",
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    publication: str | None = Query(default=None, max_length=100),
):
    if not query or len(query.strip()) < 1:
        raise ValidationError("搜索关键词不能为空")
    return APIResponse.success(
        data=app_services.public_content.search_public_content(query, kind, limit, offset, publication)
    )


@router.get("/public/events/{event_id}", response_model=APIEnvelope[EventDetailData])
def get_public_event(event_id: int):
    detail = app_services.event_intelligence.get_detail(event_id, public_only=True)
    detail["markets"] = app_services.market_intelligence.get_event_market(event_id)["markets"]
    return APIResponse.success(data=detail)


@router.get("/public/entities/{slug}", response_model=APIEnvelope[EntityData])
def get_public_entity(
    slug: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return APIResponse.success(data=app_services.intelligence_catalog.get_public_entity(slug, limit, offset))


@router.get("/public/narratives/{slug}", response_model=APIEnvelope[NarrativeData])
def get_public_narrative(
    slug: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return APIResponse.success(data=app_services.intelligence_catalog.get_public_narrative(slug, limit, offset))


@router.get("/analyst/news", response_model=APIEnvelope[list[ContentItem]])
def get_analyst_news(
    kind: ContentKind = "news",
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    x_api_key: str = Header(alias="X-API-Key", min_length=16),
):
    app_services.analyst_access.authenticate(x_api_key)
    data = app_services.content.list_review_decisions("selected", page, limit, None, None, kind)
    return APIResponse.paginated(data["results"], data["total"], data["page"], data["limit"])


@router.get("/analyst/events", response_model=APIEnvelope[list[EventDetailData]])
def list_analyst_events(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    kind: ContentKind | None = None,
    updated_after: str | None = Query(default=None, max_length=64),
    x_api_key: str = Header(alias="X-API-Key", min_length=16),
):
    data = app_services.analyst_data.list_events(x_api_key, page, limit, kind, updated_after)
    return APIResponse.paginated(data["items"], data["total"], data["page"], data["limit"])


@router.get("/analyst/events/{event_id}", response_model=APIEnvelope[EventDetailData])
def get_analyst_event(event_id: int, x_api_key: str = Header(alias="X-API-Key", min_length=16)):
    from ..core.exceptions import NotFoundError
    detail = app_services.analyst_data.get_event(x_api_key, event_id)
    if not detail:
        raise NotFoundError("事件不存在")
    return APIResponse.success(data=detail)


@router.get("/analyst/entities", response_model=APIEnvelope[list[EntityData]])
def list_analyst_entities(
    entity_type: str | None = None,
    query: str | None = Query(default=None, max_length=200),
    x_api_key: str = Header(alias="X-API-Key", min_length=16),
):
    return APIResponse.success(data=app_services.analyst_data.list_entities(x_api_key, entity_type, query))


@router.get("/analyst/narratives", response_model=APIEnvelope[list[NarrativeData]])
def list_analyst_narratives(x_api_key: str = Header(alias="X-API-Key", min_length=16)):
    return APIResponse.success(data=app_services.analyst_data.list_narratives(x_api_key))


@router.get("/analyst/tags", response_model=APIEnvelope[list[dict]])
def list_analyst_tags(x_api_key: str = Header(alias="X-API-Key", min_length=16)):
    return APIResponse.success(data=app_services.analyst_data.list_tags(x_api_key))


@router.get("/analyst/delta", response_model=APIEnvelope[dict])
def get_analyst_delta(
    since: str = Query(min_length=10, max_length=64),
    limit: int = Query(default=200, ge=1, le=1000),
    x_api_key: str = Header(alias="X-API-Key", min_length=16),
):
    return APIResponse.success(data=app_services.analyst_data.delta(x_api_key, since, limit))
