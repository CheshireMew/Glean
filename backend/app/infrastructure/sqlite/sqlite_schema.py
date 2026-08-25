from __future__ import annotations

import sqlite3

from shared.content_contract import (
    ARCHIVE_STATUS_READY,
    ARCHIVE_TABLE,
    DELIVERY_OPERATION_STATUSES,
    DELIVERY_OPERATION_STATUS_PENDING,
    DELIVERY_PART_STATUSES,
    DELIVERY_PART_STATUS_PENDING,
    DELIVERY_STATUSES,
    DELIVERY_STATUS_PENDING,
    DELIVERY_STATUS_SENT,
    ENRICHMENT_STATUSES,
    ENRICHMENT_STATUS_PENDING,
    INCOMING_STAGE,
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_SELECTED,
    REVIEW_STATUSES,
    SCRAPER_COMMAND_STATUSES,
    SCRAPER_COMMAND_STATUS_PENDING,
    SCRAPER_COMMAND_TYPES,
    SCRAPER_RUNTIME_STATUSES,
    PUSH_LOG_STATUSES,
    REVIEW_TABLE,
    EVENT_SOURCE_TABLE,
    EVENT_TABLE,
)

from .sqlite_support import column_exists, ensure_column, sql_string_list


def create_news_table(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT,
            source_site TEXT NOT NULL,
            source_url TEXT UNIQUE NOT NULL,
            published_at TIMESTAMP NOT NULL,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_marked_important BOOLEAN DEFAULT FALSE,
            site_importance_flag TEXT,
            stage TEXT DEFAULT '{INCOMING_STAGE}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            type TEXT DEFAULT 'news',
            author TEXT DEFAULT '',
            event_id INTEGER,
            event_similarity REAL,
            is_event_primary BOOLEAN DEFAULT FALSE,
            CHECK (stage IN ('incoming', 'archived')),
            CHECK (type IN ('news', 'article'))
        )
        """
    )


def ensure_news_columns(cursor: sqlite3.Cursor) -> None:
    ensure_column(cursor, "news", "type", "TEXT DEFAULT 'news'")
    ensure_column(cursor, "news", "author", "TEXT DEFAULT ''")
    ensure_column(cursor, "news", "event_id", "INTEGER")
    ensure_column(cursor, "news", "event_similarity", "REAL")
    ensure_column(cursor, "news", "is_event_primary", "BOOLEAN DEFAULT FALSE")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_event ON news(event_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_stage_kind_scraped ON news(stage, type, scraped_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_kind_published ON news(type, published_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_source_kind_scraped ON news(source_site, type, scraped_at DESC)")


def create_event_tables(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {EVENT_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_news_id INTEGER NOT NULL UNIQUE,
            title TEXT NOT NULL,
            content TEXT,
            content_type TEXT NOT NULL DEFAULT 'news',
            published_at DATETIME NOT NULL,
            first_seen_at DATETIME NOT NULL,
            last_seen_at DATETIME NOT NULL,
            source_count INTEGER NOT NULL DEFAULT 1,
            event_key TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (canonical_news_id) REFERENCES news(id) ON DELETE RESTRICT,
            CHECK (content_type IN ('news', 'article')),
            CHECK (source_count >= 1)
        )
        """
    )
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_events_kind_time ON {EVENT_TABLE}(content_type, published_at DESC)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_events_kind_last_seen ON {EVENT_TABLE}(content_type, last_seen_at DESC)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_events_key ON {EVENT_TABLE}(event_key)")
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {EVENT_SOURCE_TABLE} (
            event_id INTEGER NOT NULL,
            news_id INTEGER NOT NULL UNIQUE,
            similarity REAL NOT NULL DEFAULT 1.0,
            is_primary BOOLEAN NOT NULL DEFAULT FALSE,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (event_id, news_id),
            FOREIGN KEY (event_id) REFERENCES {EVENT_TABLE}(id) ON DELETE CASCADE,
            FOREIGN KEY (news_id) REFERENCES news(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_event_sources_event ON {EVENT_SOURCE_TABLE}(event_id, is_primary DESC)")


def ensure_event_references(cursor: sqlite3.Cursor) -> None:
    ensure_column(cursor, ARCHIVE_TABLE, "event_id", "INTEGER")
    ensure_column(cursor, REVIEW_TABLE, "event_id", "INTEGER")
    ensure_column(cursor, REVIEW_TABLE, "profile_slug", "TEXT")
    ensure_column(cursor, REVIEW_TABLE, "review_error", "TEXT")
    ensure_column(cursor, REVIEW_TABLE, "review_attempts", "INTEGER DEFAULT 0")
    ensure_column(
        cursor,
        REVIEW_TABLE,
        "enrichment_status",
        f"TEXT DEFAULT '{ENRICHMENT_STATUS_PENDING}'",
    )
    ensure_column(cursor, REVIEW_TABLE, "enriched_summary", "TEXT")
    ensure_column(cursor, REVIEW_TABLE, "enriched_impact", "TEXT")
    ensure_column(cursor, REVIEW_TABLE, "enriched_background", "TEXT")
    ensure_column(cursor, REVIEW_TABLE, "enrichment_citations", "TEXT DEFAULT '[]'")
    ensure_column(cursor, REVIEW_TABLE, "enrichment_error", "TEXT")
    ensure_column(cursor, REVIEW_TABLE, "enriched_at", "DATETIME")
    ensure_column(cursor, REVIEW_TABLE, "review_claim_token", "TEXT")
    ensure_column(cursor, REVIEW_TABLE, "review_claim_expires_at", "TIMESTAMP")
    ensure_column(cursor, REVIEW_TABLE, "enrichment_attempts", "INTEGER DEFAULT 0")
    ensure_column(cursor, REVIEW_TABLE, "enrichment_claim_token", "TEXT")
    ensure_column(cursor, REVIEW_TABLE, "enrichment_claim_expires_at", "TIMESTAMP")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_archive_event ON {ARCHIVE_TABLE}(event_id)")
    if column_exists(cursor, REVIEW_TABLE, "event_id"):
        cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_review_event ON {REVIEW_TABLE}(event_id)")
    if column_exists(cursor, REVIEW_TABLE, "profile_slug"):
        cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_review_profile ON {REVIEW_TABLE}(profile_slug, review_status)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_review_claim ON {REVIEW_TABLE}(content_type, review_status, review_claim_expires_at)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_enrichment_claim ON {REVIEW_TABLE}(content_type, enrichment_status, enrichment_claim_expires_at)")
    cursor.execute(
        f"CREATE INDEX IF NOT EXISTS idx_review_claim_queue ON {REVIEW_TABLE}(content_type, review_status, review_attempts, published_at, id)"
    )
    cursor.execute(
        f"CREATE INDEX IF NOT EXISTS idx_enrichment_claim_queue ON {REVIEW_TABLE}(content_type, review_status, enrichment_status, enrichment_attempts, published_at, id)"
    )


def create_editorial_profiles_table(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS editorial_profiles (
            slug TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            content_type TEXT NOT NULL,
            review_prompt TEXT NOT NULL DEFAULT '',
            enrichment_prompt TEXT NOT NULL DEFAULT '',
            min_score INTEGER NOT NULL DEFAULT 5,
            max_items INTEGER NOT NULL DEFAULT 12,
            max_per_category INTEGER NOT NULL DEFAULT 4,
            max_per_source INTEGER NOT NULL DEFAULT 4,
            enabled BOOLEAN NOT NULL DEFAULT 1,
            is_default BOOLEAN NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_editorial_profiles_kind ON editorial_profiles(content_type, enabled, is_default)")


def ensure_editorial_profile_columns(cursor: sqlite3.Cursor) -> None:
    ensure_column(cursor, "editorial_profiles", "max_items", "INTEGER NOT NULL DEFAULT 12")
    ensure_column(cursor, "editorial_profiles", "max_per_category", "INTEGER NOT NULL DEFAULT 4")
    ensure_column(cursor, "editorial_profiles", "max_per_source", "INTEGER NOT NULL DEFAULT 4")
    cursor.execute("UPDATE editorial_profiles SET is_default = 0 WHERE enabled = 0 AND is_default = 1")
    for content_kind in ("news", "article"):
        defaults = cursor.execute(
            "SELECT slug FROM editorial_profiles WHERE content_type = ? AND enabled = 1 AND is_default = 1 ORDER BY created_at, slug",
            (content_kind,),
        ).fetchall()
        if len(defaults) > 1:
            keep_slug = defaults[0]["slug"]
            cursor.execute(
                "UPDATE editorial_profiles SET is_default = CASE WHEN slug = ? THEN 1 ELSE 0 END WHERE content_type = ?",
                (keep_slug, content_kind),
            )
        elif not defaults:
            candidate = cursor.execute(
                "SELECT slug FROM editorial_profiles WHERE content_type = ? AND enabled = 1 ORDER BY created_at, slug LIMIT 1",
                (content_kind,),
            ).fetchone()
            if candidate:
                cursor.execute("UPDATE editorial_profiles SET is_default = 1 WHERE slug = ?", (candidate["slug"],))
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_editorial_profiles_one_default ON editorial_profiles(content_type) WHERE is_default = 1"
    )


def seed_editorial_profiles(cursor: sqlite3.Cursor) -> None:
    defaults = (
        ("daily-briefs", "精选快讯", "news", "说明事件为何值得进入精选快讯。", 12, 4, 4, 1),
        ("deep-reads", "深度文章", "article", "说明文章提供了哪些新增事实、分析或方法。", 8, 3, 3, 1),
    )
    for slug, name, content_type, enrichment_prompt, max_items, max_category, max_source, is_default in defaults:
        cursor.execute(
            """
            INSERT OR IGNORE INTO editorial_profiles (
                slug, name, content_type, enrichment_prompt, min_score, max_items,
                max_per_category, max_per_source, enabled, is_default
            ) VALUES (?, ?, ?, ?, 5, ?, ?, ?, 1, ?)
            """,
            (slug, name, content_type, enrichment_prompt, max_items, max_category, max_source, is_default),
        )


def create_shared_tables(cursor: sqlite3.Cursor, *, include_worker_metadata: bool = True) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            category TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS news_tags (
            news_id INTEGER,
            tag_id INTEGER,
            PRIMARY KEY (news_id, tag_id),
            FOREIGN KEY (news_id) REFERENCES news(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS processing_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            news_id INTEGER,
            stage TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT,
            operation_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (news_id) REFERENCES news(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS push_logs (
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
        """
        CREATE TABLE IF NOT EXISTS filter_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_type TEXT NOT NULL,
            rule_pattern TEXT NOT NULL,
            hit_count INTEGER DEFAULT 0,
            last_hit_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS system_config (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_name TEXT NOT NULL,
            api_key TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            enabled BOOLEAN DEFAULT 1,
            last_used_at TIMESTAMP,
            notes TEXT
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_key ON api_keys(api_key)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_enabled ON api_keys(enabled)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_retention ON processing_logs(created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_push_logs_retention ON push_logs(pushed_at)")
    ensure_column(cursor, "api_keys", "key_prefix", "TEXT")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS scraper_runtime_state (
            scraper_name TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'idle',
            queued_at TIMESTAMP,
            start_time TIMESTAMP,
            last_run TIMESTAMP,
            last_result TEXT,
            last_error TEXT,
            items_scraped INTEGER DEFAULT 0,
            logs TEXT DEFAULT '[]',
            run_id TEXT,
            worker_id TEXT,
            heartbeat_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS scraper_runtime_commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scraper_name TEXT NOT NULL,
            command_type TEXT NOT NULL,
            payload TEXT,
            status TEXT NOT NULL DEFAULT '{SCRAPER_COMMAND_STATUS_PENDING}',
            result_message TEXT,
            claimed_by TEXT,
            lease_expires_at TIMESTAMP,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_scraper_runtime_commands_status ON scraper_runtime_commands(status, created_at)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_scraper_runtime_commands_scraper ON scraper_runtime_commands(scraper_name, status, created_at)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_scraper_runtime_commands_retention ON scraper_runtime_commands(status, updated_at)"
    )
    worker_metadata_columns = (
        """
            owner_version TEXT,
            runtime_status TEXT NOT NULL DEFAULT 'ready',
            status_details TEXT,
        """
        if include_worker_metadata
        else ""
    )
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS runtime_leases (
            name TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            lease_expires_at TIMESTAMP NOT NULL,
            {worker_metadata_columns}
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS rss_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            feed_url TEXT NOT NULL UNIQUE,
            site_url TEXT NOT NULL,
            content_kind TEXT NOT NULL DEFAULT 'article',
            parser_type TEXT NOT NULL DEFAULT 'generic',
            default_limit INTEGER NOT NULL DEFAULT 20,
            default_interval INTEGER NOT NULL DEFAULT 240,
            enabled BOOLEAN NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rss_sources_enabled ON rss_sources(enabled, content_kind)")


def ensure_runtime_columns(cursor: sqlite3.Cursor, *, include_worker_metadata: bool = True) -> None:
    ensure_column(cursor, "processing_logs", "operation_id", "TEXT")
    ensure_column(cursor, "scraper_runtime_state", "run_id", "TEXT")
    ensure_column(cursor, "scraper_runtime_state", "worker_id", "TEXT")
    ensure_column(cursor, "scraper_runtime_state", "heartbeat_at", "TIMESTAMP")
    ensure_column(cursor, "scraper_runtime_commands", "claimed_by", "TEXT")
    ensure_column(cursor, "scraper_runtime_commands", "lease_expires_at", "TIMESTAMP")
    ensure_column(cursor, "scraper_runtime_commands", "attempt_count", "INTEGER NOT NULL DEFAULT 0")
    if include_worker_metadata:
        ensure_column(cursor, "runtime_leases", "owner_version", "TEXT")
        ensure_column(cursor, "runtime_leases", "runtime_status", "TEXT NOT NULL DEFAULT 'ready'")
        ensure_column(cursor, "runtime_leases", "status_details", "TEXT")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_processing_operation ON processing_logs(operation_id, created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_scraper_state_heartbeat ON scraper_runtime_state(status, heartbeat_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_scraper_command_lease ON scraper_runtime_commands(status, lease_expires_at)")


def create_archive_table(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {ARCHIVE_TABLE} (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT,
            source_site TEXT NOT NULL,
            source_url TEXT NOT NULL UNIQUE,
            published_at DATETIME NOT NULL,
            scraped_at DATETIME NOT NULL,
            archived_at DATETIME NOT NULL,
            is_marked_important BOOLEAN,
            site_importance_flag TEXT,
            archive_status TEXT DEFAULT '{ARCHIVE_STATUS_READY}',
            content_type TEXT DEFAULT 'news',
            source_item_id INTEGER,
            restored_from_blocklist BOOLEAN DEFAULT FALSE,
            block_reason TEXT,
            event_id INTEGER,
            FOREIGN KEY (source_item_id) REFERENCES news(id) ON DELETE CASCADE,
            FOREIGN KEY (event_id) REFERENCES {EVENT_TABLE}(id) ON DELETE CASCADE,
            CHECK (archive_status IN ('ready', 'blocked', 'reviewed')),
            CHECK (content_type IN ('news', 'article'))
        )
        """
    )
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_archive_source ON {ARCHIVE_TABLE}(source_site)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_archive_time ON {ARCHIVE_TABLE}(archived_at)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_archive_status ON {ARCHIVE_TABLE}(archive_status)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_archive_kind ON {ARCHIVE_TABLE}(content_type, archive_status, published_at)")


def create_review_table(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {REVIEW_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT,
            source_site TEXT NOT NULL,
            source_url TEXT NOT NULL,
            published_at DATETIME NOT NULL,
            scraped_at DATETIME NOT NULL,
            archived_at DATETIME NOT NULL,
            queued_at DATETIME NOT NULL,
            is_marked_important BOOLEAN,
            site_importance_flag TEXT,
            content_type TEXT DEFAULT 'news',
            source_item_id INTEGER,
            event_id INTEGER,
            profile_slug TEXT,
            review_status TEXT DEFAULT '{REVIEW_STATUS_PENDING}',
            review_summary TEXT,
            review_reason TEXT,
            review_score INTEGER,
            review_category TEXT,
            review_tags TEXT,
            delivery_status TEXT DEFAULT '{DELIVERY_STATUS_PENDING}',
            delivered_at TIMESTAMP,
            review_error TEXT,
            review_attempts INTEGER DEFAULT 0,
            enrichment_status TEXT DEFAULT '{ENRICHMENT_STATUS_PENDING}',
            enriched_summary TEXT,
            enriched_impact TEXT,
            enriched_background TEXT,
            enrichment_citations TEXT DEFAULT '[]',
            enrichment_error TEXT,
            enriched_at DATETIME,
            review_claim_token TEXT,
            review_claim_expires_at TIMESTAMP,
            enrichment_attempts INTEGER DEFAULT 0,
            enrichment_claim_token TEXT,
            enrichment_claim_expires_at TIMESTAMP,
            UNIQUE(event_id, profile_slug),
            FOREIGN KEY (source_item_id) REFERENCES news(id) ON DELETE CASCADE,
            FOREIGN KEY (event_id) REFERENCES {EVENT_TABLE}(id) ON DELETE CASCADE,
            FOREIGN KEY (profile_slug) REFERENCES editorial_profiles(slug) ON DELETE RESTRICT,
            CHECK (content_type IN ('news', 'article')),
            CHECK (review_status IN ({sql_string_list(REVIEW_STATUSES)})),
            CHECK (delivery_status IN ({sql_string_list(DELIVERY_STATUSES)})),
            CHECK (enrichment_status IN ({sql_string_list(ENRICHMENT_STATUSES)}))
        )
        """
    )
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_review_source ON {REVIEW_TABLE}(source_site)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_review_queue ON {REVIEW_TABLE}(review_status)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_review_delivery ON {REVIEW_TABLE}(delivery_status)")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_review_public ON {REVIEW_TABLE}(content_type, review_status, delivery_status, published_at)")
    cursor.execute(
        f"CREATE INDEX IF NOT EXISTS idx_review_admin_list ON {REVIEW_TABLE}(content_type, review_status, published_at DESC, id DESC)"
    )
    if column_exists(cursor, REVIEW_TABLE, "event_id"):
        cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_review_event ON {REVIEW_TABLE}(event_id)")
    if column_exists(cursor, REVIEW_TABLE, "profile_slug"):
        cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_review_profile ON {REVIEW_TABLE}(profile_slug, review_status)")
        cursor.execute(
            f"CREATE INDEX IF NOT EXISTS idx_review_public_feed ON {REVIEW_TABLE}(content_type, profile_slug, review_status, delivery_status, published_at DESC, id DESC)"
        )


def create_daily_reports_table(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            publication_key TEXT NOT NULL UNIQUE,
            date TEXT NOT NULL,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            news_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (type IN ('news', 'article'))
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_reports_date ON daily_reports(date DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_reports_type ON daily_reports(type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_reports_retention ON daily_reports(created_at)")
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS daily_report_items (
            report_id INTEGER NOT NULL,
            review_entry_id INTEGER,
            event_id INTEGER,
            position INTEGER NOT NULL,
            section TEXT NOT NULL,
            ranking_score REAL NOT NULL,
            source_count INTEGER NOT NULL DEFAULT 1,
            title TEXT NOT NULL,
            source_url TEXT NOT NULL,
            source_site TEXT,
            published_at TEXT,
            content_type TEXT NOT NULL,
            review_summary TEXT,
            enriched_summary TEXT,
            enriched_impact TEXT,
            enriched_background TEXT,
            enrichment_citations TEXT NOT NULL DEFAULT '[]',
            PRIMARY KEY (report_id, position),
            FOREIGN KEY (report_id) REFERENCES daily_reports(id) ON DELETE CASCADE,
            FOREIGN KEY (review_entry_id) REFERENCES {REVIEW_TABLE}(id) ON DELETE SET NULL,
            FOREIGN KEY (event_id) REFERENCES {EVENT_TABLE}(id) ON DELETE SET NULL,
            CHECK (content_type IN ('news', 'article'))
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_report_items_order ON daily_report_items(report_id, position)")


def create_delivery_tables(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS delivery_operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_key TEXT NOT NULL UNIQUE,
            operation_type TEXT NOT NULL,
            content_kind TEXT,
            payload_hash TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{{}}',
            status TEXT NOT NULL DEFAULT '{DELIVERY_OPERATION_STATUS_PENDING}',
            total_parts INTEGER NOT NULL DEFAULT 0,
            sent_parts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            owner_token TEXT,
            lease_expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
        """
    )
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS delivery_parts (
            operation_id INTEGER NOT NULL,
            part_index INTEGER NOT NULL,
            content_hash TEXT NOT NULL,
            content TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '{DELIVERY_PART_STATUS_PENDING}',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            remote_message_id TEXT,
            last_error TEXT,
            sending_at TIMESTAMP,
            sent_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (operation_id, part_index),
            FOREIGN KEY (operation_id) REFERENCES delivery_operations(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS delivery_operation_entries (
            operation_id INTEGER NOT NULL,
            entry_ref TEXT NOT NULL,
            review_entry_id INTEGER,
            PRIMARY KEY (operation_id, entry_ref),
            FOREIGN KEY (operation_id) REFERENCES delivery_operations(id) ON DELETE CASCADE,
            FOREIGN KEY (review_entry_id) REFERENCES {REVIEW_TABLE}(id) ON DELETE SET NULL
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_delivery_operations_status ON delivery_operations(status, updated_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_delivery_parts_status ON delivery_parts(operation_id, status, part_index)")
    ensure_column(cursor, "delivery_operations", "metadata", "TEXT NOT NULL DEFAULT '{}'")
    ensure_column(cursor, "delivery_operations", "owner_token", "TEXT")
    ensure_column(cursor, "delivery_operations", "lease_expires_at", "TIMESTAMP")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_delivery_operations_lease ON delivery_operations(status, lease_expires_at)")


def create_keyword_blacklist_table(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS keyword_blacklist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            match_type TEXT DEFAULT 'contains',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            type TEXT NOT NULL DEFAULT 'news',
            UNIQUE(keyword, type),
            CHECK (type IN ('news', 'article')),
            CHECK (match_type IN ('contains', 'regex'))
        )
        """
    )
    ensure_column(cursor, "keyword_blacklist", "type", "TEXT DEFAULT 'news'")


def create_search_indexes(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS review_entries_fts USING fts5(
            title, content, review_summary, enriched_summary,
            content='{REVIEW_TABLE}', content_rowid='id', tokenize='trigram'
        )
        """
    )
    cursor.execute(
        f"""
        CREATE TRIGGER IF NOT EXISTS review_entries_fts_insert AFTER INSERT ON {REVIEW_TABLE} BEGIN
            INSERT INTO review_entries_fts(rowid, title, content, review_summary, enriched_summary)
            VALUES (new.id, new.title, new.content, new.review_summary, new.enriched_summary);
        END
        """
    )
    cursor.execute(
        f"""
        CREATE TRIGGER IF NOT EXISTS review_entries_fts_delete AFTER DELETE ON {REVIEW_TABLE} BEGIN
            INSERT INTO review_entries_fts(review_entries_fts, rowid, title, content, review_summary, enriched_summary)
            VALUES ('delete', old.id, old.title, old.content, old.review_summary, old.enriched_summary);
        END
        """
    )
    cursor.execute("DROP TRIGGER IF EXISTS review_entries_fts_update")
    cursor.execute(
        f"""
        CREATE TRIGGER review_entries_fts_update
        AFTER UPDATE OF title, content, review_summary, enriched_summary ON {REVIEW_TABLE}
        WHEN OLD.title IS NOT NEW.title
          OR OLD.content IS NOT NEW.content
          OR OLD.review_summary IS NOT NEW.review_summary
          OR OLD.enriched_summary IS NOT NEW.enriched_summary
        BEGIN
            INSERT INTO review_entries_fts(review_entries_fts, rowid, title, content, review_summary, enriched_summary)
            VALUES ('delete', old.id, old.title, old.content, old.review_summary, old.enriched_summary);
            INSERT INTO review_entries_fts(rowid, title, content, review_summary, enriched_summary)
            VALUES (new.id, new.title, new.content, new.review_summary, new.enriched_summary);
        END
        """
    )
    cursor.execute("INSERT INTO review_entries_fts(review_entries_fts) VALUES ('rebuild')")


def create_public_revision_tracking(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS public_content_revisions (
            content_type TEXT PRIMARY KEY,
            revision INTEGER NOT NULL DEFAULT 1,
            CHECK (content_type IN ('news', 'article'))
        )
        """
    )
    cursor.executemany(
        "INSERT OR IGNORE INTO public_content_revisions(content_type, revision) VALUES (?, 1)",
        (("news",), ("article",)),
    )
    trigger_names = (
        "public_revision_review_insert",
        "public_revision_review_update",
        "public_revision_review_delete",
        "public_revision_profile_insert",
        "public_revision_profile_update",
        "public_revision_profile_delete",
        "public_revision_event_update",
        "public_revision_event_source_insert",
        "public_revision_event_source_update",
        "public_revision_event_source_delete",
        "public_revision_news_update",
    )
    for trigger_name in trigger_names:
        cursor.execute(f"DROP TRIGGER IF EXISTS {trigger_name}")
    public_new = (
        f"NEW.review_status = '{REVIEW_STATUS_SELECTED}' AND NEW.delivery_status = '{DELIVERY_STATUS_SENT}'"
    )
    public_old = (
        f"OLD.review_status = '{REVIEW_STATUS_SELECTED}' AND OLD.delivery_status = '{DELIVERY_STATUS_SENT}'"
    )
    cursor.execute(
        f"""
        CREATE TRIGGER public_revision_review_insert AFTER INSERT ON {REVIEW_TABLE}
        WHEN {public_new}
        BEGIN
            UPDATE public_content_revisions SET revision = revision + 1 WHERE content_type = NEW.content_type;
        END
        """
    )
    cursor.execute(
        f"""
        CREATE TRIGGER public_revision_review_delete AFTER DELETE ON {REVIEW_TABLE}
        WHEN {public_old}
        BEGIN
            UPDATE public_content_revisions SET revision = revision + 1 WHERE content_type = OLD.content_type;
        END
        """
    )
    cursor.execute(
        f"""
        CREATE TRIGGER public_revision_review_update
        AFTER UPDATE OF title, source_url, published_at, source_site, review_category,
            review_reason, review_summary, review_score, enriched_summary, enriched_impact,
            enriched_background, enrichment_citations, event_id, profile_slug,
            review_status, delivery_status, content_type
        ON {REVIEW_TABLE}
        WHEN ({public_old} OR {public_new}) AND (
            OLD.title IS NOT NEW.title OR OLD.source_url IS NOT NEW.source_url
            OR OLD.published_at IS NOT NEW.published_at OR OLD.source_site IS NOT NEW.source_site
            OR OLD.review_category IS NOT NEW.review_category OR OLD.review_reason IS NOT NEW.review_reason
            OR OLD.review_summary IS NOT NEW.review_summary OR OLD.review_score IS NOT NEW.review_score
            OR OLD.enriched_summary IS NOT NEW.enriched_summary OR OLD.enriched_impact IS NOT NEW.enriched_impact
            OR OLD.enriched_background IS NOT NEW.enriched_background
            OR OLD.enrichment_citations IS NOT NEW.enrichment_citations OR OLD.event_id IS NOT NEW.event_id
            OR OLD.profile_slug IS NOT NEW.profile_slug OR OLD.review_status IS NOT NEW.review_status
            OR OLD.delivery_status IS NOT NEW.delivery_status OR OLD.content_type IS NOT NEW.content_type
        )
        BEGIN
            UPDATE public_content_revisions
            SET revision = revision + 1
            WHERE content_type IN (OLD.content_type, NEW.content_type);
        END
        """
    )
    for action in ("INSERT", "UPDATE", "DELETE"):
        reference = "NEW" if action == "INSERT" else "OLD"
        cursor.execute(
            f"""
            CREATE TRIGGER public_revision_profile_{action.lower()} AFTER {action} ON editorial_profiles
            BEGIN
                UPDATE public_content_revisions
                SET revision = revision + 1
                WHERE content_type IN ({reference}.content_type{', NEW.content_type' if action == 'UPDATE' else ''});
            END
            """
        )
    cursor.execute(
        f"""
        CREATE TRIGGER public_revision_event_update AFTER UPDATE OF source_count ON {EVENT_TABLE}
        WHEN OLD.source_count IS NOT NEW.source_count
        BEGIN
            UPDATE public_content_revisions SET revision = revision + 1
            WHERE content_type IN (
                SELECT DISTINCT content_type FROM {REVIEW_TABLE}
                WHERE event_id = NEW.id AND review_status = '{REVIEW_STATUS_SELECTED}'
                  AND delivery_status = '{DELIVERY_STATUS_SENT}'
            );
        END
        """
    )
    for action in ("INSERT", "UPDATE", "DELETE"):
        event_expression = (
            "NEW.event_id" if action == "INSERT" else
            "OLD.event_id" if action == "DELETE" else
            "OLD.event_id, NEW.event_id"
        )
        cursor.execute(
            f"""
            CREATE TRIGGER public_revision_event_source_{action.lower()} AFTER {action} ON {EVENT_SOURCE_TABLE}
            BEGIN
                UPDATE public_content_revisions SET revision = revision + 1
                WHERE content_type IN (
                    SELECT DISTINCT content_type FROM {REVIEW_TABLE}
                    WHERE event_id IN ({event_expression})
                      AND review_status = '{REVIEW_STATUS_SELECTED}'
                      AND delivery_status = '{DELIVERY_STATUS_SENT}'
                );
            END
            """
        )
    cursor.execute(
        f"""
        CREATE TRIGGER public_revision_news_update
        AFTER UPDATE OF title, source_site, source_url, published_at ON news
        WHEN OLD.title IS NOT NEW.title OR OLD.source_site IS NOT NEW.source_site
          OR OLD.source_url IS NOT NEW.source_url OR OLD.published_at IS NOT NEW.published_at
        BEGIN
            UPDATE public_content_revisions SET revision = revision + 1
            WHERE content_type IN (
                SELECT DISTINCT r.content_type
                FROM {EVENT_SOURCE_TABLE} es JOIN {REVIEW_TABLE} r ON r.event_id = es.event_id
                WHERE es.news_id = NEW.id AND r.review_status = '{REVIEW_STATUS_SELECTED}'
                  AND r.delivery_status = '{DELIVERY_STATUS_SENT}'
            );
        END
        """
    )


def create_domain_validation_triggers(cursor: sqlite3.Cursor) -> None:
    validations = {
        "news_domain_insert": (
            "news", "INSERT", "NEW.stage IS NULL OR NEW.stage NOT IN ('incoming','archived') OR "
            "NEW.type IS NULL OR NEW.type NOT IN ('news','article') OR "
            "NEW.is_event_primary IS NULL OR NEW.is_event_primary NOT IN (0,1) OR "
            "(NEW.event_similarity IS NOT NULL AND (NEW.event_similarity < 0 OR NEW.event_similarity > 1)) OR "
            f"(NEW.event_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM {EVENT_TABLE} WHERE id = NEW.event_id))"
        ),
        "news_domain_update": (
            "news", "UPDATE", "NEW.stage IS NULL OR NEW.stage NOT IN ('incoming','archived') OR "
            "NEW.type IS NULL OR NEW.type NOT IN ('news','article') OR "
            "NEW.is_event_primary IS NULL OR NEW.is_event_primary NOT IN (0,1) OR "
            "(NEW.event_similarity IS NOT NULL AND (NEW.event_similarity < 0 OR NEW.event_similarity > 1)) OR "
            f"(NEW.event_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM {EVENT_TABLE} WHERE id = NEW.event_id))"
        ),
        "event_domain_insert": (
            EVENT_TABLE, "INSERT", "NEW.content_type IS NULL OR NEW.content_type NOT IN ('news','article') OR "
            "NEW.source_count < 1 OR NOT EXISTS (SELECT 1 FROM news WHERE id = NEW.canonical_news_id)"
        ),
        "event_domain_update": (
            EVENT_TABLE, "UPDATE", "NEW.content_type IS NULL OR NEW.content_type NOT IN ('news','article') OR "
            "NEW.source_count < 1 OR NOT EXISTS (SELECT 1 FROM news WHERE id = NEW.canonical_news_id)"
        ),
        "event_source_domain_insert": (
            EVENT_SOURCE_TABLE, "INSERT", "NEW.similarity < 0 OR NEW.similarity > 1 OR NEW.is_primary NOT IN (0,1)"
        ),
        "event_source_domain_update": (
            EVENT_SOURCE_TABLE, "UPDATE", "NEW.similarity < 0 OR NEW.similarity > 1 OR NEW.is_primary NOT IN (0,1)"
        ),
        "archive_domain_insert": (
            ARCHIVE_TABLE, "INSERT",
            "NEW.archive_status IS NULL OR NEW.archive_status NOT IN ('ready','blocked','reviewed') OR "
            "NEW.content_type IS NULL OR NEW.content_type NOT IN ('news','article') OR "
            "(NEW.source_item_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM news WHERE id = NEW.source_item_id)) OR "
            f"(NEW.event_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM {EVENT_TABLE} WHERE id = NEW.event_id))",
        ),
        "archive_domain_update": (
            ARCHIVE_TABLE, "UPDATE",
            "NEW.archive_status IS NULL OR NEW.archive_status NOT IN ('ready','blocked','reviewed') OR "
            "NEW.content_type IS NULL OR NEW.content_type NOT IN ('news','article') OR "
            "(NEW.source_item_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM news WHERE id = NEW.source_item_id)) OR "
            f"(NEW.event_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM {EVENT_TABLE} WHERE id = NEW.event_id))",
        ),
        "review_domain_insert": (
            REVIEW_TABLE, "INSERT",
            f"NEW.review_status IS NULL OR NEW.review_status NOT IN ({sql_string_list(REVIEW_STATUSES)}) OR "
            f"NEW.delivery_status IS NULL OR NEW.delivery_status NOT IN ({sql_string_list(DELIVERY_STATUSES)}) OR "
            f"NEW.enrichment_status IS NULL OR NEW.enrichment_status NOT IN ({sql_string_list(ENRICHMENT_STATUSES)}) OR "
            "NEW.content_type IS NULL OR NEW.content_type NOT IN ('news','article') OR "
            "COALESCE(NEW.review_attempts, 0) < 0 OR COALESCE(NEW.enrichment_attempts, 0) < 0 OR "
            "(NEW.review_score IS NOT NULL AND (NEW.review_score < 0 OR NEW.review_score > 10)) OR "
            "(NEW.source_item_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM news WHERE id = NEW.source_item_id)) OR "
            f"(NEW.event_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM {EVENT_TABLE} WHERE id = NEW.event_id)) OR "
            "(NEW.profile_slug IS NOT NULL AND NOT EXISTS (SELECT 1 FROM editorial_profiles WHERE slug = NEW.profile_slug))",
        ),
        "review_domain_update": (
            REVIEW_TABLE, "UPDATE",
            f"NEW.review_status IS NULL OR NEW.review_status NOT IN ({sql_string_list(REVIEW_STATUSES)}) OR "
            f"NEW.delivery_status IS NULL OR NEW.delivery_status NOT IN ({sql_string_list(DELIVERY_STATUSES)}) OR "
            f"NEW.enrichment_status IS NULL OR NEW.enrichment_status NOT IN ({sql_string_list(ENRICHMENT_STATUSES)}) OR "
            "NEW.content_type IS NULL OR NEW.content_type NOT IN ('news','article') OR "
            "COALESCE(NEW.review_attempts, 0) < 0 OR COALESCE(NEW.enrichment_attempts, 0) < 0 OR "
            "(NEW.review_score IS NOT NULL AND (NEW.review_score < 0 OR NEW.review_score > 10)) OR "
            "(NEW.source_item_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM news WHERE id = NEW.source_item_id)) OR "
            f"(NEW.event_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM {EVENT_TABLE} WHERE id = NEW.event_id)) OR "
            "(NEW.profile_slug IS NOT NULL AND NOT EXISTS (SELECT 1 FROM editorial_profiles WHERE slug = NEW.profile_slug))",
        ),
        "editorial_profile_domain_insert": (
            "editorial_profiles", "INSERT",
            "TRIM(COALESCE(NEW.slug, '')) = '' OR TRIM(COALESCE(NEW.name, '')) = '' OR "
            "NEW.content_type NOT IN ('news','article') OR NEW.min_score < 1 OR NEW.min_score > 10 OR "
            "NEW.max_items < 1 OR NEW.max_items > 100 OR "
            "NEW.max_per_category < 1 OR NEW.max_per_category > 100 OR "
            "NEW.max_per_source < 1 OR NEW.max_per_source > 100 OR "
            "NEW.enabled NOT IN (0,1) OR NEW.is_default NOT IN (0,1) OR (NEW.is_default = 1 AND NEW.enabled = 0)",
        ),
        "editorial_profile_domain_update": (
            "editorial_profiles", "UPDATE",
            "TRIM(COALESCE(NEW.slug, '')) = '' OR TRIM(COALESCE(NEW.name, '')) = '' OR "
            "NEW.content_type NOT IN ('news','article') OR NEW.min_score < 1 OR NEW.min_score > 10 OR "
            "NEW.max_items < 1 OR NEW.max_items > 100 OR "
            "NEW.max_per_category < 1 OR NEW.max_per_category > 100 OR "
            "NEW.max_per_source < 1 OR NEW.max_per_source > 100 OR "
            "NEW.enabled NOT IN (0,1) OR NEW.is_default NOT IN (0,1) OR (NEW.is_default = 1 AND NEW.enabled = 0)",
        ),
        "delivery_operation_domain_insert": (
            "delivery_operations", "INSERT",
            "TRIM(COALESCE(NEW.operation_type, '')) = '' OR "
            "(NEW.content_kind IS NOT NULL AND NEW.content_kind NOT IN ('news','article')) OR "
            f"NEW.status NOT IN ({sql_string_list(DELIVERY_OPERATION_STATUSES)}) OR "
            "NEW.total_parts < 0 OR NEW.sent_parts < 0 OR NEW.sent_parts > NEW.total_parts",
        ),
        "delivery_operation_domain_update": (
            "delivery_operations", "UPDATE",
            "TRIM(COALESCE(NEW.operation_type, '')) = '' OR "
            "(NEW.content_kind IS NOT NULL AND NEW.content_kind NOT IN ('news','article')) OR "
            f"NEW.status NOT IN ({sql_string_list(DELIVERY_OPERATION_STATUSES)}) OR "
            "NEW.total_parts < 0 OR NEW.sent_parts < 0 OR NEW.sent_parts > NEW.total_parts",
        ),
        "delivery_part_domain_insert": (
            "delivery_parts", "INSERT",
            f"NEW.part_index < 0 OR NEW.attempt_count < 0 OR NEW.status NOT IN ({sql_string_list(DELIVERY_PART_STATUSES)})",
        ),
        "delivery_part_domain_update": (
            "delivery_parts", "UPDATE",
            f"NEW.part_index < 0 OR NEW.attempt_count < 0 OR NEW.status NOT IN ({sql_string_list(DELIVERY_PART_STATUSES)})",
        ),
        "scraper_state_domain_insert": (
            "scraper_runtime_state", "INSERT",
            f"TRIM(COALESCE(NEW.scraper_name, '')) = '' OR NEW.status NOT IN ({sql_string_list(SCRAPER_RUNTIME_STATUSES)}) OR "
            "COALESCE(NEW.items_scraped, 0) < 0",
        ),
        "scraper_state_domain_update": (
            "scraper_runtime_state", "UPDATE",
            f"TRIM(COALESCE(NEW.scraper_name, '')) = '' OR NEW.status NOT IN ({sql_string_list(SCRAPER_RUNTIME_STATUSES)}) OR "
            "COALESCE(NEW.items_scraped, 0) < 0",
        ),
        "scraper_command_domain_insert": (
            "scraper_runtime_commands", "INSERT",
            f"TRIM(COALESCE(NEW.scraper_name, '')) = '' OR NEW.command_type NOT IN ({sql_string_list(SCRAPER_COMMAND_TYPES)}) OR "
            f"NEW.status NOT IN ({sql_string_list(SCRAPER_COMMAND_STATUSES)}) OR NEW.attempt_count < 0",
        ),
        "scraper_command_domain_update": (
            "scraper_runtime_commands", "UPDATE",
            f"TRIM(COALESCE(NEW.scraper_name, '')) = '' OR NEW.command_type NOT IN ({sql_string_list(SCRAPER_COMMAND_TYPES)}) OR "
            f"NEW.status NOT IN ({sql_string_list(SCRAPER_COMMAND_STATUSES)}) OR NEW.attempt_count < 0",
        ),
        "rss_source_domain_insert": (
            "rss_sources", "INSERT",
            "TRIM(COALESCE(NEW.slug, '')) = '' OR TRIM(COALESCE(NEW.display_name, '')) = '' OR "
            "NEW.content_kind NOT IN ('news','article') OR NEW.parser_type NOT IN ('generic','summary_source_link') OR "
            "NEW.default_limit < 1 OR NEW.default_interval < 1 OR NEW.enabled NOT IN (0,1)",
        ),
        "rss_source_domain_update": (
            "rss_sources", "UPDATE",
            "TRIM(COALESCE(NEW.slug, '')) = '' OR TRIM(COALESCE(NEW.display_name, '')) = '' OR "
            "NEW.content_kind NOT IN ('news','article') OR NEW.parser_type NOT IN ('generic','summary_source_link') OR "
            "NEW.default_limit < 1 OR NEW.default_interval < 1 OR NEW.enabled NOT IN (0,1)",
        ),
        "api_key_domain_insert": (
            "api_keys", "INSERT",
            "TRIM(COALESCE(NEW.key_name, '')) = '' OR TRIM(COALESCE(NEW.api_key, '')) = '' OR "
            "NEW.enabled IS NULL OR NEW.enabled NOT IN (0,1)",
        ),
        "api_key_domain_update": (
            "api_keys", "UPDATE",
            "TRIM(COALESCE(NEW.key_name, '')) = '' OR TRIM(COALESCE(NEW.api_key, '')) = '' OR "
            "NEW.enabled IS NULL OR NEW.enabled NOT IN (0,1)",
        ),
        "blacklist_domain_insert": (
            "keyword_blacklist", "INSERT",
            "TRIM(COALESCE(NEW.keyword, '')) = '' OR NEW.type NOT IN ('news','article') OR "
            "NEW.match_type NOT IN ('contains','regex')",
        ),
        "blacklist_domain_update": (
            "keyword_blacklist", "UPDATE",
            "TRIM(COALESCE(NEW.keyword, '')) = '' OR NEW.type NOT IN ('news','article') OR "
            "NEW.match_type NOT IN ('contains','regex')",
        ),
        "push_log_domain_insert": (
            "push_logs", "INSERT",
            "TRIM(COALESCE(NEW.platform, '')) = '' OR "
            f"NEW.status NOT IN ({sql_string_list(PUSH_LOG_STATUSES)})",
        ),
        "push_log_domain_update": (
            "push_logs", "UPDATE",
            "TRIM(COALESCE(NEW.platform, '')) = '' OR "
            f"NEW.status NOT IN ({sql_string_list(PUSH_LOG_STATUSES)})",
        ),
        "daily_report_domain_insert": (
            "daily_reports", "INSERT",
            "TRIM(COALESCE(NEW.publication_key, '')) = '' OR TRIM(COALESCE(NEW.date, '')) = '' OR "
            "TRIM(COALESCE(NEW.title, '')) = '' OR NEW.type NOT IN ('news','article') OR NEW.news_count < 0",
        ),
        "daily_report_domain_update": (
            "daily_reports", "UPDATE",
            "TRIM(COALESCE(NEW.publication_key, '')) = '' OR TRIM(COALESCE(NEW.date, '')) = '' OR "
            "TRIM(COALESCE(NEW.title, '')) = '' OR NEW.type NOT IN ('news','article') OR NEW.news_count < 0",
        ),
        "daily_report_item_domain_insert": (
            "daily_report_items", "INSERT",
            "NEW.position < 0 OR NEW.source_count < 1 OR NEW.content_type NOT IN ('news','article') OR "
            "TRIM(COALESCE(NEW.title, '')) = '' OR TRIM(COALESCE(NEW.source_url, '')) = ''",
        ),
        "daily_report_item_domain_update": (
            "daily_report_items", "UPDATE",
            "NEW.position < 0 OR NEW.source_count < 1 OR NEW.content_type NOT IN ('news','article') OR "
            "TRIM(COALESCE(NEW.title, '')) = '' OR TRIM(COALESCE(NEW.source_url, '')) = ''",
        ),
    }
    for name, (table, action, predicate) in validations.items():
        cursor.execute(f"DROP TRIGGER IF EXISTS {name}")
        cursor.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS {name}
            BEFORE {action} ON {table}
            WHEN {predicate}
            BEGIN
                SELECT RAISE(ABORT, 'domain constraint violation');
            END
            """
        )


def seed_tags(cursor: sqlite3.Cursor) -> None:
    predefined_tags = [
        ("BTC", "cryptocurrency"),
        ("ETH", "cryptocurrency"),
        ("DeFi", "topic"),
        ("NFT", "topic"),
        ("Layer2", "technology"),
        ("监管", "topic"),
        ("融资", "event"),
        ("黑客", "security"),
    ]
    for tag_name, category in predefined_tags:
        cursor.execute("INSERT OR IGNORE INTO tags (name, category) VALUES (?, ?)", (tag_name, category))


def create_intelligence_extension_schema(cursor: sqlite3.Cursor) -> None:
    """Create the event-intelligence, editorial, publication and feedback foundation.

    These tables extend the existing content contract. They deliberately do not add
    another content-stage model: review_entries remains the mutable editorial source,
    while revisions and publications preserve its history and delivery projections.
    """
    ensure_column(cursor, EVENT_SOURCE_TABLE, "source_role", "TEXT NOT NULL DEFAULT 'reporting'")
    ensure_column(cursor, EVENT_SOURCE_TABLE, "evidence_group", "TEXT")
    ensure_column(cursor, EVENT_SOURCE_TABLE, "origin_news_id", "INTEGER")
    ensure_column(cursor, EVENT_SOURCE_TABLE, "independence_score", "REAL NOT NULL DEFAULT 1.0")
    ensure_column(cursor, EVENT_SOURCE_TABLE, "verification_status", "TEXT NOT NULL DEFAULT 'unverified'")
    ensure_column(cursor, EVENT_SOURCE_TABLE, "evidence_notes", "TEXT")
    ensure_column(cursor, "rss_sources", "authority_type", "TEXT NOT NULL DEFAULT 'media'")
    ensure_column(cursor, "rss_sources", "is_official", "BOOLEAN NOT NULL DEFAULT 0")
    cursor.execute(
        f"CREATE INDEX IF NOT EXISTS idx_event_sources_evidence ON {EVENT_SOURCE_TABLE}(event_id, evidence_group, source_role)"
    )

    ensure_column(cursor, REVIEW_TABLE, "editorial_version", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(cursor, REVIEW_TABLE, "editorial_updated_at", "TIMESTAMP")
    ensure_column(cursor, REVIEW_TABLE, "editorial_updated_by", "TEXT")
    ensure_column(cursor, "daily_reports", "profile_slug", "TEXT")
    ensure_column(cursor, "daily_reports", "publication_id", "INTEGER")
    ensure_column(cursor, "daily_reports", "draft_id", "INTEGER")
    ensure_column(cursor, "delivery_operations", "channel_slug", "TEXT")

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS content_revisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_entry_id INTEGER NOT NULL,
            event_id INTEGER,
            revision_number INTEGER NOT NULL,
            snapshot_json TEXT NOT NULL,
            changed_fields_json TEXT NOT NULL DEFAULT '[]',
            change_note TEXT,
            actor TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(review_entry_id, revision_number),
            FOREIGN KEY (review_entry_id) REFERENCES {REVIEW_TABLE}(id) ON DELETE CASCADE,
            FOREIGN KEY (event_id) REFERENCES {EVENT_TABLE}(id) ON DELETE SET NULL,
            CHECK (revision_number >= 1)
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_content_revisions_entry ON content_revisions(review_entry_id, revision_number DESC)"
    )
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS event_updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            update_type TEXT NOT NULL DEFAULT 'development',
            title TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            occurred_at TIMESTAMP NOT NULL,
            source_news_id INTEGER,
            is_public BOOLEAN NOT NULL DEFAULT 1,
            actor TEXT NOT NULL DEFAULT 'system',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (event_id) REFERENCES {EVENT_TABLE}(id) ON DELETE CASCADE,
            FOREIGN KEY (source_news_id) REFERENCES news(id) ON DELETE SET NULL,
            CHECK (update_type IN ('development','correction','retraction','context','market')),
            CHECK (is_public IN (0,1))
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_event_updates_event ON event_updates(event_id, occurred_at DESC)")
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS event_key_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            fact_text TEXT NOT NULL,
            source_news_id INTEGER,
            confidence REAL NOT NULL DEFAULT 1.0,
            verification_status TEXT NOT NULL DEFAULT 'unverified',
            is_public BOOLEAN NOT NULL DEFAULT 1,
            actor TEXT NOT NULL DEFAULT 'system',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (event_id) REFERENCES {EVENT_TABLE}(id) ON DELETE CASCADE,
            FOREIGN KEY (source_news_id) REFERENCES news(id) ON DELETE SET NULL,
            CHECK (confidence >= 0 AND confidence <= 1),
            CHECK (verification_status IN ('unverified','verified','disputed')),
            CHECK (is_public IN (0,1))
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_event_key_facts_event ON event_key_facts(event_id, is_public, id)"
    )
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS event_relations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            related_event_id INTEGER NOT NULL,
            relation_type TEXT NOT NULL DEFAULT 'related',
            notes TEXT NOT NULL DEFAULT '',
            is_public BOOLEAN NOT NULL DEFAULT 1,
            actor TEXT NOT NULL DEFAULT 'system',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(event_id, related_event_id, relation_type),
            FOREIGN KEY (event_id) REFERENCES {EVENT_TABLE}(id) ON DELETE CASCADE,
            FOREIGN KEY (related_event_id) REFERENCES {EVENT_TABLE}(id) ON DELETE CASCADE,
            CHECK (event_id != related_event_id),
            CHECK (relation_type IN ('related','cause','effect','follow_up','contradiction','same_story')),
            CHECK (is_public IN (0,1))
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_event_relations_related ON event_relations(related_event_id, is_public, id)"
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS publication_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            channel_type TEXT NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT 1,
            config_json TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (channel_type IN ('telegram','email','discord','slack','webhook')),
            CHECK (enabled IN (0,1))
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS profile_publications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_slug TEXT NOT NULL UNIQUE,
            public_slug TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            enabled BOOLEAN NOT NULL DEFAULT 1,
            is_public BOOLEAN NOT NULL DEFAULT 0,
            rss_enabled BOOLEAN NOT NULL DEFAULT 0,
            digest_frequency TEXT NOT NULL DEFAULT 'daily',
            digest_time TEXT NOT NULL DEFAULT '09:00',
            timezone TEXT,
            template_json TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (profile_slug) REFERENCES editorial_profiles(slug) ON DELETE CASCADE,
            CHECK (enabled IN (0,1)),
            CHECK (is_public IN (0,1)),
            CHECK (rss_enabled IN (0,1)),
            CHECK (digest_frequency IN ('realtime','daily','weekly','manual'))
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS publication_targets (
            publication_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            delivery_mode TEXT NOT NULL DEFAULT 'digest',
            enabled BOOLEAN NOT NULL DEFAULT 1,
            PRIMARY KEY (publication_id, channel_id, delivery_mode),
            FOREIGN KEY (publication_id) REFERENCES profile_publications(id) ON DELETE CASCADE,
            FOREIGN KEY (channel_id) REFERENCES publication_channels(id) ON DELETE CASCADE,
            CHECK (delivery_mode IN ('realtime','digest','alert')),
            CHECK (enabled IN (0,1))
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS publication_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            draft_key TEXT NOT NULL UNIQUE,
            publication_id INTEGER NOT NULL,
            content_type TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            scheduled_at TIMESTAMP,
            published_report_id INTEGER,
            created_by TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (publication_id) REFERENCES profile_publications(id) ON DELETE RESTRICT,
            FOREIGN KEY (published_report_id) REFERENCES daily_reports(id) ON DELETE SET NULL,
            CHECK (content_type IN ('news','article')),
            CHECK (status IN ('draft','scheduled','publishing','published','cancelled'))
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_publication_drafts_status ON publication_drafts(status, scheduled_at)")
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS publication_draft_items (
            draft_id INTEGER NOT NULL,
            review_entry_id INTEGER NOT NULL,
            position INTEGER NOT NULL,
            section TEXT NOT NULL DEFAULT '其他',
            included BOOLEAN NOT NULL DEFAULT 1,
            overrides_json TEXT NOT NULL DEFAULT '{{}}',
            PRIMARY KEY (draft_id, review_entry_id),
            UNIQUE(draft_id, position),
            FOREIGN KEY (draft_id) REFERENCES publication_drafts(id) ON DELETE CASCADE,
            FOREIGN KEY (review_entry_id) REFERENCES {REVIEW_TABLE}(id) ON DELETE RESTRICT,
            CHECK (position >= 0),
            CHECK (included IN (0,1))
        )
        """
    )
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS publication_corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER,
            review_entry_id INTEGER,
            event_id INTEGER,
            correction_type TEXT NOT NULL,
            message TEXT NOT NULL,
            actor TEXT NOT NULL,
            published_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (report_id) REFERENCES daily_reports(id) ON DELETE CASCADE,
            FOREIGN KEY (review_entry_id) REFERENCES {REVIEW_TABLE}(id) ON DELETE SET NULL,
            FOREIGN KEY (event_id) REFERENCES {EVENT_TABLE}(id) ON DELETE SET NULL,
            CHECK (correction_type IN ('correction','clarification','retraction')),
            CHECK (report_id IS NOT NULL OR review_entry_id IS NOT NULL OR event_id IS NOT NULL)
        )
        """
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS ai_invocations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_id TEXT,
            review_entry_id INTEGER,
            event_id INTEGER,
            profile_slug TEXT,
            stage TEXT NOT NULL,
            provider_name TEXT NOT NULL,
            model TEXT NOT NULL,
            prompt_version TEXT NOT NULL,
            failover_index INTEGER NOT NULL DEFAULT 0,
            attempt INTEGER NOT NULL DEFAULT 1,
            started_at TIMESTAMP NOT NULL,
            completed_at TIMESTAMP,
            duration_ms INTEGER,
            input_tokens INTEGER,
            output_tokens INTEGER,
            estimated_cost REAL,
            success BOOLEAN NOT NULL DEFAULT 0,
            error_type TEXT,
            error_message TEXT,
            response_hash TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (review_entry_id) REFERENCES {REVIEW_TABLE}(id) ON DELETE SET NULL,
            FOREIGN KEY (event_id) REFERENCES {EVENT_TABLE}(id) ON DELETE SET NULL,
            FOREIGN KEY (profile_slug) REFERENCES editorial_profiles(slug) ON DELETE SET NULL,
            CHECK (stage IN ('review','enrichment','evaluation','connection_test')),
            CHECK (failover_index >= 0),
            CHECK (success IN (0,1))
        )
        """
    )
    ensure_column(cursor, "ai_invocations", "attempt", "INTEGER NOT NULL DEFAULT 1")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_invocations_time ON ai_invocations(started_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_invocations_profile ON ai_invocations(profile_slug, stage, success)")
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS ai_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invocation_id INTEGER,
            review_entry_id INTEGER NOT NULL,
            outcome TEXT NOT NULL,
            quality_score INTEGER,
            changed_fields_json TEXT NOT NULL DEFAULT '[]',
            notes TEXT,
            actor TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (invocation_id) REFERENCES ai_invocations(id) ON DELETE SET NULL,
            FOREIGN KEY (review_entry_id) REFERENCES {REVIEW_TABLE}(id) ON DELETE CASCADE,
            CHECK (outcome IN ('accepted','edited','rejected','incorrect')),
            CHECK (quality_score IS NULL OR (quality_score >= 1 AND quality_score <= 5))
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_evaluation_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            content_type TEXT NOT NULL,
            stage TEXT NOT NULL,
            input_json TEXT NOT NULL,
            expected_json TEXT NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (content_type IN ('news','article')),
            CHECK (stage IN ('review','enrichment')),
            CHECK (enabled IN (0,1))
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_evaluation_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_key TEXT NOT NULL,
            case_id INTEGER NOT NULL,
            provider_name TEXT NOT NULL,
            model TEXT NOT NULL,
            prompt_version TEXT NOT NULL,
            result_json TEXT NOT NULL,
            metrics_json TEXT NOT NULL DEFAULT '{}',
            passed BOOLEAN NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (case_id) REFERENCES ai_evaluation_cases(id) ON DELETE CASCADE,
            CHECK (passed IN (0,1))
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_evaluation_runs_key ON ai_evaluation_runs(run_key, case_id)")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            symbol TEXT,
            description TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (entity_type IN ('asset','protocol','company','person','regulator','exchange','organization','jurisdiction'))
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_entities_type_symbol ON entities(entity_type, symbol)")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS entity_aliases (
            entity_id INTEGER NOT NULL,
            alias TEXT NOT NULL,
            normalized_alias TEXT NOT NULL UNIQUE,
            PRIMARY KEY (entity_id, normalized_alias),
            FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS event_entities (
            event_id INTEGER NOT NULL,
            entity_id INTEGER NOT NULL,
            role TEXT NOT NULL DEFAULT 'mentioned',
            confidence REAL NOT NULL DEFAULT 1.0,
            source TEXT NOT NULL DEFAULT 'manual',
            PRIMARY KEY (event_id, entity_id, role),
            FOREIGN KEY (event_id) REFERENCES {EVENT_TABLE}(id) ON DELETE CASCADE,
            FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE,
            CHECK (role IN ('subject','actor','affected','location','mentioned')),
            CHECK (confidence >= 0 AND confidence <= 1),
            CHECK (source IN ('manual','ai','rule'))
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS narratives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            keywords_json TEXT NOT NULL DEFAULT '[]',
            enabled BOOLEAN NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (enabled IN (0,1))
        )
        """
    )
    ensure_column(cursor, "narratives", "keywords_json", "TEXT NOT NULL DEFAULT '[]'")
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS event_narratives (
            event_id INTEGER NOT NULL,
            narrative_id INTEGER NOT NULL,
            confidence REAL NOT NULL DEFAULT 1.0,
            source TEXT NOT NULL DEFAULT 'manual',
            PRIMARY KEY (event_id, narrative_id),
            FOREIGN KEY (event_id) REFERENCES {EVENT_TABLE}(id) ON DELETE CASCADE,
            FOREIGN KEY (narrative_id) REFERENCES narratives(id) ON DELETE CASCADE,
            CHECK (confidence >= 0 AND confidence <= 1),
            CHECK (source IN ('manual','ai','rule'))
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS watchlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL DEFAULT '',
            enabled BOOLEAN NOT NULL DEFAULT 1,
            visibility TEXT NOT NULL DEFAULT 'private',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (enabled IN (0,1)),
            CHECK (visibility IN ('private','public'))
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS watchlist_entities (
            watchlist_id INTEGER NOT NULL,
            entity_id INTEGER NOT NULL,
            PRIMARY KEY (watchlist_id, entity_id),
            FOREIGN KEY (watchlist_id) REFERENCES watchlists(id) ON DELETE CASCADE,
            FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS watchlist_narratives (
            watchlist_id INTEGER NOT NULL,
            narrative_id INTEGER NOT NULL,
            PRIMARY KEY (watchlist_id, narrative_id),
            FOREIGN KEY (watchlist_id) REFERENCES watchlists(id) ON DELETE CASCADE,
            FOREIGN KEY (narrative_id) REFERENCES narratives(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS alert_policies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL DEFAULT '',
            enabled BOOLEAN NOT NULL DEFAULT 1,
            watchlist_id INTEGER,
            profile_slug TEXT,
            conditions_json TEXT NOT NULL DEFAULT '{}',
            schedule_type TEXT NOT NULL DEFAULT 'instant',
            quiet_hours_json TEXT NOT NULL DEFAULT '{}',
            channel_id INTEGER NOT NULL,
            last_evaluated_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (watchlist_id) REFERENCES watchlists(id) ON DELETE SET NULL,
            FOREIGN KEY (profile_slug) REFERENCES editorial_profiles(slug) ON DELETE SET NULL,
            FOREIGN KEY (channel_id) REFERENCES publication_channels(id) ON DELETE RESTRICT,
            CHECK (enabled IN (0,1)),
            CHECK (schedule_type IN ('instant','daily','weekly'))
        )
        """
    )
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS alert_matches (
            policy_id INTEGER NOT NULL,
            event_id INTEGER NOT NULL,
            operation_key TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            matched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            delivered_at TIMESTAMP,
            PRIMARY KEY (policy_id, event_id),
            FOREIGN KEY (policy_id) REFERENCES alert_policies(id) ON DELETE CASCADE,
            FOREIGN KEY (event_id) REFERENCES {EVENT_TABLE}(id) ON DELETE CASCADE,
            CHECK (status IN ('pending','queued','sent','failed','suppressed'))
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS source_catalog (
            source_key TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            source_type TEXT NOT NULL,
            authority_type TEXT NOT NULL DEFAULT 'media',
            homepage_url TEXT,
            is_official BOOLEAN NOT NULL DEFAULT 0,
            enabled BOOLEAN NOT NULL DEFAULT 1,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (source_type IN ('site','rss','api','manual')),
            CHECK (authority_type IN ('primary','media','aggregator','commentary')),
            CHECK (is_official IN (0,1)),
            CHECK (enabled IN (0,1))
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS source_health_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_key TEXT NOT NULL,
            window_start TIMESTAMP NOT NULL,
            window_end TIMESTAMP NOT NULL,
            run_count INTEGER NOT NULL DEFAULT 0,
            success_count INTEGER NOT NULL DEFAULT 0,
            error_count INTEGER NOT NULL DEFAULT 0,
            zero_result_count INTEGER NOT NULL DEFAULT 0,
            item_count INTEGER NOT NULL DEFAULT 0,
            average_delay_seconds REAL,
            content_completeness REAL,
            cluster_join_rate REAL,
            selection_rate REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (source_key) REFERENCES source_catalog(source_key) ON DELETE CASCADE
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_source_health_time ON source_health_snapshots(source_key, window_end DESC)")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS source_incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_key TEXT NOT NULL,
            incident_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            summary TEXT NOT NULL,
            details_json TEXT NOT NULL DEFAULT '{}',
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP,
            FOREIGN KEY (source_key) REFERENCES source_catalog(source_key) ON DELETE CASCADE,
            CHECK (incident_type IN ('fetch_error','zero_results','content_missing','parser_drift','stale_source')),
            CHECK (status IN ('open','acknowledged','resolved'))
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS market_instruments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            symbol TEXT NOT NULL,
            quote_symbol TEXT NOT NULL DEFAULT 'USDT',
            enabled BOOLEAN NOT NULL DEFAULT 1,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(provider, symbol, quote_symbol),
            FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE,
            CHECK (enabled IN (0,1))
        )
        """
    )
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS market_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            instrument_id INTEGER NOT NULL,
            observation_window TEXT NOT NULL,
            observed_at TIMESTAMP NOT NULL,
            price REAL,
            volume REAL,
            funding_rate REAL,
            open_interest REAL,
            metadata_json TEXT NOT NULL DEFAULT '{{}}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(event_id, instrument_id, observation_window),
            FOREIGN KEY (event_id) REFERENCES {EVENT_TABLE}(id) ON DELETE CASCADE,
            FOREIGN KEY (instrument_id) REFERENCES market_instruments(id) ON DELETE CASCADE,
            CHECK (observation_window IN ('t-1h','t0','t+15m','t+1h','t+24h','t+7d'))
        )
        """
    )
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS market_impact_assessments (
            event_id INTEGER NOT NULL,
            instrument_id INTEGER NOT NULL,
            expected_direction TEXT,
            expected_impact TEXT,
            realized_direction TEXT,
            return_15m REAL,
            return_1h REAL,
            return_24h REAL,
            abnormal_return_24h REAL,
            confidence REAL,
            evaluated_at TIMESTAMP,
            metadata_json TEXT NOT NULL DEFAULT '{{}}',
            PRIMARY KEY (event_id, instrument_id),
            FOREIGN KEY (event_id) REFERENCES {EVENT_TABLE}(id) ON DELETE CASCADE,
            FOREIGN KEY (instrument_id) REFERENCES market_instruments(id) ON DELETE CASCADE,
            CHECK (expected_direction IS NULL OR expected_direction IN ('positive','negative','neutral','uncertain')),
            CHECK (realized_direction IS NULL OR realized_direction IN ('positive','negative','neutral')),
            CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS analyst_change_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_type TEXT NOT NULL,
            object_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CHECK (object_type IN ('event','correction','entity','narrative','tag')),
            CHECK (action IN ('created','updated','deleted'))
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_analyst_change_log_cursor ON analyst_change_log(id, object_type)"
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS analyst_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            channel_id INTEGER NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT 1,
            object_types_json TEXT NOT NULL DEFAULT '["event","correction","entity","narrative","tag"]',
            content_types_json TEXT NOT NULL DEFAULT '[]',
            profile_slugs_json TEXT NOT NULL DEFAULT '[]',
            cursor INTEGER NOT NULL DEFAULT 0,
            batch_size INTEGER NOT NULL DEFAULT 50,
            last_delivered_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (channel_id) REFERENCES publication_channels(id) ON DELETE RESTRICT,
            CHECK (enabled IN (0,1)),
            CHECK (cursor >= 0),
            CHECK (batch_size >= 1 AND batch_size <= 100)
        )
        """
    )

    change_triggers = {
        "analyst_event_insert": f"AFTER INSERT ON {EVENT_TABLE} BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('event', NEW.id, 'created'); END",
        "analyst_event_update": f"AFTER UPDATE ON {EVENT_TABLE} BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('event', NEW.id, 'updated'); END",
        "analyst_event_delete": f"AFTER DELETE ON {EVENT_TABLE} BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('event', OLD.id, 'deleted'); END",
        "analyst_event_source_insert": f"AFTER INSERT ON {EVENT_SOURCE_TABLE} BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('event', NEW.event_id, 'updated'); END",
        "analyst_event_source_update": f"AFTER UPDATE ON {EVENT_SOURCE_TABLE} BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('event', NEW.event_id, 'updated'); END",
        "analyst_event_source_delete": f"AFTER DELETE ON {EVENT_SOURCE_TABLE} BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('event', OLD.event_id, 'updated'); END",
        "analyst_review_insert": f"AFTER INSERT ON {REVIEW_TABLE} WHEN NEW.event_id IS NOT NULL BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('event', NEW.event_id, 'updated'); END",
        "analyst_review_update": f"AFTER UPDATE ON {REVIEW_TABLE} WHEN NEW.event_id IS NOT NULL BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('event', NEW.event_id, 'updated'); END",
        "analyst_review_delete": f"AFTER DELETE ON {REVIEW_TABLE} WHEN OLD.event_id IS NOT NULL BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('event', OLD.event_id, 'updated'); END",
        "analyst_event_update_insert": "AFTER INSERT ON event_updates BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('event', NEW.event_id, 'updated'); END",
        "analyst_event_update_update": "AFTER UPDATE ON event_updates BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('event', NEW.event_id, 'updated'); END",
        "analyst_event_update_delete": "AFTER DELETE ON event_updates BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('event', OLD.event_id, 'updated'); END",
        "analyst_event_fact_insert": "AFTER INSERT ON event_key_facts BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('event', NEW.event_id, 'updated'); END",
        "analyst_event_fact_update": "AFTER UPDATE ON event_key_facts BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('event', NEW.event_id, 'updated'); END",
        "analyst_event_fact_delete": "AFTER DELETE ON event_key_facts BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('event', OLD.event_id, 'updated'); END",
        "analyst_event_relation_insert": "AFTER INSERT ON event_relations BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('event', NEW.event_id, 'updated'); INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('event', NEW.related_event_id, 'updated'); END",
        "analyst_event_relation_update": "AFTER UPDATE ON event_relations BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('event', NEW.event_id, 'updated'); INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('event', NEW.related_event_id, 'updated'); END",
        "analyst_event_relation_delete": "AFTER DELETE ON event_relations BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('event', OLD.event_id, 'updated'); INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('event', OLD.related_event_id, 'updated'); END",
        "analyst_correction_insert": "AFTER INSERT ON publication_corrections BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('correction', NEW.id, 'created'); END",
        "analyst_correction_update": "AFTER UPDATE ON publication_corrections BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('correction', NEW.id, 'updated'); END",
        "analyst_correction_delete": "AFTER DELETE ON publication_corrections BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('correction', OLD.id, 'deleted'); END",
        "analyst_entity_insert": "AFTER INSERT ON entities BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('entity', NEW.id, 'created'); END",
        "analyst_entity_update": "AFTER UPDATE ON entities BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('entity', NEW.id, 'updated'); END",
        "analyst_entity_delete": "AFTER DELETE ON entities BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('entity', OLD.id, 'deleted'); END",
        "analyst_narrative_insert": "AFTER INSERT ON narratives BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('narrative', NEW.id, 'created'); END",
        "analyst_narrative_update": "AFTER UPDATE ON narratives BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('narrative', NEW.id, 'updated'); END",
        "analyst_narrative_delete": "AFTER DELETE ON narratives BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('narrative', OLD.id, 'deleted'); END",
        "analyst_tag_insert": "AFTER INSERT ON tags BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('tag', NEW.id, 'created'); END",
        "analyst_tag_update": "AFTER UPDATE ON tags BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('tag', NEW.id, 'updated'); END",
        "analyst_tag_delete": "AFTER DELETE ON tags BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('tag', OLD.id, 'deleted'); END",
        "analyst_news_tag_insert": "AFTER INSERT ON news_tags BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('tag', NEW.tag_id, 'updated'); END",
        "analyst_news_tag_delete": "AFTER DELETE ON news_tags BEGIN INSERT INTO analyst_change_log(object_type, object_id, action) VALUES ('tag', OLD.tag_id, 'updated'); END",
    }
    for trigger_name, trigger_sql in change_triggers.items():
        cursor.execute(f"CREATE TRIGGER IF NOT EXISTS {trigger_name} {trigger_sql}")

    cursor.execute(
        "INSERT OR IGNORE INTO publication_channels(slug, name, channel_type, enabled) VALUES ('telegram-default', '默认 Telegram', 'telegram', 1)"
    )
    cursor.execute(
        """
        INSERT OR IGNORE INTO profile_publications(
            profile_slug, public_slug, display_name, enabled, is_public, rss_enabled
        )
        SELECT slug, slug, name, enabled, is_default, is_default
        FROM editorial_profiles
        """
    )
    cursor.execute(
        """
        INSERT OR IGNORE INTO publication_targets(publication_id, channel_id, delivery_mode, enabled)
        SELECT p.id, c.id, 'digest', 1
        FROM profile_publications p
        JOIN editorial_profiles e ON e.slug = p.profile_slug AND e.is_default = 1
        JOIN publication_channels c ON c.slug = 'telegram-default'
        """
    )
