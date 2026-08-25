from __future__ import annotations

import sqlite3

from shared.content_contract import (
    ARCHIVE_STATUS_BLOCKED,
    ARCHIVE_STATUS_READY,
    ARCHIVE_STATUS_REVIEWED,
    ARCHIVED_STAGE,
    DELIVERY_STATUS_PENDING,
    EVENT_CLUSTER_THRESHOLD_KEY,
    INCOMING_STAGE,
    EVENT_SOURCE_TABLE,
    EVENT_TABLE,
    REVIEW_STATUS_DISCARDED,
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_SELECTED,
    SYSTEM_TIMEZONE_KEY,
    automation_key,
    delivery_key,
    integration_key,
    review_key,
    ARCHIVE_TABLE,
    REVIEW_TABLE,
)

from .sqlite_support import column_exists, table_exists


LEGACY_CONFIG_GROUPS = {
    SYSTEM_TIMEZONE_KEY: ["system_timezone"],
    delivery_key("news", "time"): ["daily_push_time"],
    delivery_key("article", "time"): ["daily_article_push_time"],
    delivery_key("news", "last_date"): ["last_daily_push_date"],
    delivery_key("article", "last_date"): ["last_daily_article_push_date"],
    automation_key("news", "scan_hours"): ["news_dedup_hours", "auto_dedup_hours"],
    automation_key("news", "window_hours"): ["news_dedup_window_hours"],
    automation_key("news", "block_hours"): ["news_filter_hours", "auto_filter_hours"],
    automation_key("news", "review_hours"): ["news_ai_scoring_hours", "auto_ai_scoring_hours"],
    automation_key("news", "delivery_hours"): ["news_push_hours", "auto_push_hours"],
    automation_key("article", "scan_hours"): ["article_dedup_hours", "auto_article_dedup_hours", "article_auto_dedup_hours"],
    automation_key("article", "window_hours"): ["article_dedup_window_hours"],
    automation_key("article", "block_hours"): ["article_filter_hours", "auto_article_filter_hours", "article_auto_filter_hours"],
    automation_key("article", "review_hours"): ["article_ai_scoring_hours", "auto_article_ai_scoring_hours", "article_auto_ai_scoring_hours"],
    automation_key("article", "delivery_hours"): ["article_push_hours", "auto_article_push_hours", "article_auto_push_hours"],
    review_key("news", "prompt"): ["ai_filter_prompt_news", "ai_filter_prompt"],
    review_key("article", "prompt"): ["ai_filter_prompt_article", "ai_filter_prompt"],
    review_key("news", "hours"): ["ai_filter_hours_news", "ai_filter_hours"],
    review_key("article", "hours"): ["ai_filter_hours_article", "ai_filter_hours"],
    integration_key("llm", "api_key"): ["llm_api_key"],
    integration_key("llm", "base_url"): ["llm_base_url"],
    integration_key("llm", "model"): ["llm_model"],
    integration_key("telegram", "bot_token"): ["telegram_bot_token"],
    integration_key("telegram", "chat_id"): ["telegram_chat_id"],
    integration_key("telegram", "enabled"): ["telegram_enabled"],
    EVENT_CLUSTER_THRESHOLD_KEY: ["automation.dedup.threshold", "dedup_threshold"],
}

LEGACY_CONFIG_KEYS = {key for keys in LEGACY_CONFIG_GROUPS.values() for key in keys}

LEGACY_NEWS_COLUMNS = (
    "keyword_filter_passed",
    "keyword_filter_reason",
    "ai_tags",
    "ai_category",
    "ai_score",
    "ai_summary",
    "push_status",
    "pushed_at",
    "is_duplicate",
    "is_local_duplicate",
    "duplicate_of",
)


