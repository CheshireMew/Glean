from __future__ import annotations

import json
from typing import Dict, Optional

from .base_repository import BaseRepository


class AnalystSubscriptionRepository(BaseRepository):
    JSON_FIELDS = {
        "object_types_json": "object_types",
        "content_types_json": "content_types",
        "profile_slugs_json": "profile_slugs",
    }

    @classmethod
    def _hydrate(cls, row) -> Optional[Dict]:
        if not row:
            return None
        item = dict(row)
        for source, target in cls.JSON_FIELDS.items():
            item[target] = json.loads(item.pop(source) or "[]")
        return item

    def list_subscriptions(self, enabled_only: bool = False) -> list[Dict]:
        where = "WHERE s.enabled = 1" if enabled_only else ""
        rows = self.execute(
            f"""
            SELECT s.*, c.slug AS channel_slug, c.name AS channel_name,
                   c.channel_type, c.enabled AS channel_enabled
            FROM analyst_subscriptions s
            JOIN publication_channels c ON c.id = s.channel_id
            {where}
            ORDER BY s.enabled DESC, s.name
            """
        ).fetchall()
        return [self._hydrate(row) for row in rows]

    def get_subscription(self, subscription_id: int) -> Optional[Dict]:
        row = self.execute(
            """
            SELECT s.*, c.slug AS channel_slug, c.name AS channel_name,
                   c.channel_type, c.enabled AS channel_enabled
            FROM analyst_subscriptions s
            JOIN publication_channels c ON c.id = s.channel_id
            WHERE s.id = ?
            """,
            (subscription_id,),
        ).fetchone()
        return self._hydrate(row)

    def save_subscription(
        self, values: Dict, subscription_id: int | None = None, initial_cursor: int = 0
    ) -> int:
        if subscription_id is None:
            cursor = self.execute(
                """
                INSERT INTO analyst_subscriptions(
                    name, channel_id, enabled, object_types_json, content_types_json,
                    profile_slugs_json, cursor, batch_size
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    values["name"], values["channel_id"], bool(values.get("enabled", True)),
                    json.dumps(values.get("object_types") or [], ensure_ascii=False),
                    json.dumps(values.get("content_types") or [], ensure_ascii=False),
                    json.dumps(values.get("profile_slugs") or [], ensure_ascii=False),
                    initial_cursor, int(values.get("batch_size") or 50),
                ),
            )
            return int(cursor.lastrowid)
        columns = {
            "name": "name",
            "channel_id": "channel_id",
            "enabled": "enabled",
            "object_types": "object_types_json",
            "content_types": "content_types_json",
            "profile_slugs": "profile_slugs_json",
            "batch_size": "batch_size",
        }
        changes = {}
        for key, column in columns.items():
            if key not in values:
                continue
            value = values[key]
            if key in {"object_types", "content_types", "profile_slugs"}:
                value = json.dumps(value or [], ensure_ascii=False)
            changes[column] = value
        if not changes:
            return subscription_id if self.get_subscription(subscription_id) else 0
        assignments = [f"{column} = ?" for column in changes]
        assignments.append("updated_at = CURRENT_TIMESTAMP")
        cursor = self.execute(
            f"UPDATE analyst_subscriptions SET {', '.join(assignments)} WHERE id = ?",
            (*changes.values(), subscription_id),
        )
        return subscription_id if cursor.rowcount > 0 else 0

    def current_cursor(self) -> int:
        row = self.execute("SELECT COALESCE(MAX(id), 0) AS cursor FROM analyst_change_log").fetchone()
        return int(row["cursor"])

    def list_changes(self, cursor: int, limit: int) -> list[Dict]:
        rows = self.execute(
            """
            SELECT id AS cursor, object_type, object_id, action, occurred_at
            FROM analyst_change_log WHERE id > ? ORDER BY id LIMIT ?
            """,
            (cursor, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_correction(self, correction_id: int) -> Optional[Dict]:
        row = self.execute(
            """
            SELECT c.*, COALESCE(e.content_type, re.content_type, dr.type) AS content_type,
                   COALESCE(re.profile_slug, dr.profile_slug) AS profile_slug
            FROM publication_corrections c
            LEFT JOIN content_events e ON e.id = c.event_id
            LEFT JOIN review_entries re ON re.id = c.review_entry_id
            LEFT JOIN daily_reports dr ON dr.id = c.report_id
            WHERE c.id = ?
            """,
            (correction_id,),
        ).fetchone()
        return dict(row) if row else None

    def advance_cursor(self, subscription_id: int, cursor: int, delivered: bool) -> bool:
        result = self.execute(
            """
            UPDATE analyst_subscriptions
            SET cursor = ?,
                last_delivered_at = CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE last_delivered_at END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND cursor <= ?
            """,
            (cursor, delivered, subscription_id, cursor),
        )
        return result.rowcount > 0

    def complete_batch(self, subscription_id: int, cursor_from: int, cursor_to: int) -> bool:
        result = self.execute('''
            UPDATE analyst_subscriptions SET cursor=?, last_delivered_at=CURRENT_TIMESTAMP,
                updated_at=CURRENT_TIMESTAMP WHERE id=? AND cursor=?
        ''', (cursor_to, subscription_id, cursor_from))
        if result.rowcount:
            return True
        current = self.get_subscription(subscription_id)
        return bool(current and current['cursor'] >= cursor_to)
