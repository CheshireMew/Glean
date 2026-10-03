from fastapi import APIRouter, Depends, Query

from ..composition import app_services
from ..core.response import APIEnvelope, APIResponse
from ..models.wechat import WechatSourceRequest, WechatSourceSettings
from .auth import get_current_user

router = APIRouter(prefix='/wechat', dependencies=[Depends(get_current_user)])


@router.get('/status', response_model=APIEnvelope[dict])
def get_wechat_status():
    runtime = app_services.automation_settings.get_runtime()
    return APIResponse.success(data={**app_services.wechat_sources.status(),
        'automation': {key: runtime[key] for key in ('enabled', 'start_time', 'end_time')}})


@router.post('/login', response_model=APIEnvelope[dict])
def start_wechat_login():
    return APIResponse.success(data=app_services.wechat_sources.start_login())


@router.post('/login/cancel', response_model=APIEnvelope[dict])
async def cancel_wechat_login():
    return APIResponse.success(data=await app_services.wechat_sources.cancel_login())


@router.post('/disconnect', response_model=APIEnvelope[dict])
async def disconnect_wechat():
    return APIResponse.success(data=await app_services.wechat_sources.disconnect())


@router.get('/search', response_model=APIEnvelope[dict])
async def search_wechat_accounts(query: str = Query(min_length=1, max_length=80),
                                 begin: int = Query(default=0, ge=0, le=100)):
    return APIResponse.success(data=await app_services.wechat_gateway.search(query.strip(), begin))


@router.get('/sources', response_model=APIEnvelope[dict])
def get_wechat_sources():
    return APIResponse.success(data={'sources': app_services.wechat_sources.list_sources()})


@router.post('/sources', response_model=APIEnvelope[dict])
def add_wechat_source(payload: WechatSourceRequest):
    return APIResponse.success(data=app_services.wechat_sources.add_source(payload.model_dump()))


@router.put('/sources/{source_id}', response_model=APIEnvelope[dict])
def update_wechat_source(source_id: int, payload: WechatSourceSettings):
    return APIResponse.success(data=app_services.wechat_sources.update_source(source_id, payload.model_dump()))
