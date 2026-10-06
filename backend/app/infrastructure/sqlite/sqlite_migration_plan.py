from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from typing import Callable

from .sqlite_migrations import (
    drop_legacy_news_columns,
    migrate_ai_provider_chain,
    migrate_api_key_hashes,
    migrate_archive_table,
    migrate_daily_report_snapshots,
    migrate_delivery_entry_references,
    migrate_keyword_blacklist_scope,
    migrate_legacy_config,
    migrate_legacy_content_timestamps_to_utc,
    migrate_legacy_duplicate_groups,
    migrate_orphan_review_events,
    migrate_push_logs_to_review_entries,
    migrate_review_entries_to_event_profiles,
    migrate_review_prompts_to_profiles,
    migrate_review_table,
    normalize_domain_values,
    normalize_news_stages,
    seed_default_rss_sources,
)
from .sqlite_schema import (
    create_archive_table,
    create_daily_reports_table,
    create_delivery_tables,
    create_domain_validation_triggers,
    create_editorial_profiles_table,
    create_event_tables,
    create_intelligence_extension_schema,
    create_keyword_blacklist_table,
    create_news_table,
    create_news_translations_table,
    create_review_table,
    create_search_indexes,
    create_public_revision_tracking,
    create_shared_tables,
    ensure_editorial_profile_columns,
    ensure_event_references,
    ensure_news_columns,
    ensure_runtime_columns,
    seed_editorial_profiles,
    seed_tags,
)
from .sqlite_support import version_key
from .source_presets import seed_ai_rss_sources, seed_curated_rss_sources
from .wechat_schema import create_wechat_schema
from .auth_schema import create_auth_schema
from .delivery_plan_schema import create_delivery_plan_schema
from .editorial_retention_schema import migrate_draft_retention, create_delivery_and_retention_schema
from .news_identity_schema import create_news_identity_schema


LEGACY_BASELINE_VERSION = "2026.08.12.1"
WORKER_RUNTIME_VERSION = "2026.08.23.1"
PERFORMANCE_SCHEMA_VERSION = "2026.08.24.1"
INTELLIGENCE_FOUNDATION_VERSION = "2026.08.24.2"
INTELLIGENCE_WORKFLOWS_VERSION = "2026.08.25.1"
AI_NEWS_SOURCES_VERSION = "2026.09.26.1"
AI_TRANSLATIONS_VERSION = "2026.09.27.1"
WECHAT_VERSION = "2026.09.27.2"
AUTH_VERSION = "2026.09.27.3"
V2EX_VERSION = "2026.09.27.4"
JUEJIN_WEEKLY_VERSION = "2026.09.27.5"
CURATED_RSS_VERSION = "2026.10.03.1"
DELIVERY_RETENTION_VERSION = "2026.10.05.1"
SCHEMA_VERSION = "2026.10.06.1"


@dataclass(frozen=True)
class MigrationStep:
    name: str
    from_version: str | None
    to_version: str
    apply: Callable[[sqlite3.Cursor], None]


def _create_current_schema(cursor: sqlite3.Cursor) -> None:
    create_auth_schema(cursor)
    create_wechat_schema(cursor)
    create_news_table(cursor)
    create_news_translations_table(cursor)
    ensure_news_columns(cursor)
    create_event_tables(cursor)
    create_editorial_profiles_table(cursor)
    ensure_editorial_profile_columns(cursor)
    seed_editorial_profiles(cursor)
    create_shared_tables(cursor)
    ensure_runtime_columns(cursor)
    create_archive_table(cursor)
    create_review_table(cursor)
    ensure_event_references(cursor)
    create_daily_reports_table(cursor)
    create_delivery_tables(cursor)
    create_delivery_plan_schema(cursor)
    create_keyword_blacklist_table(cursor)
    normalize_domain_values(cursor)
    create_search_indexes(cursor)
    create_public_revision_tracking(cursor)
    create_intelligence_extension_schema(cursor)
    migrate_draft_retention(cursor)
    create_domain_validation_triggers(cursor)
    migrate_legacy_config(cursor)
    seed_default_rss_sources(cursor)
    seed_ai_rss_sources(cursor)
    seed_curated_rss_sources(cursor)
    seed_tags(cursor)


def _migrate_legacy_to_baseline(cursor: sqlite3.Cursor) -> None:
    create_news_table(cursor)
    ensure_news_columns(cursor)
    create_event_tables(cursor)
    create_editorial_profiles_table(cursor)
    ensure_editorial_profile_columns(cursor)
    seed_editorial_profiles(cursor)
    create_shared_tables(cursor, include_worker_metadata=False)
    ensure_runtime_columns(cursor, include_worker_metadata=False)
    create_archive_table(cursor)
    create_review_table(cursor)
    ensure_event_references(cursor)
    migrate_push_logs_to_review_entries(cursor)
    create_daily_reports_table(cursor)
    create_delivery_tables(cursor)
    create_keyword_blacklist_table(cursor)
    migrate_archive_table(cursor)
    migrate_review_table(cursor)
    normalize_news_stages(cursor)
    migrate_legacy_duplicate_groups(cursor)
    migrate_orphan_review_events(cursor)
    migrate_review_entries_to_event_profiles(cursor)
    migrate_keyword_blacklist_scope(cursor)
    migrate_daily_report_snapshots(cursor)
    migrate_delivery_entry_references(cursor)
    migrate_api_key_hashes(cursor)
    normalize_domain_values(cursor)
    create_search_indexes(cursor)
    create_public_revision_tracking(cursor)
    create_domain_validation_triggers(cursor)
    migrate_legacy_config(cursor)
    migrate_legacy_content_timestamps_to_utc(cursor)
    migrate_review_prompts_to_profiles(cursor)
    migrate_ai_provider_chain(cursor)
    drop_legacy_news_columns(cursor)
    seed_default_rss_sources(cursor)
    seed_tags(cursor)


