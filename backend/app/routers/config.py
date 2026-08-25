from __future__ import annotations

from fastapi import APIRouter, Depends

from ..core.response import APIEnvelope, APIResponse, ErrorEnvelope
from ..composition import app_services
from ..models.config import (
    AIProviderConfigRequest,
    AIReviewConfigRequest,
    AutomationConfigRequest,
    ContentKind,
    DeliveryScheduleConfig,
    EditorialProfileRequest,
    RssSourceRequest,
    SystemSettingsRequest,
    SystemTimezoneConfig,
    TelegramConfigRequest,
)
from .auth import get_current_user
from ..models.responses import (
    AIProviderConfigData,
    AutomationConfigData,
    DeliveryScheduleData,
    EditorialProfileData,
    EditorialProfilesData,
    ReviewSettingsData,
    RssSourceData,
    RssSourcesData,
    TelegramConfigData,
    TimezoneData,
)

router = APIRouter(responses={400: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}, 500: {"model": ErrorEnvelope}})


@router.get("/system/timezone", response_model=APIEnvelope[TimezoneData])
def get_system_timezone(user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.system_settings.get_timezone())


@router.post("/system/timezone", response_model=APIEnvelope[None])
def set_system_timezone(config: SystemTimezoneConfig, user: str = Depends(get_current_user)):
    result = app_services.system_settings.set_timezone(config.timezone)
    return APIResponse.success(message=result["message"])


@router.post("/system/settings", response_model=APIEnvelope[None])
def set_system_settings(config: SystemSettingsRequest, user: str = Depends(get_current_user)):
    result = app_services.system_configuration.save(
        config.timezone,
        config.automation.model_dump(),
        config.delivery.news_time,
        config.delivery.article_time,
    )
    return APIResponse.success(message=result["message"])


@router.get("/delivery/schedule", response_model=APIEnvelope[DeliveryScheduleData])
def get_delivery_schedule(user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.delivery_settings.get_schedule())


@router.post("/delivery/schedule", response_model=APIEnvelope[None])
def set_delivery_schedule(config: DeliveryScheduleConfig, user: str = Depends(get_current_user)):
    result = app_services.delivery_settings.set_schedule(config.news_time, config.article_time)
    return APIResponse.success(message=result["message"])


@router.get("/config/automation", response_model=APIEnvelope[AutomationConfigData])
def get_automation_config(user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.automation_settings.get_config())


@router.post("/config/automation", response_model=APIEnvelope[None])
def set_automation_config(req: AutomationConfigRequest, user: str = Depends(get_current_user)):
    result = app_services.automation_settings.set_config(req.model_dump())
    return APIResponse.success(message=result["message"])


@router.get("/integration/telegram", response_model=APIEnvelope[TelegramConfigData])
def get_telegram_config(user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.telegram_settings.get_config())


@router.post("/integration/telegram", response_model=APIEnvelope[None])
def set_telegram_config(config: TelegramConfigRequest, user: str = Depends(get_current_user)):
    return APIResponse.success(message=app_services.telegram_settings.set_config(config.model_dump())["message"])


@router.get("/integration/ai", response_model=APIEnvelope[AIProviderConfigData])
def get_ai_provider_config(user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.ai_provider_settings.get_config())


@router.post("/integration/ai", response_model=APIEnvelope[None])
def set_ai_provider_config(config: AIProviderConfigRequest, user: str = Depends(get_current_user)):
    return APIResponse.success(message=app_services.ai_provider_settings.set_config(config.model_dump())["message"])


@router.get("/editorial/profiles", response_model=APIEnvelope[EditorialProfilesData])
def list_editorial_profiles(kind: ContentKind | None = None, user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.editorial_profiles.list_profiles(kind))


@router.put("/editorial/profiles/{slug}", response_model=APIEnvelope[EditorialProfileData])
def save_editorial_profile(slug: str, config: EditorialProfileRequest, user: str = Depends(get_current_user)):
    payload = config.model_dump()
    payload["slug"] = slug
    return APIResponse.success(data=app_services.editorial_profiles.save_profile(payload), message="内容档案已保存")


@router.get("/review/settings", response_model=APIEnvelope[ReviewSettingsData])
def get_ai_review_config(kind: ContentKind = "news", user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.review_settings.get_config(kind))


@router.post("/review/settings", response_model=APIEnvelope[None])
def set_ai_review_config(config: AIReviewConfigRequest, kind: ContentKind = "news", user: str = Depends(get_current_user)):
    return APIResponse.success(message=app_services.review_settings.set_config(config.prompt, config.hours, kind)["message"])


@router.get("/rss/sources", response_model=APIEnvelope[RssSourcesData])
def get_rss_sources(user: str = Depends(get_current_user)):
    return APIResponse.success(data=app_services.rss_sources.list_sources())


@router.post("/rss/sources", response_model=APIEnvelope[RssSourceData])
def create_rss_source(config: RssSourceRequest, user: str = Depends(get_current_user)):
    return APIResponse.success(message="RSS 源已创建", data=app_services.rss_sources.create_source(config.model_dump()))


@router.put("/rss/sources/{source_id}", response_model=APIEnvelope[RssSourceData])
def update_rss_source(source_id: int, config: RssSourceRequest, user: str = Depends(get_current_user)):
    return APIResponse.success(message="RSS 源已更新", data=app_services.rss_sources.update_source(source_id, config.model_dump()))


@router.delete("/rss/sources/{source_id}", response_model=APIEnvelope[None])
def delete_rss_source(source_id: int, user: str = Depends(get_current_user)):
    return APIResponse.success(message=app_services.rss_sources.delete_source(source_id)["message"])
