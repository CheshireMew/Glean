from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal


@lru_cache(maxsize=1)
def _load_contract() -> dict:
    contract_path = Path(__file__).with_name("content_contract.json")
    return json.loads(contract_path.read_text(encoding="utf-8"))


_CONTRACT = _load_contract()

CONTENT_KIND_NEWS = _CONTRACT["contentKinds"]["news"]
CONTENT_KIND_ARTICLE = _CONTRACT["contentKinds"]["article"]
CONTENT_KINDS = (CONTENT_KIND_NEWS, CONTENT_KIND_ARTICLE)

INCOMING_STAGE = _CONTRACT["stages"]["incoming"]
ARCHIVED_STAGE = _CONTRACT["stages"]["archived"]
CONTENT_STAGES = (INCOMING_STAGE, ARCHIVED_STAGE)

EVENT_TABLE = _CONTRACT["events"]["table"]
EVENT_SOURCE_TABLE = _CONTRACT["events"]["sourceTable"]

ARCHIVE_TABLE = _CONTRACT["archive"]["table"]
ARCHIVE_STATUS_READY = _CONTRACT["archive"]["statuses"]["ready"]
ARCHIVE_STATUS_BLOCKED = _CONTRACT["archive"]["statuses"]["blocked"]
ARCHIVE_STATUS_REVIEWED = _CONTRACT["archive"]["statuses"]["reviewed"]
ARCHIVE_STATUSES = (ARCHIVE_STATUS_READY, ARCHIVE_STATUS_BLOCKED, ARCHIVE_STATUS_REVIEWED)

REVIEW_TABLE = _CONTRACT["review"]["table"]
REVIEW_STATUS_PENDING = _CONTRACT["review"]["statuses"]["pending"]
REVIEW_STATUS_PROCESSING = _CONTRACT["review"]["statuses"]["processing"]
REVIEW_STATUS_SELECTED = _CONTRACT["review"]["statuses"]["selected"]
REVIEW_STATUS_DISCARDED = _CONTRACT["review"]["statuses"]["discarded"]
REVIEW_STATUSES = (
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_PROCESSING,
    REVIEW_STATUS_SELECTED,
    REVIEW_STATUS_DISCARDED,
)
REVIEW_MAX_ATTEMPTS = int(_CONTRACT["review"]["maxAttempts"])

ENRICHMENT_STATUS_PENDING = _CONTRACT["enrichment"]["statuses"]["pending"]
ENRICHMENT_STATUS_PROCESSING = _CONTRACT["enrichment"]["statuses"]["processing"]
ENRICHMENT_STATUS_COMPLETED = _CONTRACT["enrichment"]["statuses"]["completed"]
ENRICHMENT_STATUS_FAILED = _CONTRACT["enrichment"]["statuses"]["failed"]
ENRICHMENT_STATUS_NOT_APPLICABLE = _CONTRACT["enrichment"]["statuses"]["notApplicable"]
ENRICHMENT_STATUSES = (
    ENRICHMENT_STATUS_PENDING,
    ENRICHMENT_STATUS_PROCESSING,
    ENRICHMENT_STATUS_COMPLETED,
    ENRICHMENT_STATUS_FAILED,
    ENRICHMENT_STATUS_NOT_APPLICABLE,
)

DELIVERY_STATUS_PENDING = _CONTRACT["delivery"]["statuses"]["pending"]
DELIVERY_STATUS_SENT = _CONTRACT["delivery"]["statuses"]["sent"]
DELIVERY_STATUS_EXPIRED = _CONTRACT["delivery"]["statuses"]["expired"]
DELIVERY_STATUSES = (DELIVERY_STATUS_PENDING, DELIVERY_STATUS_SENT, DELIVERY_STATUS_EXPIRED)