def migrate_push_logs_to_review_entries(cursor: sqlite3.Cursor) -> None:
    if not table_exists(cursor, "push_logs") or column_exists(cursor, "push_logs", "review_entry_id"):
        return
    cursor.execute("ALTER TABLE push_logs RENAME TO legacy_push_logs_news_id")
    cursor.execute(
        f"""
        CREATE TABLE push_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_entry_id INTEGER,
            operation_key TEXT,
            platform TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT,
            pushed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (review_entry_id) REFERENCES {REVIEW_TABLE}(id) ON DELETE SET NULL
        )
        """
    )
    cursor.execute(
        f"""
        INSERT INTO push_logs (id, review_entry_id, operation_key, platform, status, message, pushed_at)
        SELECT p.id,
               CASE WHEN EXISTS (SELECT 1 FROM {REVIEW_TABLE} r WHERE r.id = p.news_id) THEN p.news_id ELSE NULL END,
               'legacy:push:' || p.id,
               p.platform, p.status, p.message, p.pushed_at
        FROM legacy_push_logs_news_id p
        """
    )
    cursor.execute("DROP TABLE legacy_push_logs_news_id")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_push_logs_review ON push_logs(review_entry_id, status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_push_logs_operation ON push_logs(operation_key)")


def migrate_archive_table(cursor: sqlite3.Cursor) -> None:
    if not table_exists(cursor, "deduplicated_news"):
        return
    cursor.execute(
        f"""
        INSERT OR IGNORE INTO {ARCHIVE_TABLE} (
            id, title, content, source_site, source_url, published_at, scraped_at, archived_at,
            is_marked_important, site_importance_flag, archive_status, content_type, source_item_id,
            restored_from_blocklist, block_reason
        )
        SELECT
            id,
            title,
            content,
            source_site,
            source_url,
            published_at,
            scraped_at,
            deduplicated_at,
            is_marked_important,
            site_importance_flag,
            CASE stage
                WHEN 'filtered' THEN '{ARCHIVE_STATUS_BLOCKED}'
                WHEN 'verified' THEN '{ARCHIVE_STATUS_REVIEWED}'
                ELSE '{ARCHIVE_STATUS_READY}'
            END,
            COALESCE(type, 'news'),
            original_news_id,
            COALESCE(is_whitelist_restored, 0),
            keyword_filter_reason
        FROM deduplicated_news
        """
    )
    cursor.execute("DROP TABLE deduplicated_news")


def migrate_review_table(cursor: sqlite3.Cursor) -> None:
    if not table_exists(cursor, "curated_news"):
        return
    cursor.execute(
        f"""
        INSERT OR IGNORE INTO {REVIEW_TABLE} (
            id, title, content, source_site, source_url, published_at, scraped_at, archived_at, queued_at,
            is_marked_important, site_importance_flag, content_type, source_item_id, review_status,
            review_summary, review_reason, review_score, review_category, review_tags, delivery_status, delivered_at
        )
        SELECT
            id,
            title,
            content,
            source_site,
            source_url,
            published_at,
            scraped_at,
            deduplicated_at,
            curated_at,
            is_marked_important,
            site_importance_flag,
            COALESCE(type, 'news'),
            original_news_id,
            CASE
                WHEN ai_status = 'approved' THEN '{REVIEW_STATUS_SELECTED}'
                WHEN ai_status = 'rejected' THEN '{REVIEW_STATUS_DISCARDED}'
                ELSE '{REVIEW_STATUS_PENDING}'
            END,
            ai_summary,
            ai_explanation,
            ai_score,
            ai_category,
            ai_tags,
            COALESCE(push_status, '{DELIVERY_STATUS_PENDING}'),
            pushed_at
        FROM curated_news
        """
    )
    cursor.execute("DROP TABLE curated_news")


def normalize_news_stages(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        f"""
        UPDATE news
        SET stage = CASE stage
            WHEN 'raw' THEN '{INCOMING_STAGE}'
            WHEN 'deduplicated' THEN '{ARCHIVED_STAGE}'
            WHEN 'verified' THEN '{ARCHIVED_STAGE}'
            WHEN 'filtered' THEN '{ARCHIVED_STAGE}'
            WHEN 'duplicate' THEN '{ARCHIVED_STAGE}'
            ELSE COALESCE(stage, '{INCOMING_STAGE}')
        END
        """
    )
    cursor.execute("UPDATE news SET type = 'news' WHERE type IS NULL OR type NOT IN ('news', 'article')")


def normalize_domain_values(cursor: sqlite3.Cursor) -> None:
    """Repair legacy free-form values before validation triggers become authoritative."""
    if table_exists(cursor, "news"):
        cursor.execute(
            """
            UPDATE news
            SET is_event_primary = CASE WHEN is_event_primary = 1 THEN 1 ELSE 0 END,
                event_similarity = CASE
                    WHEN event_similarity IS NULL THEN NULL
                    ELSE MIN(1.0, MAX(0.0, event_similarity))
                END
            """
        )
    if table_exists(cursor, ARCHIVE_TABLE):
        cursor.execute(
            f"UPDATE {ARCHIVE_TABLE} SET archive_status = ? WHERE archive_status IS NULL OR archive_status NOT IN ('ready','blocked','reviewed')",
            (ARCHIVE_STATUS_READY,),
        )
        cursor.execute(
            f"UPDATE {ARCHIVE_TABLE} SET content_type = 'news' WHERE content_type IS NULL OR content_type NOT IN ('news','article')"
        )
    if table_exists(cursor, REVIEW_TABLE):
        cursor.execute(
            f"UPDATE {REVIEW_TABLE} SET review_status = ? WHERE review_status IS NULL OR review_status NOT IN ('pending','processing','selected','discarded')",
            (REVIEW_STATUS_PENDING,),
        )
        cursor.execute(
            f"UPDATE {REVIEW_TABLE} SET delivery_status = ? WHERE delivery_status IS NULL OR delivery_status NOT IN ('pending','sent','expired')",
            (DELIVERY_STATUS_PENDING,),
        )
        cursor.execute(
            f"UPDATE {REVIEW_TABLE} SET enrichment_status = CASE WHEN review_status = 'discarded' THEN 'not_applicable' ELSE 'pending' END WHERE enrichment_status IS NULL OR enrichment_status NOT IN ('pending','processing','completed','failed','not_applicable')"
        )
        cursor.execute(
            f"UPDATE {REVIEW_TABLE} SET content_type = 'news' WHERE content_type IS NULL OR content_type NOT IN ('news','article')"
        )
        cursor.execute(
            f"""
            UPDATE {REVIEW_TABLE}
            SET review_attempts = MAX(0, COALESCE(review_attempts, 0)),
                enrichment_attempts = MAX(0, COALESCE(enrichment_attempts, 0)),
                review_score = CASE
                    WHEN review_score IS NULL THEN NULL
                    ELSE MIN(10, MAX(0, review_score))
                END
            """
        )
    if table_exists(cursor, EVENT_TABLE):
        cursor.execute(
            f"UPDATE {EVENT_TABLE} SET content_type = 'news' WHERE content_type IS NULL OR content_type NOT IN ('news','article')"
        )
        cursor.execute(
            f"UPDATE {EVENT_TABLE} SET source_count = MAX(1, (SELECT COUNT(*) FROM {EVENT_SOURCE_TABLE} s WHERE s.event_id = {EVENT_TABLE}.id)) WHERE source_count IS NULL OR source_count < 1"
        )
    if table_exists(cursor, EVENT_SOURCE_TABLE):
        cursor.execute(
            f"UPDATE {EVENT_SOURCE_TABLE} SET similarity = MIN(1.0, MAX(0.0, COALESCE(similarity, 0.0))), is_primary = CASE WHEN is_primary = 1 THEN 1 ELSE 0 END"
        )
    if table_exists(cursor, "keyword_blacklist"):
        cursor.execute("UPDATE keyword_blacklist SET keyword = TRIM(keyword)")
        cursor.execute("UPDATE keyword_blacklist SET type = 'news' WHERE type IS NULL OR type NOT IN ('news','article')")
        cursor.execute("UPDATE keyword_blacklist SET match_type = 'contains' WHERE match_type IS NULL OR match_type NOT IN ('contains','regex')")
    if table_exists(cursor, "editorial_profiles"):
        cursor.execute(
            """
            UPDATE editorial_profiles
            SET content_type = CASE WHEN content_type IN ('news','article') THEN content_type ELSE 'news' END,
                min_score = MIN(10, MAX(1, COALESCE(min_score, 5))),
                max_items = MIN(100, MAX(1, COALESCE(max_items, 12))),
                max_per_category = MIN(100, MAX(1, COALESCE(max_per_category, 4))),
                max_per_source = MIN(100, MAX(1, COALESCE(max_per_source, 4))),
                enabled = CASE WHEN enabled = 1 THEN 1 ELSE 0 END,
                is_default = CASE WHEN enabled = 1 AND is_default = 1 THEN 1 ELSE 0 END
            """
        )
    if table_exists(cursor, "delivery_operations"):
        cursor.execute(
            """
            UPDATE delivery_operations
            SET operation_type = CASE WHEN TRIM(COALESCE(operation_type, '')) = '' THEN 'legacy' ELSE operation_type END,
                content_kind = CASE WHEN content_kind IN ('news','article') THEN content_kind ELSE NULL END,
                status = CASE WHEN status IN ('pending','sending','failed','needs_attention','sent') THEN status ELSE 'failed' END,
                total_parts = MAX(0, COALESCE(total_parts, 0)),
                sent_parts = MAX(0, COALESCE(sent_parts, 0))
            """
        )
        cursor.execute("UPDATE delivery_operations SET sent_parts = total_parts WHERE sent_parts > total_parts")
    if table_exists(cursor, "delivery_parts"):
        cursor.execute(
            """
            UPDATE delivery_parts
            SET status = CASE WHEN status IN ('pending','sending','failed','unknown','sent') THEN status ELSE 'failed' END,
                part_index = MAX(0, COALESCE(part_index, 0)),
                attempt_count = MAX(0, COALESCE(attempt_count, 0))
            """
        )
    if table_exists(cursor, "scraper_runtime_state"):
        cursor.execute(
            """
            UPDATE scraper_runtime_state
            SET status = CASE WHEN status IN ('idle','queued','running','error') THEN status ELSE 'error' END,
                items_scraped = MAX(0, COALESCE(items_scraped, 0))
            """
        )
    if table_exists(cursor, "scraper_runtime_commands"):
        cursor.execute(
            """
            UPDATE scraper_runtime_commands
            SET command_type = CASE WHEN command_type IN ('run','stop') THEN command_type ELSE 'stop' END,
                status = CASE WHEN status IN ('pending','processing','completed','failed','cancelled') THEN status ELSE 'failed' END,
                attempt_count = MAX(0, COALESCE(attempt_count, 0))
            """
        )
    if table_exists(cursor, "rss_sources"):
        cursor.execute(
            """
            UPDATE rss_sources
            SET content_kind = CASE WHEN content_kind IN ('news','article') THEN content_kind ELSE 'article' END,
                parser_type = CASE WHEN parser_type IN ('generic','summary_source_link') THEN parser_type ELSE 'generic' END,
                default_limit = MAX(1, COALESCE(default_limit, 20)),
                default_interval = MAX(1, COALESCE(default_interval, 240)),
                enabled = CASE WHEN enabled = 1 THEN 1 ELSE 0 END
            """
        )
    if table_exists(cursor, "api_keys"):
        cursor.execute("UPDATE api_keys SET enabled = CASE WHEN enabled = 1 THEN 1 ELSE 0 END")
    if table_exists(cursor, "push_logs"):
        cursor.execute(
            """
            UPDATE push_logs
            SET platform = CASE WHEN TRIM(COALESCE(platform, '')) = '' THEN 'legacy' ELSE platform END,
                status = CASE
                    WHEN status IN ('success','failed','unknown','needs_attention','in_progress') THEN status
                    ELSE 'failed'
                END
            """
        )
    if table_exists(cursor, "daily_reports"):
        cursor.execute("UPDATE daily_reports SET news_count = MAX(0, COALESCE(news_count, 0))")
    if table_exists(cursor, "daily_report_items"):
        cursor.execute(
            "UPDATE daily_report_items SET source_count = MAX(1, COALESCE(source_count, 1)), position = MAX(0, position)"
        )


def drop_legacy_news_columns(cursor: sqlite3.Cursor) -> None:
    """Remove superseded per-source processing fields after their data has been migrated."""
    for column_name in LEGACY_NEWS_COLUMNS:
        if not column_exists(cursor, "news", column_name):
            continue
        cursor.execute("SELECT name, sql FROM sqlite_master WHERE type = 'index' AND tbl_name = 'news' AND sql IS NOT NULL")
        for index_row in cursor.fetchall():
            index_sql = (index_row["sql"] or "").lower()
            if column_name.lower() in index_sql:
                escaped_name = index_row["name"].replace('"', '""')
                cursor.execute(f'DROP INDEX "{escaped_name}"')
        escaped_column = column_name.replace('"', '""')
        cursor.execute(f'ALTER TABLE news DROP COLUMN "{escaped_column}"')


def migrate_legacy_duplicate_groups(cursor: sqlite3.Cursor) -> None:
    """Turn legacy master/duplicate rows into durable event memberships once."""
    if not column_exists(cursor, "news", "duplicate_of"):
        return

    cursor.execute(
        f"""
        SELECT n.*
        FROM news n
        WHERE n.event_id IS NULL
          AND (
              n.stage = '{ARCHIVED_STAGE}'
              OR EXISTS (SELECT 1 FROM {ARCHIVE_TABLE} a WHERE a.source_item_id = n.id)
              OR EXISTS (SELECT 1 FROM {REVIEW_TABLE} r WHERE r.source_item_id = n.id)
          )
        ORDER BY n.published_at ASC, n.id ASC
        """
    )
    rows = [dict(row) for row in cursor.fetchall()]
    if not rows:
        return

    by_id = {row["id"]: row for row in rows}
    groups: dict[int, list[dict]] = {}
    for row in rows:
        root_id = row.get("duplicate_of") or row["id"]
        if root_id not in by_id:
            root_id = row["id"]
        groups.setdefault(root_id, []).append(row)

    for root_id, members in groups.items():
        primary = by_id.get(root_id) or max(members, key=lambda item: len(item.get("content") or ""))
        cursor.execute(
            f"""
            INSERT OR IGNORE INTO {EVENT_TABLE} (
                canonical_news_id, title, content, content_type, published_at,
                first_seen_at, last_seen_at, source_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                primary["id"],
                primary["title"],
                primary.get("content") or "",
                primary.get("type") or "news",
                primary["published_at"],
                min(member["scraped_at"] for member in members),
                max(member["scraped_at"] for member in members),
                len(members),
            ),
        )
        cursor.execute(f"SELECT id FROM {EVENT_TABLE} WHERE canonical_news_id = ?", (primary["id"],))
        event_id = cursor.fetchone()["id"]
        for member in members:
            is_primary = member["id"] == primary["id"]
            cursor.execute(
                f"INSERT OR IGNORE INTO {EVENT_SOURCE_TABLE} (event_id, news_id, similarity, is_primary) VALUES (?, ?, ?, ?)",
                (event_id, member["id"], 1.0 if is_primary else 0.5, int(is_primary)),
            )
            cursor.execute(
                "UPDATE news SET event_id = ?, event_similarity = ?, is_event_primary = ?, stage = ? WHERE id = ?",
                (event_id, 1.0 if is_primary else 0.5, int(is_primary), ARCHIVED_STAGE, member["id"]),
            )
        cursor.execute(f"UPDATE {ARCHIVE_TABLE} SET event_id = ? WHERE source_item_id = ?", (event_id, primary["id"]))
        cursor.execute(f"UPDATE {REVIEW_TABLE} SET event_id = ? WHERE source_item_id = ?", (event_id, primary["id"]))


def migrate_orphan_review_events(cursor: sqlite3.Cursor) -> None:
    """Preserve review rows whose source or event relation was missing in older databases."""
    cursor.execute(
        f"""
        SELECT title, content, source_site, source_url, published_at, scraped_at,
               archived_at, content_type, source_item_id
        FROM {REVIEW_TABLE}
        WHERE event_id IS NULL
        ORDER BY id ASC
        """
    )
    orphan_rows = [dict(row) for row in cursor.fetchall()]
    for row in orphan_rows:
        cursor.execute(
            "SELECT id, event_id FROM news WHERE id = ? OR source_url = ? ORDER BY CASE WHEN id = ? THEN 0 ELSE 1 END LIMIT 1",
            (row.get("source_item_id"), row["source_url"], row.get("source_item_id")),
        )
        news_row = cursor.fetchone()
        if news_row:
            news_id = news_row["id"]
            event_id = news_row["event_id"]
        else:
            cursor.execute(
                """
                INSERT INTO news (
                    title, content, source_site, source_url, published_at, scraped_at,
                    stage, type, event_similarity, is_event_primary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1.0, 1)
                """,
                (
                    row["title"], row.get("content") or "", row["source_site"], row["source_url"],
                    row["published_at"], row["scraped_at"], ARCHIVED_STAGE,
                    row.get("content_type") or "news",
                ),
            )
            news_id = cursor.lastrowid
            event_id = None

        if not event_id:
            first_seen = row.get("scraped_at") or row.get("archived_at") or row["published_at"]
            cursor.execute(
                f"""
                INSERT INTO {EVENT_TABLE} (
                    canonical_news_id, title, content, content_type, published_at,
                    first_seen_at, last_seen_at, source_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    news_id, row["title"], row.get("content") or "",
                    row.get("content_type") or "news", row["published_at"], first_seen, first_seen,
                ),
            )
            event_id = cursor.lastrowid
            cursor.execute(
                f"INSERT INTO {EVENT_SOURCE_TABLE} (event_id, news_id, similarity, is_primary) VALUES (?, ?, 1.0, 1)",
                (event_id, news_id),
            )
            cursor.execute(
                "UPDATE news SET event_id = ?, event_similarity = 1.0, is_event_primary = 1, stage = ? WHERE id = ?",
                (event_id, ARCHIVED_STAGE, news_id),
            )

        cursor.execute(
            f"UPDATE {REVIEW_TABLE} SET source_item_id = ?, event_id = ? WHERE source_url = ? AND event_id IS NULL",
            (news_id, event_id, row["source_url"]),
        )
        cursor.execute(
            f"UPDATE {ARCHIVE_TABLE} SET source_item_id = ?, event_id = ? WHERE source_url = ?",
            (news_id, event_id, row["source_url"]),
        )


def migrate_review_prompts_to_profiles(cursor: sqlite3.Cursor) -> None:
    profile_by_kind = {"news": "daily-briefs", "article": "deep-reads"}
    for content_kind, profile_slug in profile_by_kind.items():
        cursor.execute("SELECT value FROM system_config WHERE key = ?", (review_key(content_kind, "prompt"),))
        row = cursor.fetchone()
        if row and row["value"]:
            cursor.execute(
                "UPDATE editorial_profiles SET review_prompt = ?, updated_at = CURRENT_TIMESTAMP WHERE slug = ? AND review_prompt = ''",
                (row["value"], profile_slug),
            )
        cursor.execute("DELETE FROM system_config WHERE key = ?", (review_key(content_kind, "prompt"),))
        cursor.execute(f"UPDATE {REVIEW_TABLE} SET profile_slug = ? WHERE content_type = ? AND profile_slug IS NULL", (profile_slug, content_kind))


def migrate_ai_provider_chain(cursor: sqlite3.Cursor) -> None:
    import json

    provider_key = integration_key("llm", "providers")
    cursor.execute("SELECT value FROM system_config WHERE key = ?", (provider_key,))
    if cursor.fetchone() is None:
        keys = {
            field: integration_key("llm", field)
            for field in ("api_key", "base_url", "model")
        }
        values = {}
        for field, key in keys.items():
            cursor.execute("SELECT value FROM system_config WHERE key = ?", (key,))
            row = cursor.fetchone()
            values[field] = row["value"] if row else ""
        if values["api_key"]:
            providers = [{
                "name": "primary",
                "api_key": values["api_key"],
                "base_url": values["base_url"] or "https://api.deepseek.com",
                "model": values["model"] or "deepseek-chat",
            }]
            cursor.execute(
                "INSERT INTO system_config (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                (provider_key, json.dumps(providers, ensure_ascii=False)),
            )
    for field in ("api_key", "base_url", "model"):
        cursor.execute("DELETE FROM system_config WHERE key = ?", (integration_key("llm", field),))


def migrate_review_entries_to_event_profiles(cursor: sqlite3.Cursor) -> None:
    cursor.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (REVIEW_TABLE,))
    row = cursor.fetchone()
    table_sql = (row["sql"] or "").lower() if row else ""
    normalized_sql = "".join(table_sql.split())
    if "unique(event_id,profile_slug)" in normalized_sql:
        return

    legacy_table = "legacy_review_entries_event_migration"
    cursor.execute(f"ALTER TABLE {REVIEW_TABLE} RENAME TO {legacy_table}")
    from .sqlite_schema import create_review_table

    create_review_table(cursor)
    cursor.execute(
        f"""
        INSERT INTO {REVIEW_TABLE} (
            id, title, content, source_site, source_url, published_at, scraped_at, archived_at,
            queued_at, is_marked_important, site_importance_flag, content_type, source_item_id,
            event_id, profile_slug, review_status, review_summary, review_reason, review_score,
            review_category, review_tags, delivery_status, delivered_at, review_error, review_attempts,
            enrichment_status, enriched_summary, enriched_impact, enriched_background,
            enrichment_citations, enrichment_error, enriched_at
        )
        SELECT
            id, title, content, source_site, source_url, published_at, scraped_at, archived_at,
            queued_at, is_marked_important, site_importance_flag, content_type, source_item_id,
            event_id,
            COALESCE(profile_slug, CASE WHEN content_type = 'article' THEN 'deep-reads' ELSE 'daily-briefs' END),
            review_status, review_summary, review_reason, review_score, review_category, review_tags,
            delivery_status, delivered_at, review_error, review_attempts, enrichment_status,
            enriched_summary, enriched_impact, enriched_background, enrichment_citations,
            enrichment_error, enriched_at
        FROM {legacy_table}
        WHERE event_id IS NOT NULL
        """
    )
    cursor.execute(f"DROP TABLE {legacy_table}")
    create_review_table(cursor)


