from __future__ import annotations

from datetime import datetime


def load_last_news(scraper, db):
    scraper.db = db
    if not scraper.incremental_mode:
        return

    try:
        conn = db.connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT source_url, title, published_at FROM news
            WHERE source_site = ?
            ORDER BY published_at DESC
            LIMIT 200
            """,
            (scraper.site_name,),
        )
        rows = cursor.fetchall()
        try:
            conn.close()
        except Exception:
            pass

        if not rows:
            print(f"[增量抓取] {scraper.site_name}: 未找到历史记录，将全量抓取")
            scraper.last_news_title = None
            scraper.last_news_url = None
            scraper.last_news_time = None
            return

        latest = rows[0]
        scraper.last_news_url = latest[0]
        scraper.last_news_title = latest[1]
        scraper.last_news_time = _parse_timestamp(latest[2])

        count = 0
        for row in rows:
            url = row[0]
            if url:
                scraper.existing_urls.add(url)
                count += 1

        print(f"[增量抓取] {scraper.site_name}: 已加载 {count} 条历史URL用于去重")
        print(f"[增量抓取] 最新记录: {scraper.last_news_title[:30]}... ({scraper.last_news_time})")
    except Exception as exc:
        print(f"[增量抓取] 加载历史记录失败: {exc}")


def should_stop_scraping(scraper, news_title: str, news_url: str, news_time: datetime = None) -> bool:
    if not scraper.incremental_mode:
        return False
    if not scraper.last_news_title and not scraper.last_news_url:
        return False

    if news_url in scraper.existing_urls or news_url == scraper.last_news_url:
        scraper.encountered_existing_items = True
    # Lists can pin/reorder old entries. Only item limits/list exhaustion stop a
    # scan; an old URL is skipped by the caller, never evidence that the rest is old.
    return False


def _parse_timestamp(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except Exception:
            try:
                return datetime.fromisoformat(value)
            except Exception:
                return None
    return None