def _add_worker_runtime_metadata(cursor: sqlite3.Cursor) -> None:
    ensure_runtime_columns(cursor)


def _add_performance_schema(cursor: sqlite3.Cursor) -> None:
    create_event_tables(cursor)
    create_review_table(cursor)
    ensure_event_references(cursor)
    create_shared_tables(cursor)
    create_daily_reports_table(cursor)
    create_delivery_tables(cursor)
    create_search_indexes(cursor)
    create_public_revision_tracking(cursor)


def _add_intelligence_extension_schema(cursor: sqlite3.Cursor) -> None:
    create_intelligence_extension_schema(cursor)
    create_public_revision_tracking(cursor)
    create_domain_validation_triggers(cursor)


def _complete_intelligence_workflows(cursor: sqlite3.Cursor) -> None:
    create_intelligence_extension_schema(cursor)
    seed_default_rss_sources(cursor)


LEGACY_COMPATIBILITY_STEP = MigrationStep(
    name="legacy-compatibility-baseline",
    from_version=None,
    to_version=LEGACY_BASELINE_VERSION,
    apply=_migrate_legacy_to_baseline,
)
MIGRATION_STEPS = (
    MigrationStep(
        name="worker-runtime-metadata",
        from_version=LEGACY_BASELINE_VERSION,
        to_version=WORKER_RUNTIME_VERSION,
        apply=_add_worker_runtime_metadata,
    ),
    MigrationStep(
        name="performance-and-retention-foundation",
        from_version=WORKER_RUNTIME_VERSION,
        to_version=PERFORMANCE_SCHEMA_VERSION,
        apply=_add_performance_schema,
    ),
    MigrationStep(
        name="event-intelligence-and-publication-foundation",
        from_version=PERFORMANCE_SCHEMA_VERSION,
        to_version=INTELLIGENCE_FOUNDATION_VERSION,
        apply=_add_intelligence_extension_schema,
    ),
    MigrationStep(
        name="intelligence-workflow-completion",
        from_version=INTELLIGENCE_FOUNDATION_VERSION,
        to_version=INTELLIGENCE_WORKFLOWS_VERSION,
        apply=_complete_intelligence_workflows,
    ),
    MigrationStep(
        name="ai-news-rss-sources",
        from_version=INTELLIGENCE_WORKFLOWS_VERSION,
        to_version=AI_NEWS_SOURCES_VERSION,
        apply=seed_ai_rss_sources,
    ),
    MigrationStep(
        name="ai-news-chinese-translations",
        from_version=AI_NEWS_SOURCES_VERSION,
        to_version=AI_TRANSLATIONS_VERSION,
        apply=create_news_translations_table,
    ),
    MigrationStep(
        name="wechat-public-accounts",
        from_version=AI_TRANSLATIONS_VERSION,
        to_version=WECHAT_VERSION,
        apply=create_wechat_schema,
    ),
    MigrationStep(
        name="admin-sessions-and-login-limits",
        from_version=WECHAT_VERSION,
        to_version=AUTH_VERSION,
        apply=create_auth_schema,
    ),
    MigrationStep(
        name="v2ex-tech-subscription",
        from_version=AUTH_VERSION,
        to_version=V2EX_VERSION,
        apply=seed_ai_rss_sources,
    ),
    MigrationStep(
        name="juejin-weekly-subscription",
        from_version=V2EX_VERSION,
        to_version=JUEJIN_WEEKLY_VERSION,
        apply=seed_ai_rss_sources,
    ),
    MigrationStep(
        name="curated-rss-subscriptions",
        from_version=JUEJIN_WEEKLY_VERSION,
        to_version=CURATED_RSS_VERSION,
        apply=seed_curated_rss_sources,
    ),
    MigrationStep(
        name="immutable-business-delivery-plans-and-draft-retention",
        from_version=CURATED_RSS_VERSION,
        to_version=DELIVERY_RETENTION_VERSION,
        apply=create_delivery_and_retention_schema,
    ),
    MigrationStep(
        name="persistent-media-article-identities",
        from_version=DELIVERY_RETENTION_VERSION,
        to_version=SCHEMA_VERSION,
        apply=create_news_identity_schema,
    ),
)


def create_current_schema(cursor: sqlite3.Cursor) -> None:
    _create_current_schema(cursor)


def resolve_migration_plan(previous_version: str | None) -> tuple[MigrationStep, ...]:
    if previous_version == SCHEMA_VERSION:
        return ()
    if previous_version is None or version_key(previous_version) < version_key(LEGACY_BASELINE_VERSION):
        return (LEGACY_COMPATIBILITY_STEP, *MIGRATION_STEPS)
    if version_key(previous_version) > version_key(SCHEMA_VERSION):
        raise RuntimeError(
            f"数据库结构版本 {previous_version} 新于当前程序支持的 {SCHEMA_VERSION}，拒绝降级写入"
        )
    plan = []
    current = previous_version
    steps_by_source = {step.from_version: step for step in MIGRATION_STEPS}
    while current != SCHEMA_VERSION:
        step = steps_by_source.get(current)
        if step is None:
            raise RuntimeError(
                f"数据库结构版本 {previous_version} 不在已登记的迁移链上，拒绝猜测式迁移"
            )
        plan.append(step)
        current = step.to_version
    return tuple(plan)
