from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..composition import app_services
from ..core.response import APIEnvelope, APIResponse, ErrorEnvelope
from ..models.intelligence import SourceCatalogUpdateRequest, SourceIncidentUpdateRequest
from ..models.responses import SourceCatalogData, SourceHealthRunData, SourceIncidentData
from .auth import get_current_user


router = APIRouter(responses={400: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}})


@router.get("/source-operations/sources", response_model=APIEnvelope[list[SourceCatalogData]])
def list_sources(user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.source_operations.list_sources())


@router.post("/source-operations/sync", response_model=APIEnvelope[dict])
def sync_sources(user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.source_operations.sync_catalog())


@router.patch("/source-operations/sources/{source_key}", response_model=APIEnvelope[SourceCatalogData])
def update_source(source_key: str, request: SourceCatalogUpdateRequest, user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.source_operations.update_source(source_key, request.model_dump(exclude_unset=True)))


@router.post("/source-operations/health/snapshot", response_model=APIEnvelope[SourceHealthRunData])
def snapshot_health(source_key: str | None = None, hours: int = Query(default=24, ge=1, le=720), user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.source_operations.snapshot(source_key, hours))


@router.get("/source-operations/health", response_model=APIEnvelope[list[dict]])
def list_health(source_key: str | None = None, limit: int = Query(default=200, ge=1, le=2000), user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.source_operations.list_health(source_key, limit))


@router.get("/source-operations/incidents", response_model=APIEnvelope[list[SourceIncidentData]])
def list_incidents(status: str | None = None, limit: int = Query(default=200, ge=1, le=2000), user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.source_operations.list_incidents(status, limit))


@router.patch("/source-operations/incidents/{incident_id}", response_model=APIEnvelope[SourceIncidentData])
def update_incident(incident_id: int, request: SourceIncidentUpdateRequest, user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.source_operations.update_incident(incident_id, request.status))
