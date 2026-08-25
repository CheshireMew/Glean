from __future__ import annotations

import json
from typing import Dict, Optional

from .base_repository import BaseRepository


class PublicationRepository(BaseRepository):
    def ensure_for_profile(self, profile: Dict) -> Dict:
        self.execute(
            """
            INSERT INTO profile_publications(
                profile_slug, public_slug, display_name, enabled, is_public, rss_enabled
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(profile_slug) DO UPDATE SET
                display_name = CASE
                    WHEN profile_publications.display_name = '' THEN excluded.display_name
                    ELSE profile_publications.display_name
                END,
                enabled = excluded.enabled,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                profile["slug"],
                profile["slug"],
                profile["name"],
                bool(profile.get("enabled", True)),
                bool(profile.get("is_default", False)),
                bool(profile.get("is_default", False)),
            ),
        )
        return self.get_publication_by_profile(profile["slug"])

    def list_publications(self, public_only: bool = False) -> list[Dict]:
        where = "WHERE p.enabled = 1 AND p.is_public = 1" if public_only else ""
        rows = self.execute(
            f"""
            SELECT p.*, e.name AS profile_name, e.content_type, e.min_score,
                   e.max_items, e.max_per_category, e.max_per_source
            FROM profile_publications p
            JOIN editorial_profiles e ON e.slug = p.profile_slug
            {where}
            ORDER BY e.content_type, p.display_name
            """
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["template"] = json.loads(item.pop("template_json") or "{}")
            item["targets"] = self.list_targets(item["id"])
            result.append(item)
        return result

    def get_publication(self, publication_id: int) -> Optional[Dict]:
        row = self.execute(
            """
            SELECT p.*, e.name AS profile_name, e.content_type
            FROM profile_publications p JOIN editorial_profiles e ON e.slug = p.profile_slug
            WHERE p.id = ?
            """,
            (publication_id,),
        ).fetchone()
        return self._hydrate_publication(row)

    def get_publication_by_profile(self, profile_slug: str) -> Optional[Dict]:
        row = self.execute(
            """
            SELECT p.*, e.name AS profile_name, e.content_type
            FROM profile_publications p JOIN editorial_profiles e ON e.slug = p.profile_slug
            WHERE p.profile_slug = ?
            """,
            (profile_slug,),
        ).fetchone()
        return self._hydrate_publication(row)

    def get_publication_by_public_slug(self, public_slug: str) -> Optional[Dict]:
        row = self.execute(
            """
            SELECT p.*, e.name AS profile_name, e.content_type
            FROM profile_publications p JOIN editorial_profiles e ON e.slug = p.profile_slug
            WHERE p.public_slug = ? AND p.enabled = 1 AND p.is_public = 1
            """,
            (public_slug,),
        ).fetchone()
        return self._hydrate_publication(row)

    def _hydrate_publication(self, row) -> Optional[Dict]:
        if not row:
            return None
        item = dict(row)
        item["template"] = json.loads(item.pop("template_json") or "{}")
        item["targets"] = self.list_targets(item["id"])
        return item

    def update_publication(self, publication_id: int, values: Dict) -> bool:
        allowed = {
            "public_slug",
            "display_name",
            "description",
            "enabled",
            "is_public",
            "rss_enabled",
            "digest_frequency",
            "digest_time",
            "timezone",
            "template_json",
        }
        changes = {key: value for key, value in values.items() if key in allowed}
        if "template" in values:
            changes["template_json"] = json.dumps(values["template"], ensure_ascii=False)
        if not changes:
            return False
        assignments = [f"{key} = ?" for key in changes]
        assignments.append("updated_at = CURRENT_TIMESTAMP")
        cursor = self.execute(
            f"UPDATE profile_publications SET {', '.join(assignments)} WHERE id = ?",
            tuple([*changes.values(), publication_id]),
        )
        return cursor.rowcount > 0

    def list_channels(self, include_disabled: bool = True) -> list[Dict]:
        where = "" if include_disabled else "WHERE enabled = 1"
        rows = self.execute(
            f"SELECT * FROM publication_channels {where} ORDER BY channel_type, name"
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["config"] = json.loads(item.pop("config_json") or "{}")
            result.append(item)
        return result

    def get_channel(self, channel_id: int) -> Optional[Dict]:
        row = self.execute("SELECT * FROM publication_channels WHERE id = ?", (channel_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["config"] = json.loads(item.pop("config_json") or "{}")
        return item

    def get_channel_by_slug(self, slug: str) -> Optional[Dict]:
        row = self.execute("SELECT * FROM publication_channels WHERE slug = ?", (slug,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["config"] = json.loads(item.pop("config_json") or "{}")
        return item

    def save_channel(self, values: Dict, channel_id: int | None = None) -> int:
        payload = (
            values["slug"],
            values["name"],
            values["channel_type"],
            bool(values.get("enabled", True)),
            json.dumps(values.get("config") or {}, ensure_ascii=False),
        )
        if channel_id is None:
            cursor = self.execute(
                """
                INSERT INTO publication_channels(slug, name, channel_type, enabled, config_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                payload,
            )
            return int(cursor.lastrowid)
        cursor = self.execute(
            """
            UPDATE publication_channels
            SET slug = ?, name = ?, channel_type = ?, enabled = ?, config_json = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (*payload, channel_id),
        )
        return channel_id if cursor.rowcount > 0 else 0

    def list_targets(self, publication_id: int) -> list[Dict]:
        rows = self.execute(
            """
            SELECT t.publication_id, t.channel_id, t.delivery_mode, t.enabled,
                   c.slug AS channel_slug, c.name AS channel_name, c.channel_type,
                   c.enabled AS channel_enabled
            FROM publication_targets t
            JOIN publication_channels c ON c.id = t.channel_id
            WHERE t.publication_id = ?
            ORDER BY t.delivery_mode, c.name
            """,
            (publication_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def replace_targets(self, publication_id: int, targets: list[Dict]) -> None:
        self.execute("DELETE FROM publication_targets WHERE publication_id = ?", (publication_id,))
        for target in targets:
            self.execute(
                """
                INSERT INTO publication_targets(publication_id, channel_id, delivery_mode, enabled)
                VALUES (?, ?, ?, ?)
                """,
                (
                    publication_id,
                    target["channel_id"],
                    target["delivery_mode"],
                    bool(target.get("enabled", True)),
                ),
            )