DELIVERY_OPERATION_STATUS_PENDING = _CONTRACT["deliveryOperations"]["statuses"]["pending"]
DELIVERY_OPERATION_STATUS_SENDING = _CONTRACT["deliveryOperations"]["statuses"]["sending"]
DELIVERY_OPERATION_STATUS_FAILED = _CONTRACT["deliveryOperations"]["statuses"]["failed"]
DELIVERY_OPERATION_STATUS_NEEDS_ATTENTION = _CONTRACT["deliveryOperations"]["statuses"]["needsAttention"]
DELIVERY_OPERATION_STATUS_SENT = _CONTRACT["deliveryOperations"]["statuses"]["sent"]
DELIVERY_OPERATION_STATUSES = (
    DELIVERY_OPERATION_STATUS_PENDING,
    DELIVERY_OPERATION_STATUS_SENDING,
    DELIVERY_OPERATION_STATUS_FAILED,
    DELIVERY_OPERATION_STATUS_NEEDS_ATTENTION,
    DELIVERY_OPERATION_STATUS_SENT,
)
DELIVERY_PART_STATUS_PENDING = _CONTRACT["deliveryOperations"]["partStatuses"]["pending"]
DELIVERY_PART_STATUS_SENDING = _CONTRACT["deliveryOperations"]["partStatuses"]["sending"]
DELIVERY_PART_STATUS_FAILED = _CONTRACT["deliveryOperations"]["partStatuses"]["failed"]
DELIVERY_PART_STATUS_UNKNOWN = _CONTRACT["deliveryOperations"]["partStatuses"]["unknown"]
DELIVERY_PART_STATUS_SENT = _CONTRACT["deliveryOperations"]["partStatuses"]["sent"]
DELIVERY_PART_STATUSES = (
    DELIVERY_PART_STATUS_PENDING,
    DELIVERY_PART_STATUS_SENDING,
    DELIVERY_PART_STATUS_FAILED,
    DELIVERY_PART_STATUS_UNKNOWN,
    DELIVERY_PART_STATUS_SENT,
)
DELIVERY_MAX_ATTEMPTS = int(_CONTRACT["deliveryOperations"]["maxAttempts"])
DELIVERY_LEASE_SECONDS = int(_CONTRACT["deliveryOperations"]["leaseSeconds"])
DELIVERY_STALE_SENDING_SECONDS = int(_CONTRACT["deliveryOperations"]["staleSendingSeconds"])
TELEGRAM_MESSAGE_LIMIT = int(_CONTRACT["telegram"]["messageLimit"])

SCRAPER_RUNTIME_STATUS_IDLE = _CONTRACT["scraperRuntime"]["statuses"]["idle"]
SCRAPER_RUNTIME_STATUS_QUEUED = _CONTRACT["scraperRuntime"]["statuses"]["queued"]
SCRAPER_RUNTIME_STATUS_RUNNING = _CONTRACT["scraperRuntime"]["statuses"]["running"]
SCRAPER_RUNTIME_STATUS_ERROR = _CONTRACT["scraperRuntime"]["statuses"]["error"]
SCRAPER_RUNTIME_STATUSES = (
    SCRAPER_RUNTIME_STATUS_IDLE,
    SCRAPER_RUNTIME_STATUS_QUEUED,
    SCRAPER_RUNTIME_STATUS_RUNNING,
    SCRAPER_RUNTIME_STATUS_ERROR,
)
SCRAPER_COMMAND_TYPE_RUN = _CONTRACT["scraperCommands"]["types"]["run"]
SCRAPER_COMMAND_TYPE_STOP = _CONTRACT["scraperCommands"]["types"]["stop"]
SCRAPER_COMMAND_TYPES = (SCRAPER_COMMAND_TYPE_RUN, SCRAPER_COMMAND_TYPE_STOP)
SCRAPER_COMMAND_STATUS_PENDING = _CONTRACT["scraperCommands"]["statuses"]["pending"]
SCRAPER_COMMAND_STATUS_PROCESSING = _CONTRACT["scraperCommands"]["statuses"]["processing"]
SCRAPER_COMMAND_STATUS_COMPLETED = _CONTRACT["scraperCommands"]["statuses"]["completed"]
SCRAPER_COMMAND_STATUS_FAILED = _CONTRACT["scraperCommands"]["statuses"]["failed"]
SCRAPER_COMMAND_STATUS_CANCELLED = _CONTRACT["scraperCommands"]["statuses"]["cancelled"]
SCRAPER_COMMAND_STATUSES = (
    SCRAPER_COMMAND_STATUS_PENDING,
    SCRAPER_COMMAND_STATUS_PROCESSING,
    SCRAPER_COMMAND_STATUS_COMPLETED,
    SCRAPER_COMMAND_STATUS_FAILED,
    SCRAPER_COMMAND_STATUS_CANCELLED,
)
PUSH_LOG_STATUS_SUCCESS = _CONTRACT["pushLogs"]["statuses"]["success"]
PUSH_LOG_STATUS_FAILED = _CONTRACT["pushLogs"]["statuses"]["failed"]
PUSH_LOG_STATUS_UNKNOWN = _CONTRACT["pushLogs"]["statuses"]["unknown"]
PUSH_LOG_STATUS_NEEDS_ATTENTION = _CONTRACT["pushLogs"]["statuses"]["needsAttention"]
PUSH_LOG_STATUS_IN_PROGRESS = _CONTRACT["pushLogs"]["statuses"]["inProgress"]
PUSH_LOG_STATUSES = (
    PUSH_LOG_STATUS_SUCCESS,
    PUSH_LOG_STATUS_FAILED,
    PUSH_LOG_STATUS_UNKNOWN,
    PUSH_LOG_STATUS_NEEDS_ATTENTION,
    PUSH_LOG_STATUS_IN_PROGRESS,
)

