from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from shared.content_contract import ContentKind
from .config import AutomationRuntimeConfig, AutomationWindowConfig


class ExtensibleResponse(BaseModel):
    model_config = ConfigDict(extra="allow")


class AISourceData(BaseModel):
    key: str
    name: str
    site_url: str
    total: int
    last_collected_at: str | None


class AISourceItem(BaseModel):
    id: int
    title: str
    source_key: str
    source_site: str
    source_url: str
    source_excerpt: str
    original_title: str
    translated: bool
    published_at: str | None
    scraped_at: str | None
    author: str | None


class AIContentData(BaseModel):
    items: list[AISourceItem]
    sources: list[AISourceData]
    total: int
    limit: int
    offset: int


class AIRefreshSourceData(BaseModel):
    key: str
    name: str
    status: str
    message: str = ""


class AIRefreshData(BaseModel):
    updating: bool
    message: str = ""
    sources: list[AIRefreshSourceData]


class TokenData(BaseModel):
    access_token: str | None = None
    token_type: str
    csrf_token: str | None = None


class AuthSessionData(BaseModel):
    username: str
    csrf_token: str | None = None


class TimezoneData(BaseModel):
    timezone: str


class DeliveryScheduleData(BaseModel):
    news_time: str
    article_time: str


class AutomationConfigData(BaseModel):
    news: AutomationWindowConfig
    article: AutomationWindowConfig
    runtime: AutomationRuntimeConfig


class TelegramConfigData(BaseModel):
    bot_token: str
    has_bot_token: bool
    chat_id: str
    enabled: bool


class AIEndpointData(BaseModel):
    name: str
    api_key: str
    base_url: str
    model: str
    has_api_key: bool = False
    input_price_per_million: float = 0
    output_price_per_million: float = 0


class AIProviderConfigData(BaseModel):
    providers: list[AIEndpointData]
    analysis_concurrency: int
    enrichment_concurrency: int
    throttle_seconds: float


class EditorialProfileData(ExtensibleResponse):
    slug: str
    name: str
    content_type: ContentKind
    review_prompt: str
    enrichment_prompt: str
    min_score: int
    max_items: int
    max_per_category: int
    max_per_source: int
    enabled: bool
    is_default: bool


class EditorialProfilesData(BaseModel):
    profiles: list[EditorialProfileData]


class ReviewSettingsData(BaseModel):
    prompt: str
    hours: int
    kind: ContentKind
    profile_slug: str | None


class RssSourceData(ExtensibleResponse):
    id: int
    slug: str
    display_name: str
    feed_url: str
    site_url: str
    content_kind: ContentKind
    parser_type: str
    default_limit: int
    default_interval: int
    enabled: bool


class RssPreviewItem(BaseModel):
    title: str
    content: str
    url: str
    author: str
    published_at: str
    content_origin: str = "feed"
    completeness: str = "unknown"


class RssPreviewData(BaseModel):
    feed_url: str
    items: list[RssPreviewItem]
    notice: str


class RssSourcesData(BaseModel):
    sources: list[RssSourceData]


class DashboardOverviewData(BaseModel):
    incoming: int
    archive: int
    blocked: int
    review: int
    selected: int
    discarded: int


class SourceStat(BaseModel):
    source: str
    count: int


class SourceStatsData(BaseModel):
    stats: list[SourceStat]


class ContentItem(ExtensibleResponse):
    id: int | None = None
    title: str
    content: str | None = None
    source_site: str | None = None
    source_url: str
    published_at: str | None = None
    content_type: ContentKind | None = None


class EventSummary(BaseModel):
    multi_source: int
    single_source: int


class EventData(ExtensibleResponse):
    id: int
    title: str
    content: str | None = None
    published_at: str | None = None
    content_type: ContentKind | None = None


class EventGroup(ExtensibleResponse):
    event: EventData
    primary: ContentItem
    sources: list[ContentItem]
    alternatives: list[ContentItem]
    type: str


class EventGroupsData(BaseModel):
    results: list[EventGroup]
    total: int
    page: int
    limit: int
    summary: EventSummary


class EventDetailData(ExtensibleResponse):
    event: EventData
    sources: list[ContentItem]
    independent_source_count: int
    updates: list[dict]
    facts: list[dict]
    relations: list[dict]
    entities: list[dict]
    narratives: list[dict]
    reviews: list[dict]
    corrections: list[dict]


class EditorialEntryData(ExtensibleResponse):
    id: int
    title: str
    source_url: str
    revisions: list[dict]
    feedback: list[dict]


class PublicationDraftData(ExtensibleResponse):
    id: int
    draft_key: str
    title: str
    status: str
    items: list[dict] = Field(default_factory=list)


class PublicationDraftPreviewData(ExtensibleResponse):
    draft_id: int
    title: str
    content: str
    parts: list[str]
    items: list[str]
    target_count: int


class MutationResultData(ExtensibleResponse):
    id: int | None = None
    updated: bool | None = None


class KeywordData(ExtensibleResponse):
    id: int
    keyword: str
    match_type: str
    type: ContentKind


class BlacklistData(BaseModel):
    keywords: list[KeywordData]


class PipelineStats(ExtensibleResponse):
    scanned: int | None = None
    blocked: int | None = None
    review: int | None = None


