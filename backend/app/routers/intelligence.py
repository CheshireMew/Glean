from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..composition import app_services
from ..core.response import APIEnvelope, APIResponse, ErrorEnvelope
from ..models.intelligence import (
    AlertPolicyRequest,
    EntityRequest,
    EventEntityAttachRequest,
    EventNarrativeAttachRequest,
    NarrativeRequest,
    WatchlistRequest,
)
from ..models.responses import AlertEvaluationData, AlertPolicyData, EntityData, EventDetailData, NarrativeData, WatchlistData
from .auth import get_current_user


router = APIRouter(responses={400: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}})


@router.get("/intelligence/entities", response_model=APIEnvelope[list[EntityData]])
def list_entities(entity_type: str | None = None, query: str | None = None, user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.intelligence_catalog.list_entities(entity_type, query))


@router.post("/intelligence/entities", response_model=APIEnvelope[EntityData])
def create_entity(request: EntityRequest, user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.intelligence_catalog.save_entity(request.model_dump()))


@router.put("/intelligence/entities/{entity_id}", response_model=APIEnvelope[EntityData])
def update_entity(entity_id: int, request: EntityRequest, user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.intelligence_catalog.save_entity(request.model_dump(), entity_id))


@router.post("/intelligence/events/{event_id}/entities", response_model=APIEnvelope[EventDetailData])
def attach_event_entity(event_id: int, request: EventEntityAttachRequest, user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.intelligence_catalog.attach_entity(event_id, request.model_dump()))


@router.get("/intelligence/narratives", response_model=APIEnvelope[list[NarrativeData]])
def list_narratives(user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.intelligence_catalog.list_narratives())


@router.post("/intelligence/narratives", response_model=APIEnvelope[NarrativeData])
def create_narrative(request: NarrativeRequest, user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.intelligence_catalog.save_narrative(request.model_dump()))


@router.put("/intelligence/narratives/{narrative_id}", response_model=APIEnvelope[NarrativeData])
def update_narrative(narrative_id: int, request: NarrativeRequest, user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.intelligence_catalog.save_narrative(request.model_dump(), narrative_id))


@router.post("/intelligence/events/{event_id}/narratives", response_model=APIEnvelope[EventDetailData])
def attach_event_narrative(event_id: int, request: EventNarrativeAttachRequest, user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.intelligence_catalog.attach_narrative(event_id, request.model_dump()))


@router.post("/intelligence/events/{event_id}/classify", response_model=APIEnvelope[dict])
def classify_event(event_id: int, user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.intelligence_catalog.classify_event(event_id))


@router.post("/intelligence/classify", response_model=APIEnvelope[dict])
def classify_recent_events(
    hours: int = Query(default=168, ge=1, le=8760),
    limit: int = Query(default=500, ge=1, le=5000),
    user: str = Depends(get_current_user),
):
    return APIResponse.success(data=app_services.intelligence_catalog.classify_recent(hours, limit))


@router.get("/intelligence/watchlists", response_model=APIEnvelope[list[WatchlistData]])
def list_watchlists(user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.intelligence_catalog.list_watchlists())


@router.post("/intelligence/watchlists", response_model=APIEnvelope[WatchlistData])
def create_watchlist(request: WatchlistRequest, user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.intelligence_catalog.save_watchlist(request.model_dump()))


@router.put("/intelligence/watchlists/{watchlist_id}", response_model=APIEnvelope[WatchlistData])
def update_watchlist(watchlist_id: int, request: WatchlistRequest, user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.intelligence_catalog.save_watchlist(request.model_dump(), watchlist_id))


@router.get("/intelligence/alerts", response_model=APIEnvelope[list[AlertPolicyData]])
def list_alert_policies(user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.intelligence_catalog.list_alert_policies())


@router.post("/intelligence/alerts", response_model=APIEnvelope[AlertPolicyData])
def create_alert_policy(request: AlertPolicyRequest, user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.intelligence_catalog.save_alert_policy(request.model_dump()))


@router.put("/intelligence/alerts/{policy_id}", response_model=APIEnvelope[AlertPolicyData])
def update_alert_policy(policy_id: int, request: AlertPolicyRequest, user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.intelligence_catalog.save_alert_policy(request.model_dump(), policy_id))


@router.post("/intelligence/alerts/evaluate", response_model=APIEnvelope[AlertEvaluationData])
def evaluate_alert_policies(policy_id: int | None = None, hours: int = Query(default=24, ge=1, le=720), user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.intelligence_catalog.evaluate_alerts(policy_id, hours))


@router.get("/intelligence/alert-matches", response_model=APIEnvelope[list[dict]])
def list_alert_matches(status: str | None = None, limit: int = Query(default=200, ge=1, le=1000), user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.intelligence_catalog.list_alert_matches(status, limit))
