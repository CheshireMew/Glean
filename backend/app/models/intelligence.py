from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shared.content_contract import ContentKind


class EditorialEditRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    review_summary: str | None = Field(default=None, max_length=10000)
    review_reason: str | None = Field(default=None, max_length=10000)
    review_score: int | None = Field(default=None, ge=0, le=10)
    review_category: str | None = Field(default=None, max_length=100)
    review_tags: list[str] | None = Field(default=None, max_length=100)
    enriched_summary: str | None = Field(default=None, max_length=30000)
    enriched_impact: str | None = Field(default=None, max_length=30000)
    enriched_background: str | None = Field(default=None, max_length=30000)
    enrichment_citations: list[dict] | None = Field(default=None, max_length=200)
    change_note: str | None = Field(default=None, max_length=1000)
    quality_score: int | None = Field(default=None, ge=1, le=5)


class EditorialFeedbackRequest(BaseModel):
    outcome: Literal["accepted", "edited", "rejected", "incorrect"]
    quality_score: int | None = Field(default=None, ge=1, le=5)
    changed_fields: list[str] = Field(default_factory=list, max_length=50)
    notes: str | None = Field(default=None, max_length=2000)
    invocation_id: int | None = Field(default=None, gt=0)


class EvidenceUpdateRequest(BaseModel):
    source_role: Literal["primary", "independent", "reporting", "repost", "commentary"] | None = None
    evidence_group: str | None = Field(default=None, max_length=200)
    origin_news_id: int | None = Field(default=None, gt=0)
    independence_score: float | None = Field(default=None, ge=0, le=1)
    verification_status: Literal["unverified", "verified", "disputed"] | None = None
    evidence_notes: str | None = Field(default=None, max_length=2000)


class EventUpdateRequest(BaseModel):
    update_type: Literal["development", "correction", "retraction", "context", "market"] = "development"
    title: str = Field(min_length=1, max_length=500)
    summary: str = Field(default="", max_length=10000)
    occurred_at: datetime
    source_news_id: int | None = Field(default=None, gt=0)
    is_public: bool = True


class EventUpdatePatchRequest(BaseModel):
    update_type: Literal["development", "correction", "retraction", "context", "market"] | None = None
    title: str | None = Field(default=None, min_length=1, max_length=500)
    summary: str | None = Field(default=None, max_length=10000)
    occurred_at: datetime | None = None
    source_news_id: int | None = Field(default=None, gt=0)
    is_public: bool | None = None


class EventFactRequest(BaseModel):
    fact_text: str = Field(min_length=1, max_length=5000)
    source_news_id: int | None = Field(default=None, gt=0)
    confidence: float = Field(default=1, ge=0, le=1)
    verification_status: Literal["unverified", "verified", "disputed"] = "unverified"
    is_public: bool = True