class PipelineActionData(ExtensibleResponse):
    status: str | None = None
    message: str | None = None
    stats: PipelineStats | None = None
    remaining: int | None = None


class QueueMutationData(ExtensibleResponse):
    restored_count: int | None = None
    cleared_count: int | None = None


class PublicContentData(BaseModel):
    items: list[ContentItem]
    total: int
    limit: int
    offset: int
    next_cursor: str | None = None
    query: str | None = None
    revision: str | None = None
    not_modified: bool = False


class DailyReportData(ExtensibleResponse):
    id: int
    publication_key: str
    date: str
    type: ContentKind
    title: str
    content: str
    news_count: int
    created_at: str | None = None
    items: list[ContentItem]


class PublicReportsData(BaseModel):
    items: list[DailyReportData]
    total: int
    limit: int
    offset: int


class PublicSiteConfigData(BaseModel):
    site_url: str
    links: dict[str, str]
    publications: list[dict] = Field(default_factory=list)


class ScraperDefinitionData(BaseModel):
    name: str
    display_name: str
    source_site: str
    type: ContentKind
    source_type: str
    transport_kind: str


class ScrapersData(BaseModel):
    spiders: list[ScraperDefinitionData]


class ScraperRuntimeData(ExtensibleResponse):
    scraper_name: str | None = None
    status: str
    logs: list[str] = Field(default_factory=list)
    items_scraped: int = 0
    limit: int | None = None
    interval: int | None = None
    cooldown_until: float | None = None
    cooldown_reason: str | None = None
    configuration_error: str | None = None


class ScraperCommandData(ExtensibleResponse):
    command_id: int | None = None
    id: int | None = None
    scraper_name: str | None = None
    status: str | None = None
    message: str | None = None


class ScraperConfigData(BaseModel):
    status: str
    config: dict[str, int | str | None]


class DeliveryOperationData(ExtensibleResponse):
    operation_key: str
    status: str
    sent_count: int | None = None


class ApiKeyData(ExtensibleResponse):
    id: int
    key_name: str
    notes: str | None = None
    enabled: bool | None = None
    api_key: str | None = None


class AIConnectionData(ExtensibleResponse):
    ok: bool
    status: str | None = None
    message: str | None = None


class AIInvocationData(ExtensibleResponse):
    id: int
    stage: str
    provider_name: str
    model: str
    prompt_version: str
    success: bool
    started_at: str


class AIQualitySummaryData(ExtensibleResponse):
    days: int
    overall: dict
    groups: list[dict]
    feedback: list[dict]


class AIEvaluationCaseData(ExtensibleResponse):
    id: int
    name: str
    content_type: ContentKind
    stage: str
    input: dict
    expected: dict
    enabled: bool


class AIEvaluationRunData(ExtensibleResponse):
    run_key: str
    total: int
    passed: int
    failed: int
    results: list[dict]


class PublicationData(ExtensibleResponse):
    id: int
    profile_slug: str
    public_slug: str
    display_name: str
    content_type: ContentKind
    enabled: bool
    is_public: bool
    rss_enabled: bool
    targets: list[dict]


class PublicationChannelData(ExtensibleResponse):
    id: int
    slug: str
    name: str
    channel_type: str
    enabled: bool
    config: dict


class EntityData(ExtensibleResponse):
    id: int
    entity_type: str
    slug: str
    name: str
    symbol: str | None = None
    aliases: list[str]
    metadata: dict


class PublicEntityData(BaseModel):
    id: int
    entity_type: str
    slug: str
    name: str
    symbol: str | None = None
    description: str = ''
    events: dict


class NarrativeData(ExtensibleResponse):
    id: int
    slug: str
    name: str
    description: str
    keywords: list[str]
    enabled: bool


class AnalystSubscriptionData(ExtensibleResponse):
    id: int
    name: str
    channel_id: int
    enabled: bool
    object_types: list[str]
    content_types: list[str]
    profile_slugs: list[str]
    cursor: int
    batch_size: int


class WatchlistData(ExtensibleResponse):
    id: int
    name: str
    enabled: bool
    visibility: str
    entity_ids: list[int]
    narrative_ids: list[int]


class AlertPolicyData(ExtensibleResponse):
    id: int
    name: str
    enabled: bool
    conditions: dict
    quiet_hours: dict
    schedule_type: str
    channel_id: int


class AlertEvaluationData(ExtensibleResponse):
    policies: int
    events_scanned: int
    new_matches: int
    matches: list[dict]


class SourceCatalogData(ExtensibleResponse):
    source_key: str
    display_name: str
    source_type: str
    authority_type: str
    is_official: bool
    enabled: bool
    metadata: dict


class SourceHealthRunData(ExtensibleResponse):
    sources: int
    snapshots: list[dict]
    new_incidents: int


class SourceIncidentData(ExtensibleResponse):
    id: int
    source_key: str
    incident_type: str
    status: str
    summary: str
    details: dict


class MarketInstrumentData(ExtensibleResponse):
    id: int
    entity_id: int
    provider: str
    symbol: str
    quote_symbol: str
    enabled: bool
    metadata: dict


class EventMarketData(ExtensibleResponse):
    event: dict
    markets: list[dict]
