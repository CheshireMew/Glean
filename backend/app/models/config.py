
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from shared.content_contract import ContentKind



class SystemTimezoneConfig(BaseModel):
    timezone: str


class DeliveryScheduleConfig(BaseModel):
    news_time: str | None = None
    article_time: str | None = None


class AutomationWindowConfig(BaseModel):
    cluster_hours: int | None = Field(default=None, ge=1, le=720)
    cluster_window_hours: int | None = Field(default=None, ge=1, le=720)
    filter_hours: int | None = Field(default=None, ge=1, le=720)
    ai_scoring_hours: int | None = Field(default=None, ge=1, le=720)
    push_hours: int | None = Field(default=None, ge=1, le=720)


class AutomationRuntimeConfig(BaseModel):
    enabled: bool | None = None
    start_time: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end_time: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    interval_minutes: int | None = Field(default=None, ge=5, le=1440)
    review_batch_size: int | None = Field(default=None, ge=1, le=500)
    enrichment_batch_size: int | None = Field(default=None, ge=1, le=500)
    max_review_batches_per_cycle: int | None = Field(default=None, ge=1, le=100)
    backlog_retry_seconds: int | None = Field(default=None, ge=5, le=3600)
    scraper_concurrency: int | None = Field(default=None, ge=1, le=8)
    maintenance_interval_hours: int | None = Field(default=None, ge=1, le=168)
    operational_retention_days: int | None = Field(default=None, ge=7, le=365)
    content_retention_days: int | None = Field(default=None, ge=30, le=3650)


class AutomationConfigRequest(BaseModel):
    news: AutomationWindowConfig | None = None
    article: AutomationWindowConfig | None = None
    runtime: AutomationRuntimeConfig | None = None


class SystemSettingsRequest(BaseModel):
    timezone: str
    automation: AutomationConfigRequest
    delivery: DeliveryScheduleConfig


class TelegramConfigRequest(BaseModel):
    bot_token: str
    chat_id: str
    enabled: bool = False


class AIEndpointRequest(BaseModel):
    name: str
    api_key: str
    base_url: str
    model: str
    input_price_per_million: float = Field(default=0, ge=0, le=10000)
    output_price_per_million: float = Field(default=0, ge=0, le=10000)


class AIProviderConfigRequest(BaseModel):
    providers: list[AIEndpointRequest]
    analysis_concurrency: int = Field(default=3, ge=1, le=20)
    enrichment_concurrency: int = Field(default=2, ge=1, le=10)
    throttle_seconds: float = Field(default=0, ge=0, le=60)


class EditorialProfileRequest(BaseModel):
    slug: str
    name: str
    content_type: ContentKind
    review_prompt: str = ""
    enrichment_prompt: str = ""
    min_score: int = Field(default=5, ge=1, le=10)
    max_items: int = Field(default=12, ge=1, le=100)
    max_per_category: int = Field(default=4, ge=1, le=100)
    max_per_source: int = Field(default=4, ge=1, le=100)
    enabled: bool = True
    is_default: bool = False


class AIReviewConfigRequest(BaseModel):
    prompt: str | None = None
    hours: int | None = Field(default=8, ge=1, le=720)


class RssPreviewRequest(BaseModel):
    feed_url: str
    parser_type: Literal["generic", "summary_source_link"] = "generic"
    limit: int = Field(default=3, ge=1, le=5)


class RssSourceRequest(BaseModel):
    slug: str | None = None
    display_name: str
    feed_url: str
    site_url: str
    content_kind: ContentKind = "article"
    parser_type: Literal["generic", "summary_source_link"] = "generic"
    default_limit: int = Field(default=20, ge=1, le=100)
    default_interval: int = Field(default=240, ge=5, le=10080)
    enabled: bool = True