class EventFactPatchRequest(BaseModel):
    fact_text: str | None = Field(default=None, min_length=1, max_length=5000)
    source_news_id: int | None = Field(default=None, gt=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    verification_status: Literal["unverified", "verified", "disputed"] | None = None
    is_public: bool | None = None


class EventRelationRequest(BaseModel):
    related_event_id: int = Field(gt=0)
    relation_type: Literal[
        "related", "cause", "effect", "follow_up", "contradiction", "same_story"
    ] = "related"
    notes: str = Field(default="", max_length=5000)
    is_public: bool = True


class DraftItemRequest(BaseModel):
    review_entry_id: int = Field(gt=0)
    position: int | None = Field(default=None, ge=0)
    section: str = Field(default="其他", min_length=1, max_length=100)
    included: bool = True
    overrides: dict = Field(default_factory=dict)


class DraftCreateRequest(BaseModel):
    publication_id: int = Field(gt=0)
    content_type: ContentKind
    title: str = Field(min_length=1, max_length=500)
    items: list[DraftItemRequest] = Field(min_length=1, max_length=100)


class DraftUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    items: list[DraftItemRequest] | None = Field(default=None, min_length=1, max_length=100)
    scheduled_at: datetime | None = None
    status: Literal["draft", "scheduled", "cancelled"] | None = None

    @model_validator(mode="after")
    def validate_schedule(self):
        if self.status == "scheduled" and self.scheduled_at is None:
            raise ValueError("定时草稿必须提供 scheduled_at")
        return self


class CorrectionCreateRequest(BaseModel):
    correction_type: Literal["correction", "clarification", "retraction"]
    message: str = Field(min_length=1, max_length=10000)
    report_id: int | None = Field(default=None, gt=0)
    review_entry_id: int | None = Field(default=None, gt=0)
    event_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_target(self):
        if not any((self.report_id, self.review_entry_id, self.event_id)):
            raise ValueError("更正必须关联日报、内容或事件")
        return self


class AIEvaluationCaseRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    content_type: ContentKind
    stage: Literal["review", "enrichment"]
    input: dict
    expected: dict
    enabled: bool = True


class AIEvaluationRunRequest(BaseModel):
    case_ids: list[int] | None = Field(default=None, max_length=500)
    provider_name: str | None = Field(default=None, max_length=100)


class PublicationTargetRequest(BaseModel):
    channel_id: int = Field(gt=0)
    delivery_mode: Literal["realtime", "digest", "alert"]
    enabled: bool = True


class PublicationUpdateRequest(BaseModel):
    public_slug: str | None = Field(default=None, min_length=1, max_length=100)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    enabled: bool | None = None
    is_public: bool | None = None
    rss_enabled: bool | None = None
    digest_frequency: Literal["realtime", "daily", "weekly", "manual"] | None = None
    digest_time: str | None = Field(default=None, min_length=5, max_length=5)
    timezone: str | None = Field(default=None, max_length=100)
    template: dict | None = None
    targets: list[PublicationTargetRequest] | None = Field(default=None, max_length=100)


class PublicationChannelRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    channel_type: Literal["telegram", "email", "discord", "slack", "webhook"]
    enabled: bool = True
    config: dict = Field(default_factory=dict)


class EntityRequest(BaseModel):
    entity_type: Literal["asset", "protocol", "company", "person", "regulator", "exchange", "organization", "jurisdiction"]
    slug: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=300)
    symbol: str | None = Field(default=None, max_length=50)
    description: str = Field(default="", max_length=5000)
    aliases: list[str] = Field(default_factory=list, max_length=200)
    metadata: dict = Field(default_factory=dict)


class EventEntityAttachRequest(BaseModel):
    entity_id: int = Field(gt=0)
    role: Literal["subject", "actor", "affected", "location", "mentioned"] = "mentioned"
    confidence: float = Field(default=1, ge=0, le=1)
    source: Literal["manual", "ai", "rule"] = "manual"


class NarrativeRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=5000)
    keywords: list[str] = Field(default_factory=list, max_length=200)
    enabled: bool = True


class EventNarrativeAttachRequest(BaseModel):
    narrative_id: int = Field(gt=0)
    confidence: float = Field(default=1, ge=0, le=1)
    source: Literal["manual", "ai", "rule"] = "manual"


class WatchlistRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    enabled: bool = True
    visibility: Literal["private", "public"] = "private"
    entity_ids: list[int] = Field(default_factory=list, max_length=1000)
    narrative_ids: list[int] = Field(default_factory=list, max_length=1000)


class AlertConditions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_score: int = Field(default=0, ge=0, le=10)
    categories: list[str] = Field(default_factory=list, max_length=100)
    content_types: list[ContentKind] = Field(default_factory=list, max_length=2)
    min_independent_sources: int = Field(default=0, ge=0, le=1000)
    verified_only: bool = False
    source_sites: list[str] = Field(default_factory=list, max_length=500)
    keywords: list[str] = Field(default_factory=list, max_length=500)
    entity_ids: list[int] = Field(default_factory=list, max_length=1000)
    narrative_ids: list[int] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def validate_ids(self):
        if any(value <= 0 for value in (*self.entity_ids, *self.narrative_ids)):
            raise ValueError("实体和叙事 ID 必须大于 0")
        return self


