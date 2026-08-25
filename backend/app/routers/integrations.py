from fastapi import APIRouter, Depends

from ..composition import app_services
from ..core.response import APIEnvelope, APIResponse, ErrorEnvelope
from ..models.responses import AIConnectionData, AnalystSubscriptionData, ApiKeyData
from ..models.intelligence import AnalystSubscriptionCreateRequest, AnalystSubscriptionUpdateRequest
from ..models.operations import ApiKeyCreateRequest, ApiKeyStatusRequest
from ..models.config import AIProviderConfigRequest
from .auth import get_current_user


router = APIRouter(responses={400: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}})


@router.post("/integration/analyst/keys", response_model=APIEnvelope[ApiKeyData])
async def create_api_key(request: ApiKeyCreateRequest, user: str = Depends(get_current_user)):
    result = await app_services.analyst_access.create_api_key(request.key_name, request.notes)
    return APIResponse.success(message=result["message"], data=result)


@router.get("/integration/analyst/keys", response_model=APIEnvelope[list[ApiKeyData]])
def get_analyst_api_keys(user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.analyst_access.get_api_keys())


@router.delete("/integration/analyst/keys/{key_id}", response_model=APIEnvelope[None])
async def delete_api_key(key_id: int, user: str = Depends(get_current_user)):
    result = await app_services.analyst_access.delete_api_key(key_id)
    return APIResponse.success(message=result["message"])


@router.patch("/integration/analyst/keys/{key_id}", response_model=APIEnvelope[None])
def set_api_key_status(key_id: int, request: ApiKeyStatusRequest, user: str = Depends(get_current_user)):
    result = app_services.analyst_access.set_api_key_enabled(key_id, request.enabled)
    return APIResponse.success(message=result["message"])


@router.get(
    "/integration/analyst/subscriptions",
    response_model=APIEnvelope[list[AnalystSubscriptionData]],
)
def list_analyst_subscriptions(user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.analyst_subscriptions.list_subscriptions())


@router.post(
    "/integration/analyst/subscriptions",
    response_model=APIEnvelope[AnalystSubscriptionData],
)
def create_analyst_subscription(
    request: AnalystSubscriptionCreateRequest, user: str = Depends(get_current_user)
):
    return APIResponse.success(data=app_services.analyst_subscriptions.create(request.model_dump()))


@router.put(
    "/integration/analyst/subscriptions/{subscription_id}",
    response_model=APIEnvelope[AnalystSubscriptionData],
)
def update_analyst_subscription(
    subscription_id: int,
    request: AnalystSubscriptionUpdateRequest,
    user: str = Depends(get_current_user),
):
    return APIResponse.success(
        data=app_services.analyst_subscriptions.update(
            subscription_id, request.model_dump(exclude_unset=True)
        )
    )


@router.post("/integration/analyst/subscriptions/deliver", response_model=APIEnvelope[dict])
async def deliver_analyst_subscriptions(user: str = Depends(get_current_user)):
    return APIResponse.success(data=await app_services.analyst_subscriptions.deliver())


@router.post("/integration/ai/test", response_model=APIEnvelope[AIConnectionData])
async def test_ai_connection(
    config: AIProviderConfigRequest | None = None,
    user: str = Depends(get_current_user),
):
    payload = config.model_dump() if config is not None else None
    return APIResponse.success(data=await app_services.ai_pipeline.test_ai_connection(payload))