def migrate_legacy_config(cursor: sqlite3.Cursor) -> None:
    cursor.execute("SELECT key, value FROM system_config")
    existing = {row["key"]: row["value"] for row in cursor.fetchall()}

    for canonical_key, legacy_keys in LEGACY_CONFIG_GROUPS.items():
        if existing.get(canonical_key):
            continue
        for legacy_key in legacy_keys:
            legacy_value = existing.get(legacy_key)
            if legacy_value not in (None, ""):
                cursor.execute(
                    """
                    INSERT INTO system_config (key, value, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                    """,
                    (canonical_key, legacy_value),
                )
                existing[canonical_key] = legacy_value
                break

    if SYSTEM_TIMEZONE_KEY not in existing:
        cursor.execute(
            """
            INSERT INTO system_config (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO NOTHING
            """,
            (SYSTEM_TIMEZONE_KEY, "Asia/Shanghai"),
        )

    for legacy_key in LEGACY_CONFIG_KEYS:
        cursor.execute("DELETE FROM system_config WHERE key = ?", (legacy_key,))


def seed_default_rss_sources(cursor: sqlite3.Cursor) -> None:
    sources = (
        (
            "chainfeeds", "Chainfeeds Article", "https://www.chainfeeds.me/rss",
            "https://www.chainfeeds.xyz", "article", "summary_source_link", 20, 240, 1,
            "media", 0,
        ),
        (
            "sec-press-releases", "SEC Press Releases",
            "https://www.sec.gov/news/pressreleases.rss", "https://www.sec.gov/newsroom/press-releases",
            "article", "generic", 30, 120, 1, "primary", 1,
        ),
        (
            "cftc-press-releases", "CFTC Press Releases",
            "https://www.cftc.gov/RSS/RSSGP/rssgp.xml", "https://www.cftc.gov/PressRoom/PressReleases",
            "article", "generic", 30, 120, 1, "primary", 1,
        ),
        (
            "kraken-blog", "Kraken Blog", "https://blog.kraken.com/feed",
            "https://blog.kraken.com/", "article", "generic", 30, 180, 1, "primary", 1,
        ),
        (
            "ethereum-foundation-blog", "Ethereum Foundation Blog",
            "https://blog.ethereum.org/feed.xml", "https://blog.ethereum.org/",
            "article", "generic", 30, 180, 1, "primary", 1,
        ),
        (
            "ens-governance-forum", "ENS Governance Forum",
            "https://discuss.ens.domains/latest.rss", "https://discuss.ens.domains/",
            "article", "generic", 30, 120, 1, "primary", 1,
        ),
    )
    has_authority_metadata = column_exists(cursor, "rss_sources", "authority_type") and column_exists(
        cursor, "rss_sources", "is_official"
    )
    for source in sources:
        if has_authority_metadata:
            cursor.execute(
                """
                INSERT INTO rss_sources (
                    slug, display_name, feed_url, site_url, content_kind, parser_type,
                    default_limit, default_interval, enabled, authority_type, is_official, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(slug) DO UPDATE SET
                    authority_type = excluded.authority_type,
                    is_official = excluded.is_official
                """,
                source,
            )
        else:
            cursor.execute(
                """
                INSERT INTO rss_sources (
                    slug, display_name, feed_url, site_url, content_kind, parser_type,
                    default_limit, default_interval, enabled, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(slug) DO NOTHING
                """,
                source[:9],
            )


