from __future__ import annotations

from fastapi import APIRouter, Depends

from ..composition import app_services
from ..core.response import APIEnvelope, APIResponse, ErrorEnvelope
from ..models.intelligence import MarketExpectationRequest, MarketInstrumentRequest, MarketSnapshotRequest
from ..models.responses import EventMarketData, MarketInstrumentData
from .auth import get_current_user


router = APIRouter(responses={400: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}})


@router.get("/market/instruments", response_model=APIEnvelope[list[MarketInstrumentData]])
def list_instruments(user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.market_intelligence.list_instruments())


@router.post("/market/instruments", response_model=APIEnvelope[MarketInstrumentData])
def create_instrument(request: MarketInstrumentRequest, user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.market_intelligence.save_instrument(request.model_dump()))


@router.put("/market/instruments/{instrument_id}", response_model=APIEnvelope[MarketInstrumentData])
def update_instrument(instrument_id: int, request: MarketInstrumentRequest, user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.market_intelligence.save_instrument(request.model_dump(), instrument_id))


@router.get("/market/events/{event_id}", response_model=APIEnvelope[EventMarketData])
def get_event_market(event_id: int, user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.market_intelligence.get_event_market(event_id))


@router.post("/market/events/{event_id}/refresh", response_model=APIEnvelope[EventMarketData])
async def refresh_event_market(event_id: int, user: str = Depends(get_current_user)):
    return APIResponse.success(data=await app_services.market_intelligence.refresh_event(event_id))


@router.put("/market/events/{event_id}/instruments/{instrument_id}/snapshot", response_model=APIEnvelope[dict])
def save_snapshot(event_id: int, instrument_id: int, request: MarketSnapshotRequest, user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.market_intelligence.save_snapshot(event_id, instrument_id, request.model_dump()))


@router.put("/market/events/{event_id}/instruments/{instrument_id}/expectation", response_model=APIEnvelope[dict])
def save_expectation(event_id: int, instrument_id: int, request: MarketExpectationRequest, user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.market_intelligence.save_expectation(event_id, instrument_id, request.model_dump()))