EXPORT_SCOPE_INCOMING = _CONTRACT["exportScopes"]["incoming"]
EXPORT_SCOPE_ARCHIVE = _CONTRACT["exportScopes"]["archive"]
EXPORT_SCOPE_BLOCKED = _CONTRACT["exportScopes"]["blocked"]
EXPORT_SCOPE_REVIEW = _CONTRACT["exportScopes"]["review"]
EXPORT_SCOPE_SELECTED = _CONTRACT["exportScopes"]["selected"]
EXPORT_SCOPE_DISCARDED = _CONTRACT["exportScopes"]["discarded"]

PUBLIC_STREAM_BRIEFS = _CONTRACT["publicStreams"]["briefs"]
PUBLIC_STREAM_LONGFORM = _CONTRACT["publicStreams"]["longform"]
PUBLIC_STREAM_MAP = {
    PUBLIC_STREAM_BRIEFS: CONTENT_KIND_NEWS,
    PUBLIC_STREAM_LONGFORM: CONTENT_KIND_ARTICLE,
}

REVIEW_DECISION_MAP = {
    REVIEW_STATUS_SELECTED: REVIEW_STATUS_SELECTED,
    REVIEW_STATUS_DISCARDED: REVIEW_STATUS_DISCARDED,
}

ContentKind = Literal[CONTENT_KIND_NEWS, CONTENT_KIND_ARTICLE]
ExportScope = Literal[
    EXPORT_SCOPE_INCOMING,
    EXPORT_SCOPE_ARCHIVE,
    EXPORT_SCOPE_BLOCKED,
    EXPORT_SCOPE_REVIEW,
    EXPORT_SCOPE_SELECTED,
    EXPORT_SCOPE_DISCARDED,
]
ReviewDecision = Literal[REVIEW_STATUS_SELECTED, REVIEW_STATUS_DISCARDED]
SearchKind = Literal["all", CONTENT_KIND_NEWS, CONTENT_KIND_ARTICLE]

SYSTEM_TIMEZONE_KEY = _CONTRACT["configKeys"]["systemTimezone"]
EVENT_CLUSTER_THRESHOLD_KEY = _CONTRACT["configKeys"]["eventClusterThreshold"]


def automation_key(kind: str, field: str) -> str:
    return f"automation.{kind}.{field}"


def review_key(kind: str, field: str) -> str:
    return f"review.{kind}.{field}"


def delivery_key(kind: str, field: str) -> str:
    return f"delivery.{kind}.{field}"


def integration_key(group: str, field: str) -> str:
    return f"integration.{group}.{field}"