def migrate_keyword_blacklist_scope(cursor: sqlite3.Cursor) -> None:
    """Make blacklist uniqueness follow the API's per-content-kind model."""
    if not table_exists(cursor, "keyword_blacklist"):
        return
    row = cursor.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'keyword_blacklist'"
    ).fetchone()
    normalized = "".join(((row["sql"] if row else "") or "").lower().split())
    if "unique(keyword,type)" in normalized:
        return
    cursor.execute("ALTER TABLE keyword_blacklist RENAME TO legacy_keyword_blacklist_scope")
    from .sqlite_schema import create_keyword_blacklist_table

    create_keyword_blacklist_table(cursor)
    cursor.execute(
        """
        INSERT OR IGNORE INTO keyword_blacklist (id, keyword, match_type, created_at, type)
        SELECT id, keyword, COALESCE(match_type, 'contains'), created_at, COALESCE(type, 'news')
        FROM legacy_keyword_blacklist_scope
        """
    )
    cursor.execute("DROP TABLE legacy_keyword_blacklist_scope")


def migrate_daily_report_snapshots(cursor: sqlite3.Cursor) -> None:
    """Turn mutable reports into immutable publications with independent item snapshots."""
    if not table_exists(cursor, "daily_reports"):
        return
    report_columns = {row["name"] for row in cursor.execute("PRAGMA table_info(daily_reports)").fetchall()}
    item_columns = (
        {row["name"] for row in cursor.execute("PRAGMA table_info(daily_report_items)").fetchall()}
        if table_exists(cursor, "daily_report_items")
        else set()
    )
    if "publication_key" in report_columns and "title" in item_columns:
        return

    reports = [dict(row) for row in cursor.execute("SELECT * FROM daily_reports ORDER BY id").fetchall()]
    items: list[dict] = []
    if table_exists(cursor, "daily_report_items"):
        items = [
            dict(row)
            for row in cursor.execute(
                f"""
                SELECT i.*, r.title, r.source_url, r.source_site, r.published_at, r.content_type,
                       r.review_summary, r.enriched_summary, r.enriched_impact,
                       r.enriched_background, r.enrichment_citations
                FROM daily_report_items i
                LEFT JOIN {REVIEW_TABLE} r ON r.id = i.review_entry_id
                ORDER BY i.report_id, i.position
                """
            ).fetchall()
        ]
        cursor.execute("DROP TABLE daily_report_items")
    cursor.execute("DROP TABLE daily_reports")
    from .sqlite_schema import create_daily_reports_table

    create_daily_reports_table(cursor)
    for report in reports:
        cursor.execute(
            """
            INSERT INTO daily_reports (id, publication_key, date, type, title, content, news_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report["id"], f"legacy-daily:{report['id']}", report["date"], report["type"],
                report["title"], report["content"], report.get("news_count") or 0, report.get("created_at"),
            ),
        )
    for item in items:
        cursor.execute(
            """
            INSERT INTO daily_report_items (
                report_id, review_entry_id, event_id, position, section, ranking_score, source_count,
                title, source_url, source_site, published_at, content_type, review_summary,
                enriched_summary, enriched_impact, enriched_background, enrichment_citations
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["report_id"], item.get("review_entry_id"), item.get("event_id"), item["position"],
                item.get("section") or "其他", item.get("ranking_score") or 0,
                item.get("source_count") or 1, item.get("title") or "历史内容",
                item.get("source_url") or "", item.get("source_site"), item.get("published_at"),
                item.get("content_type") or "news", item.get("review_summary"),
                item.get("enriched_summary"), item.get("enriched_impact"),
                item.get("enriched_background"), item.get("enrichment_citations") or "[]",
            ),
        )