class AlertQuietHours(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timezone: str | None = Field(default=None, max_length=100)
    start: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end: str | None = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    digest_time: str = Field(default="09:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    weekday: int = Field(default=0, ge=0, le=6)

    @model_validator(mode="after")
    def validate_timezone(self):
        if self.timezone:
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

            try:
                ZoneInfo(self.timezone)
            except ZoneInfoNotFoundError as exc:
                raise ValueError("提醒时区无效") from exc
        if (self.start is None) != (self.end is None):
            raise ValueError("静默时段必须同时提供 start 和 end")
        return self


class AlertPolicyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    enabled: bool = True
    watchlist_id: int | None = Field(default=None, gt=0)
    profile_slug: str | None = Field(default=None, max_length=120)
    conditions: AlertConditions = Field(default_factory=AlertConditions)
    schedule_type: Literal["instant", "daily", "weekly"] = "instant"
    quiet_hours: AlertQuietHours = Field(default_factory=AlertQuietHours)
    channel_id: int = Field(gt=0)


class SourceCatalogUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    authority_type: Literal["primary", "media", "aggregator", "commentary"] | None = None
    homepage_url: str | None = Field(default=None, max_length=2000)
    is_official: bool | None = None
    enabled: bool | None = None
    metadata: dict | None = None


class SourceIncidentUpdateRequest(BaseModel):
    status: Literal["open", "acknowledged", "resolved"]


class MarketInstrumentRequest(BaseModel):
    entity_id: int = Field(gt=0)
    provider: Literal["binance", "manual"]
    symbol: str = Field(min_length=1, max_length=50)
    quote_symbol: str = Field(default="USDT", min_length=1, max_length=20)
    enabled: bool = True
    metadata: dict = Field(default_factory=dict)


class MarketSnapshotRequest(BaseModel):
    observation_window: Literal["t-1h", "t0", "t+15m", "t+1h", "t+24h", "t+7d"]
    observed_at: datetime
    price: float | None = Field(default=None, gt=0)
    volume: float | None = Field(default=None, ge=0)
    funding_rate: float | None = None
    open_interest: float | None = Field(default=None, ge=0)
    metadata: dict = Field(default_factory=dict)


class MarketExpectationRequest(BaseModel):
    expected_direction: Literal["positive", "negative", "neutral", "uncertain"] | None = None
    expected_impact: str | None = Field(default=None, max_length=5000)
    confidence: float | None = Field(default=None, ge=0, le=1)
    metadata: dict = Field(default_factory=dict)


AnalystObjectType = Literal["event", "correction", "entity", "narrative", "tag"]


class AnalystSubscriptionCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    channel_id: int = Field(gt=0)
    enabled: bool = True
    object_types: list[AnalystObjectType] = Field(
        default_factory=lambda: ["event", "correction", "entity", "narrative", "tag"],
        min_length=1,
        max_length=5,
    )
    content_types: list[ContentKind] = Field(default_factory=list, max_length=2)
    profile_slugs: list[str] = Field(default_factory=list, max_length=100)
    batch_size: int = Field(default=50, ge=1, le=100)
    start_from: Literal["now", "beginning"] = "now"


class AnalystSubscriptionUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    channel_id: int | None = Field(default=None, gt=0)
    enabled: bool | None = None
    object_types: list[AnalystObjectType] | None = Field(default=None, min_length=1, max_length=5)
    content_types: list[ContentKind] | None = Field(default=None, max_length=2)
    profile_slugs: list[str] | None = Field(default=None, max_length=100)
    batch_size: int | None = Field(default=None, ge=1, le=100)
