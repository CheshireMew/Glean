from __future__ import annotations

from dataclasses import dataclass

from shared.content_contract import (
    ARCHIVE_STATUS_BLOCKED,
    ARCHIVE_STATUS_READY,
    ARCHIVE_TABLE,
    ENRICHMENT_STATUS_COMPLETED,
    EXPORT_SCOPE_ARCHIVE,
    EXPORT_SCOPE_BLOCKED,
    EXPORT_SCOPE_DISCARDED,
    EXPORT_SCOPE_INCOMING,
    EXPORT_SCOPE_REVIEW,
    EXPORT_SCOPE_SELECTED,
    INCOMING_STAGE,
    REVIEW_STATUS_DISCARDED,
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_SELECTED,
    REVIEW_TABLE,
)


@dataclass(frozen=True)
class ContentScopePlan:
    scope: str
    table: str
    record_kind: str
    status_column: str
    status: str
    kind_column: str
    required_enrichment_status: str | None = None


CONTENT_SCOPE_PLANS = {
    EXPORT_SCOPE_INCOMING: ContentScopePlan(
        EXPORT_SCOPE_INCOMING, "news", "incoming", "stage", INCOMING_STAGE, "type"
    ),
    EXPORT_SCOPE_ARCHIVE: ContentScopePlan(
        EXPORT_SCOPE_ARCHIVE,
        ARCHIVE_TABLE,
        "archive",
        "archive_status",
        ARCHIVE_STATUS_READY,
        "content_type",
    ),
    EXPORT_SCOPE_BLOCKED: ContentScopePlan(
        EXPORT_SCOPE_BLOCKED,
        ARCHIVE_TABLE,
        "archive",
        "archive_status",
        ARCHIVE_STATUS_BLOCKED,
        "content_type",
    ),
    EXPORT_SCOPE_REVIEW: ContentScopePlan(
        EXPORT_SCOPE_REVIEW,
        REVIEW_TABLE,
        "review",
        "review_status",
        REVIEW_STATUS_PENDING,
        "content_type",
    ),
    EXPORT_SCOPE_SELECTED: ContentScopePlan(
        EXPORT_SCOPE_SELECTED,
        REVIEW_TABLE,
        "review",
        "review_status",
        REVIEW_STATUS_SELECTED,
        "content_type",
        ENRICHMENT_STATUS_COMPLETED,
    ),
    EXPORT_SCOPE_DISCARDED: ContentScopePlan(
        EXPORT_SCOPE_DISCARDED,
        REVIEW_TABLE,
        "review",
        "review_status",
        REVIEW_STATUS_DISCARDED,
        "content_type",
    ),
}


def content_scope_plan(scope: str) -> ContentScopePlan:
    return CONTENT_SCOPE_PLANS[scope]
