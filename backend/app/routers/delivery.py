from typing import Optional

from fastapi import APIRouter, Depends
from shared.content_contract import DELIVERY_OPERATION_STATUS_SENT

from ..composition import app_services
from ..core.response import APIEnvelope, APIResponse, ErrorEnvelope
from ..models.responses import DeliveryOperationData, PipelineActionData
from ..models.operations import DeliveryRetryRequest, DeliveryTriggerRequest, TelegramSendRequest
from ..models.config import TelegramConfigRequest
from .auth import get_current_user


router = APIRouter(responses={400: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}})


@router.post("/delivery/daily/news", response_model=APIEnvelope[PipelineActionData])
async def trigger_daily_push(request: DeliveryTriggerRequest, user: str = Depends(get_current_user)):
    return APIResponse.success(
        data=await app_services.daily_delivery.send_news(
            force=True, operation_key=request.operation_key
        )
    )


@router.post("/delivery/daily/article", response_model=APIEnvelope[PipelineActionData])
async def trigger_daily_article_push(request: DeliveryTriggerRequest, user: str = Depends(get_current_user)):
    return APIResponse.success(
        data=await app_services.daily_delivery.send_articles(
            force=True, operation_key=request.operation_key
        )
    )


@router.post("/delivery/test", response_model=APIEnvelope[None])
async def test_telegram_push(
    config: TelegramConfigRequest | None = None,
    user: str = Depends(get_current_user),
):
    payload = config.model_dump() if config is not None else None
    result = await app_services.telegram_gateway.send_test_message(payload)
    return APIResponse.success(message=result["message"])


@router.post("/delivery/send", response_model=APIEnvelope[DeliveryOperationData])
async def send_news_to_telegram(request: TelegramSendRequest, user: str = Depends(get_current_user)):
    result = await app_services.manual_entry_delivery.send(
        [entry.model_dump() for entry in request.entries], request.operation_key
    )
    message = (
        f"成功发送 {result['sent_count']} 条内容到 Telegram"
        if result["status"] == DELIVERY_OPERATION_STATUS_SENT
        else "交付尚未完整完成，请根据操作状态处理"
    )
    return APIResponse.success(message=message, data=result)


@router.post("/delivery/retry", response_model=APIEnvelope[DeliveryOperationData])
async def retry_delivery(request: DeliveryRetryRequest, user: str = Depends(get_current_user)):
    result = await app_services.delivery_retry.retry(request.operation_key)
    return APIResponse.success(message="已按用户确认重新尝试未完成分段", data=result)


@router.get("/delivery/operations", response_model=APIEnvelope[list[DeliveryOperationData]])
def list_delivery_operations(
    limit: int = 50,
    status: Optional[str] = None,
    user: str = Depends(get_current_user),
):
    return APIResponse.success(
        data=app_services.delivery_operations.list_operations(min(max(limit, 1), 200), status)
    )


@router.get("/delivery/operations/{operation_key}", response_model=APIEnvelope[DeliveryOperationData])
def get_delivery_operation(operation_key: str, user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.delivery_operations.get_operation(operation_key))
