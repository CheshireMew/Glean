from __future__ import annotations

from typing import Dict, Iterable, Optional

from shared.content_contract import EVENT_SOURCE_TABLE, EVENT_TABLE, INCOMING_STAGE

from .base_repository import BaseRepository


class EventRepository(BaseRepository):
    """Owns event membership, canonical-source identity and event write invariants."""

    def create_event(self, primary: Dict, event_key: str) -> int:
        cursor = self.execute(
            f"""
            INSERT INTO {EVENT_TABLE} (
                canonical_news_id, title, content, content_type, published_at,
                first_seen_at, last_seen_at, source_count, event_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                primary["id"],
                primary["title"],
                primary.get("content") or "",
                primary.get("type") or "news",
                primary["published_at"],
                primary["scraped_at"],
                primary["scraped_at"],
                event_key,
            ),
        )
        return int(cursor.lastrowid)

    def add_sources(
        self,
        event_id: int,
        members: Iterable,
        canonical_news_id: int,
        event_match_score: float | None = None,
    ) -> None:
        for member in members:
            item = member.item
            is_primary = item["id"] == canonical_news_id
            similarity = (
                min(member.similarity, event_match_score)
                if event_match_score is not None
                else member.similarity
            )
            self.execute(
                f"""
                INSERT INTO {EVENT_SOURCE_TABLE} (event_id, news_id, similarity, is_primary)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(news_id) DO UPDATE SET
                    event_id = excluded.event_id,
                    similarity = excluded.similarity,
                    is_primary = excluded.is_primary
                """,
                (event_id, item["id"], similarity, int(is_primary)),
            )
        self.refresh_event(event_id)

    def refresh_event(self, event_id: int) -> None:
        self.execute(
            f"""
            UPDATE {EVENT_TABLE}
            SET source_count = (SELECT COUNT(*) FROM {EVENT_SOURCE_TABLE} WHERE event_id = ?),
                first_seen_at = COALESCE((
                    SELECT MIN(n.scraped_at) FROM {EVENT_SOURCE_TABLE} es JOIN news n ON n.id = es.news_id WHERE es.event_id = ?
                ), first_seen_at),
                last_seen_at = COALESCE((
                    SELECT MAX(n.scraped_at) FROM {EVENT_SOURCE_TABLE} es JOIN news n ON n.id = es.news_id WHERE es.event_id = ?
                ), last_seen_at),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (event_id, event_id, event_id, event_id),
        )

    def get_event_id_for_news(self, news_id: int) -> Optional[int]:
        membership = self.get_membership(news_id)
        return int(membership["event_id"]) if membership else None

    def get_membership(self, news_id: int) -> Dict | None:
        row = self.execute(
            f"SELECT event_id, is_primary FROM {EVENT_SOURCE_TABLE} WHERE news_id = ?",
            (news_id,),
        ).fetchone()
        return dict(row) if row else None

    def remove_source(self, event_id: int, news_id: int) -> None:
        self.execute(
            f"DELETE FROM {EVENT_SOURCE_TABLE} WHERE event_id = ? AND news_id = ?",
            (event_id, news_id),
        )

    def replace_primary_source(self, event_id: int, replacement: Dict) -> None:
        replacement_id = int(replacement["id"])
        self.execute(
            f"UPDATE {EVENT_SOURCE_TABLE} SET is_primary = CASE WHEN news_id = ? THEN 1 ELSE 0 END WHERE event_id = ?",
            (replacement_id, event_id),
        )
        self.execute(
            "UPDATE news SET is_event_primary = CASE WHEN id = ? THEN 1 ELSE 0 END WHERE event_id = ?",
            (replacement_id, event_id),
        )
        self.execute(
            f"""
            UPDATE {EVENT_TABLE}
            SET canonical_news_id = ?, title = ?, content = ?, published_at = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                replacement_id,
                replacement["title"],
                replacement.get("content") or "",
                replacement["published_at"],
                event_id,
            ),
        )

    def delete_event_records(self, event_id: int) -> None:
        self.execute(f"DELETE FROM {EVENT_SOURCE_TABLE} WHERE event_id = ?", (event_id,))
        self.execute(f"DELETE FROM {EVENT_TABLE} WHERE id = ?", (event_id,))

    def dissolve_event_records(self, event_id: int) -> None:
        self.execute(
            "UPDATE news SET stage = ?, event_id = NULL, event_similarity = NULL, is_event_primary = 0 WHERE event_id = ?",
            (INCOMING_STAGE, event_id),
        )
        self.delete_event_records(event_id)

    def delete_news(self, news_id: int) -> bool:
        return self.execute("DELETE FROM news WHERE id = ?", (news_id,)).rowcount > 0

    def delete_news_ids(self, news_ids: Iterable[int]) -> int:
        values = list(dict.fromkeys(int(news_id) for news_id in news_ids))
        if not values:
            return 0
        placeholders = ",".join("?" for _ in values)
        return self.execute(
            f"DELETE FROM news WHERE id IN ({placeholders})", tuple(values)
        ).rowcount