def migrate_delivery_entry_references(cursor: sqlite3.Cursor) -> None:
    """Preserve delivery audit references after mutable review rows are removed."""
    if not table_exists(cursor, "delivery_operation_entries"):
        return
    columns = {
        row["name"] for row in cursor.execute("PRAGMA table_info(delivery_operation_entries)").fetchall()
    }
    if "entry_ref" in columns:
        return
    rows = [dict(row) for row in cursor.execute("SELECT * FROM delivery_operation_entries").fetchall()]
    cursor.execute("ALTER TABLE delivery_operation_entries RENAME TO legacy_delivery_operation_entries")
    cursor.execute(
        f"""
        CREATE TABLE delivery_operation_entries (
            operation_id INTEGER NOT NULL,
            entry_ref TEXT NOT NULL,
            review_entry_id INTEGER,
            PRIMARY KEY (operation_id, entry_ref),
            FOREIGN KEY (operation_id) REFERENCES delivery_operations(id) ON DELETE CASCADE,
            FOREIGN KEY (review_entry_id) REFERENCES {REVIEW_TABLE}(id) ON DELETE SET NULL
        )
        """
    )
    import json

    for row in rows:
        review_id = row.get("review_entry_id")
        ref = json.dumps({"scope": "selected", "id": review_id}, separators=(",", ":"), sort_keys=True)
        cursor.execute(
            "INSERT INTO delivery_operation_entries (operation_id, entry_ref, review_entry_id) VALUES (?, ?, ?)",
            (row["operation_id"], ref, review_id),
        )
    cursor.execute("DROP TABLE legacy_delivery_operation_entries")


