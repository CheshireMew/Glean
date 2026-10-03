from __future__ import annotations

import sqlite3
from urllib.parse import urlsplit


AI_RSS_SOURCES = (
    ("qbitai", "量子位", "https://www.qbitai.com/feed/", "https://www.qbitai.com/", "media", 0),
    ("infoq-cn", "InfoQ 中文", "https://www.infoq.cn/feed", "https://www.infoq.cn/", "media", 0),
    # This feed also contains community posts, not only official HF releases.
    ("huggingface-blog", "Hugging Face Blog", "https://huggingface.co/blog/feed.xml", "https://huggingface.co/blog", "aggregator", 0),
    ("v2ex-tech", "V2EX · 技术", "https://www.v2ex.com/feed/tab/tech.xml", "https://www.v2ex.com/?tab=tech", "aggregator", 0),
    ("juejin-weekly", "掘金本周最热", "https://rsshub.bestblogs.dev/juejin/trending/all/weekly", "https://juejin.cn/", "aggregator", 0),
)

CURATED_RSS_SOURCES = (
    ("v2ex-main", "V2EX · 首页", "https://v2ex.com/index.xml", "https://www.v2ex.com/", "aggregator", 0),
    ("v2ex-tech", "V2EX · 技术", "https://www.v2ex.com/feed/tab/tech.xml", "https://www.v2ex.com/?tab=tech", "aggregator", 0),
    ("hn-chinese-digest", "Hacker News 中文每日摘要", "https://www.supertechfans.com/cn/index.xml", "https://www.supertechfans.com/cn/", "aggregator", 0),
    ("acquired-video", "Acquired", "https://www.youtube.com/feeds/videos.xml?channel_id=UCyFqFYfTW2VoIQKylJ04Rtw", "https://www.youtube.com/channel/UCyFqFYfTW2VoIQKylJ04Rtw", "primary", 0),
    ("baochipianjian", "保持偏见", "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/663e3c95af1e22bb157dcee3", "https://www.xiaoyuzhoufm.com/podcast/663e3c95af1e22bb157dcee3", "primary", 0),
)


def _feed_identity(url: str) -> tuple[str, str, str]:
    parsed = urlsplit(url)
    host = (parsed.netloc or "").lower().removeprefix("www.")
    return host, parsed.path.rstrip("/"), parsed.query


def seed_ai_rss_sources(cursor: sqlite3.Cursor) -> None:
    """Add missing presets once, preserving user names, URLs and enabled state."""
    _seed_rss_sources(cursor, AI_RSS_SOURCES)


def seed_curated_rss_sources(cursor: sqlite3.Cursor) -> None:
    """Apply the selected subscriptions, retaining removed sources and history."""
    _seed_rss_sources(cursor, CURATED_RSS_SOURCES)
    excluded_feeds = {_feed_identity(url) for url in (
        "https://www.qbitai.com/feed", "https://www.tmtpost.com/feed",
    )}
    for source_id, slug, feed_url in cursor.execute("SELECT id, slug, feed_url FROM rss_sources").fetchall():
        if slug in {"qbitai", "tmtpost"} or _feed_identity(feed_url) in excluded_feeds:
            cursor.execute("UPDATE rss_sources SET enabled=0, updated_at=CURRENT_TIMESTAMP WHERE id=? AND enabled!=0", (source_id,))


def _seed_rss_sources(cursor: sqlite3.Cursor, presets: tuple) -> None:
    existing = cursor.execute("SELECT slug, feed_url FROM rss_sources").fetchall()
    slugs = {row[0] for row in existing}
    feeds = {_feed_identity(row[1]) for row in existing}
    for slug, name, feed_url, site_url, authority, official in presets:
        if slug in slugs or _feed_identity(feed_url) in feeds:
            continue
        cursor.execute(
            """
            INSERT INTO rss_sources (
                slug, display_name, feed_url, site_url, content_kind, parser_type,
                default_limit, default_interval, enabled, authority_type, is_official
            ) VALUES (?, ?, ?, ?, 'article', 'generic', 20, 240, 1, ?, ?)
            """,
            (slug, name, feed_url, site_url, authority, official),
        )
