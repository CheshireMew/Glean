from __future__ import annotations

from datetime import datetime, timezone
import json

from ...domain.ai_sources import AI_SOURCES, TRANSLATION_SOURCE_CHARS
from ...core.time import normalize_source_time
from .base_repository import BaseRepository
from .news_repository import NewsRepository
from ..lease_fencing import assert_current_operation_lease

TRANSLATION_JOIN = f"""LEFT JOIN news_translations t ON t.news_id = n.id
    AND t.source_title = n.title
    AND t.source_content_prefix = substr(COALESCE(n.content, ''), 1, {TRANSLATION_SOURCE_CHARS})"""


class AIContentRepository(BaseRepository):
    def hacker_news_front_page(self) -> list[dict]:
        return self.source_snapshot("hacker_news")

    def source_snapshot(self, key: str) -> list[dict]:
        row = self.execute("SELECT value FROM system_config WHERE key = ?", (f"ai.front_page.{key}",)).fetchone()
        return json.loads(row["value"]) if row else []

    def save_hacker_news_front_page(self, entries: list[dict]) -> None:
        self.save_source_snapshot("hacker_news", entries)

    def save_source_snapshot(self, key: str, entries: list[dict], items: list[dict] | None = None) -> None:
        if not entries:
            raise ValueError("来源列表为空，保留上次成功列表")
        managed = self.conn is None
        conn = self.conn or self.db.connect()
        started = False
        try:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
                started = True
            # A public document or topic can be edited without changing its URL.
            # Update only this source's own saved rows; translations invalidate
            # automatically when the source title or content prefix changes.
            for item in items or []:
                content = NewsRepository._normalize_news_content(item.get("content", ""))
                conn.execute("""UPDATE news SET title=?, content=?, author=?, published_at=?,
                    updated_at=CURRENT_TIMESTAMP WHERE source_url=? AND source_site=?
                    AND (title!=? OR COALESCE(content,'')!=? OR COALESCE(author,'')!=? OR published_at!=?)""",
                    (item["title"], content, item.get("author", ""), normalize_source_time(item["published_at"]),
                     item["url"], item["source_site"], item["title"], content, item.get("author", ""),
                     normalize_source_time(item["published_at"])))
            conn.execute(
                """INSERT INTO system_config (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                (f"ai.front_page.{key}", json.dumps(entries, ensure_ascii=False)),
            )
            if started:
                assert_current_operation_lease(conn)
                conn.commit()
        except Exception:
            if started:
                conn.rollback()
            raise
        finally:
            if managed:
                conn.close()

    def _visibility(self, names: list[str]) -> tuple[str, list[str], dict[str, list[dict]]]:
        aliases = {row["slug"]: row["display_name"] for row in self.execute("SELECT slug, display_name FROM rss_sources").fetchall()}
        clauses, params, snapshots = [], [], {}
        for source in AI_SOURCES:
            selected = set(names) & {source["name"], aliases.get(source.get("rss_slug"))}
            if not source.get("snapshot") or not selected:
                continue
            entries = self.source_snapshot(source["key"])
            urls = [entry["story_url"] for entry in entries]
            for name in sorted(selected):
                snapshots[name] = entries
                clause = "n.source_site != ?"
                params.append(name)
                if urls:
                    clause += " OR n.source_url IN (" + ",".join("?" for _ in urls) + ")"
                    params.extend(urls)
                clauses.append(f"({clause})")
        return " AND ".join(clauses) or "1=1", params, snapshots

    def record_translation_batch(self, event: dict) -> None:
        self.execute(
            """INSERT INTO news_translation_batches
            (source_key, model, item_count, input_tokens, output_tokens, reasoning_tokens, success, error, started_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event["source_key"], event["model"], event["item_count"], event.get("input_tokens"),
             event.get("output_tokens"), event.get("reasoning_tokens"), bool(event["success"]),
             event.get("error_message"), event["started_at"], event["completed_at"]),
        )

    def translation_candidates(self, names: list[str]) -> list[dict]:
        marks = ",".join("?" for _ in names)
        visible, urls, _ = self._visibility(names)
        rows = self.execute(
            f"""SELECT n.id, n.title, n.content, n.source_site FROM news n {TRANSLATION_JOIN}
                WHERE n.source_site IN ({marks}) AND n.type = 'article' AND t.news_id IS NULL AND {visible}
                ORDER BY n.published_at DESC, n.id DESC""", tuple([*names, *urls]),
        ).fetchall()
        return [dict(row) for row in rows]

    def save_translation(self, item: dict, translated: dict, model: str) -> None:
        self.execute(
            """INSERT INTO news_translations
               (news_id, source_title, source_content_prefix, title_zh, excerpt_zh, model, translated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(news_id) DO UPDATE SET
               source_title=excluded.source_title, source_content_prefix=excluded.source_content_prefix,
               title_zh=excluded.title_zh, excerpt_zh=excluded.excerpt_zh,
               model=excluded.model, translated_at=excluded.translated_at""",
            (item["id"], item["title"], (item["content"] or "")[:TRANSLATION_SOURCE_CHARS],
             translated.get("title", ""), translated.get("excerpt", ""), model, datetime.now(timezone.utc).isoformat()),
        )

    def source_stats(self, names: list[str]) -> dict:
        marks = ",".join("?" for _ in names)
        visible, urls, _ = self._visibility(names)
        row = self.execute(
            f"SELECT COUNT(*) AS total, MAX(scraped_at) AS last_collected_at FROM news n WHERE source_site IN ({marks}) AND type = 'article' AND {visible}",
            tuple([*names, *urls]),
        ).fetchone()
        return dict(row)

    def list_items(self, names: list[str], query: str, limit: int, offset: int) -> dict:
        marks = ",".join("?" for _ in names)
        visible, urls, snapshots = self._visibility(names)
        where = f"n.source_site IN ({marks}) AND n.type = 'article' AND {visible}"
        params = [*names, *urls]
        if query:
            where += " AND (instr(lower(n.title), lower(?)) > 0 OR instr(lower(n.content), lower(?)) > 0 OR instr(t.title_zh, ?) > 0 OR instr(t.excerpt_zh, ?) > 0)"
            params.extend([query, query, query, query])
        total = self.execute(f"SELECT COUNT(*) AS total FROM news n {TRANSLATION_JOIN} WHERE {where}", tuple(params)).fetchone()["total"]
        order = "n.published_at DESC, n.id DESC"
        order_params = []
        if names and all(name in snapshots for name in names):
            entries = snapshots[names[0]]
            if entries and all(snapshots[name] == entries for name in names):
                order_params = [entry["story_url"] for entry in entries]
                order = "CASE n.source_url " + " ".join(f"WHEN ? THEN {index}" for index in range(len(order_params))) + " END"
        rows = self.execute(
            f"""SELECT n.id, n.title, n.content, n.source_site, n.source_url, n.published_at, n.scraped_at, n.author,
                t.title_zh, t.excerpt_zh FROM news n {TRANSLATION_JOIN} WHERE {where}
                ORDER BY {order} LIMIT ? OFFSET ?""",
            tuple([*params, *order_params, limit, offset]),
        ).fetchall()
        items = [dict(row) for row in rows]
        links = {entry["story_url"]: entry["source_url"] for entries in snapshots.values() for entry in entries}
        for item in items:
            item["source_url"] = links.get(item["source_url"], item["source_url"])
        return {"items": items, "total": total, "limit": limit, "offset": offset}