def migrate_api_key_hashes(cursor: sqlite3.Cursor) -> None:
    """Hash legacy plaintext analyst keys and retain only a display prefix."""
    if not table_exists(cursor, "api_keys") or not column_exists(cursor, "api_keys", "key_prefix"):
        return
    import hashlib

    rows = cursor.execute(
        "SELECT id, api_key FROM api_keys WHERE key_prefix IS NULL OR key_prefix = ''"
    ).fetchall()
    for row in rows:
        raw = row["api_key"] or ""
        prefix = f"{raw[:12]}…" if raw else "legacy"
        hashed = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        cursor.execute(
            "UPDATE api_keys SET api_key = ?, key_prefix = ? WHERE id = ?",
            (hashed, prefix, row["id"]),
        )


def migrate_legacy_content_timestamps_to_utc(cursor: sqlite3.Cursor) -> None:
    """Normalize legacy source/local timestamps once; SQL-generated timestamps were already UTC."""
    marker = "system.timestamps.utc_normalized"
    row = cursor.execute("SELECT value FROM system_config WHERE key = ?", (marker,)).fetchone()
    if row and row["value"] == "1":
        return
    from datetime import datetime, timezone
    import zoneinfo

    timezone_row = cursor.execute("SELECT value FROM system_config WHERE key = ?", (SYSTEM_TIMEZONE_KEY,)).fetchone()
    try:
        legacy_tz = zoneinfo.ZoneInfo(timezone_row["value"] if timezone_row else "Asia/Shanghai")
    except Exception:
        legacy_tz = zoneinfo.ZoneInfo("Asia/Shanghai")

    def convert(value):
        if value in (None, ""):
            return value
        if isinstance(value, datetime):
            parsed = value
        else:
            raw = str(value).strip().replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(raw)
            except ValueError:
                return value
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=legacy_tz)
        return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    plans = [
        ("news", ("published_at", "scraped_at"), None),
        (ARCHIVE_TABLE, ("published_at", "scraped_at"), None),
        (REVIEW_TABLE, ("published_at", "scraped_at", "queued_at"), None),
        (EVENT_TABLE, ("published_at", "first_seen_at", "last_seen_at"), None),
        ("scraper_runtime_state", ("queued_at", "last_run"), None),
    ]
    for table, columns, where in plans:
        if not table_exists(cursor, table):
            continue
        available = {item["name"] for item in cursor.execute(f"PRAGMA table_info({table})").fetchall()}
        columns = tuple(column for column in columns if column in available)
        if not columns:
            continue
        key_name = "id" if "id" in available else "rowid"
        select_columns = ", ".join([key_name, *columns])
        rows = cursor.execute(f"SELECT {select_columns} FROM {table}" + (f" WHERE {where}" if where else "")).fetchall()
        for item in rows:
            assignments = ", ".join(f"{column} = ?" for column in columns)
            cursor.execute(
                f"UPDATE {table} SET {assignments} WHERE {key_name} = ?",
                tuple([*(convert(item[column]) for column in columns), item[key_name]]),
            )
    cursor.execute(
        "INSERT INTO system_config (key, value, updated_at) VALUES (?, '1', CURRENT_TIMESTAMP) ON CONFLICT(key) DO UPDATE SET value = '1', updated_at = CURRENT_TIMESTAMP",
        (marker,),
    )
