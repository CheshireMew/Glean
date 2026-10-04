from __future__ import annotations

import re

TRANSLATION_EXCERPT_CHARS = 600
TRANSLATION_SOURCE_CHARS = 1200


# These subscriptions have a separate public destination from the existing
# editorial feed. Names remain compatible with already collected news rows.
AI_SOURCES = (
    {"key": "hacker_news", "name": "Hacker News", "site_url": "https://news.ycombinator.com/", "rss_slug": None, "snapshot": True, "limit": 30},
    # Keep historical records classified here after removing the subscription.
    {"key": "rss__qbitai", "name": "量子位", "site_url": "https://www.qbitai.com/", "rss_slug": "qbitai", "hidden": True},
    {"key": "rss__hn-chinese-digest", "name": "Hacker News 中文每日摘要", "site_url": "https://www.supertechfans.com/cn/", "rss_slug": "hn-chinese-digest"},
    {"key": "rss__infoq-cn", "name": "InfoQ 中文", "site_url": "https://www.infoq.cn/", "rss_slug": "infoq-cn"},
    {"key": "rss__huggingface-blog", "name": "Hugging Face Blog", "site_url": "https://huggingface.co/blog", "rss_slug": "huggingface-blog"},
    {"key": "lobsters", "name": "Lobsters", "site_url": "https://lobste.rs/recent", "rss_slug": None},
    {"key": "juejin_ai", "name": "掘金 · AI 推荐", "site_url": "https://juejin.cn/ai", "rss_slug": None, "snapshot": True, "hidden": True},
    {"key": "rss__juejin-weekly", "name": "掘金本周最热", "site_url": "https://juejin.cn/", "rss_slug": "juejin-weekly", "snapshot": True, "separate_identity": True},
    {"key": "waytoagi", "name": "WaytoAGI", "site_url": "https://waytoagi.feishu.cn/wiki/QPe5w5g7UisbEkkow8XcDmOpn8e", "rss_slug": None, "snapshot": True, "limit": 100, "freshness_seconds": 1800},
    {"key": "rss__v2ex-main", "name": "V2EX · 首页", "site_url": "https://www.v2ex.com/", "rss_slug": "v2ex-main", "snapshot": True, "separate_identity": True, "limit": 30, "freshness_seconds": 600},
    {"key": "rss__v2ex-tech", "name": "V2EX · 技术", "site_url": "https://www.v2ex.com/?tab=tech", "rss_slug": "v2ex-tech", "snapshot": True, "limit": 30, "freshness_seconds": 600},
    {"key": "rss__acquired-video", "name": "Acquired", "site_url": "https://www.youtube.com/channel/UCyFqFYfTW2VoIQKylJ04Rtw", "rss_slug": "acquired-video", "hidden": True},
    {"key": "rss__baochipianjian", "name": "保持偏见", "site_url": "https://www.xiaoyuzhoufm.com/podcast/663e3c95af1e22bb157dcee3", "rss_slug": "baochipianjian"},
)

PUBLIC_AI_SOURCES = tuple(source for source in AI_SOURCES if not source.get("hidden"))


def ai_source_sql(source_column: str) -> str:
    """Only internal column names are accepted by callers, never request input."""
    # Hidden AI records must not fall back into the editorial/default feed.
    names = ", ".join("'" + source["name"].replace("'", "''") + "'" for source in AI_SOURCES)
    slugs = ", ".join("'" + source["rss_slug"] + "'" for source in AI_SOURCES if source["rss_slug"])
    return f"(COALESCE({source_column}, '') IN ({names}) OR COALESCE({source_column}, '') IN (SELECT display_name FROM rss_sources WHERE slug IN ({slugs})) OR COALESCE({source_column}, '') IN (SELECT '公众号：' || name FROM wechat_sources))"


def source_text(key: str, title: str, content: str | None) -> str:
    text = (content or "").strip()
    if key == "hacker_news":
        # Compatibility with earlier scraper rows that appended our navigation
        # link and used the title as a body fallback. Neither is source content.
        text = re.sub(r"\n+Hacker News 讨论：https://news\.ycombinator\.com/item\?id=\d+\s*$", "", text).strip()
        if text == title.strip():
            return ""
    if text in {"点击查看原文>", "点击查看原文", "查看原文"}:
        return ""
    return text


def needs_chinese_translation(text: str) -> bool:
    """Skip Chinese prose containing product names, and empty/numeric fields."""
    chinese = len(re.findall(r"[\u3400-\u9fff]", text))
    words = re.findall(r"[A-Za-z]+", text)
    letters = sum(map(len, words))
    return letters >= 3 and (chinese == 0 or (len(words) >= 5 and letters > chinese * 5))


def translation_fields(key: str, title: str, content: str | None) -> dict[str, str]:
    excerpt = source_text(key, title, content)[:TRANSLATION_EXCERPT_CHARS].rstrip()
    return {name: value for name, value in {"title": title, "excerpt": excerpt}.items()
            if needs_chinese_translation(value)}
