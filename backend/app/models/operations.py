from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field
from shared.content_contract import ContentKind, ExportScope

OperationKey = Annotated[
    str,
    Field(min_length=8, max_length=128, pattern=r"[A-Za-z0-9][A-Za-z0-9:._-]{7,127}"),
]


class RunScraperRequest(BaseModel):
    items: int = Field(default=10, ge=1, le=100)


class ScraperConfigRequest(BaseModel):
    interval: Optional[str] = None
    limit: Optional[int] = Field(default=None, ge=1, le=100)


class EventClusterRequest(BaseModel):
    time_window_hours: int = Field(default=24, ge=1, le=720)
    threshold: float = Field(default=0.50, ge=0, le=1)
    kind: ContentKind = "news"


class CheckSimilarityRequest(BaseModel):
    news_id_1: int
    news_id_2: int


class ReviewRunRequest(BaseModel):
    hours: int = Field(default=8, ge=1, le=720)
    kind: ContentKind = "news"


class AddBlacklistRequest(BaseModel):
    keyword: str = Field(min_length=1, max_length=500)
    match_type: Literal["contains", "regex"] = "contains"
    kind: ContentKind = "news"


class BlocklistRunRequest(BaseModel):
    time_range_hours: int = Field(default=24, ge=1, le=720)
    kind: ContentKind = "news"


class OutputEntryRef(BaseModel):
    scope: ExportScope
    id: int = Field(gt=0)


class TelegramSendRequest(BaseModel):
    entries: List[OutputEntryRef] = Field(min_length=1, max_length=500)
    operation_key: OperationKey


class DeliveryTriggerRequest(BaseModel):
    operation_key: OperationKey


class DeliveryRetryRequest(BaseModel):
    operation_key: OperationKey


class ApiKeyCreateRequest(BaseModel):
    key_name: str = Field(min_length=1, max_length=100)
    notes: Optional[str] = Field(default=None, max_length=1000)


class ApiKeyStatusRequest(BaseModel):
    enabled: bool


class CredentialsUpdateRequest(BaseModel):
    current_password: str
    new_username: Optional[str] = None
    new_password: Optional[str] = None
