from __future__ import annotations

import json
from typing import Dict, Optional

from shared.content_contract import EVENT_TABLE, REVIEW_TABLE

from .base_repository import BaseRepository
from .public_visibility import published_entry_sql


class IntelligenceCatalogRepository(BaseRepository):
    def list_entities(self, entity_type: str | None = None, query: str | None = None) -> list[Dict]:
        where = []
        params: list[object] = []
        if entity_type:
            where.append("e.entity_type = ?")
            params.append(entity_type)
        if query:
            where.append(
                "(e.name LIKE ? OR e.symbol LIKE ? OR EXISTS (SELECT 1 FROM entity_aliases a WHERE a.entity_id = e.id AND a.alias LIKE ?))"
            )
            term = f"%{query}%"
            params.extend((term, term, term))
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        rows = self.execute(
            f"""
            SELECT e.*, (SELECT COUNT(DISTINCT event_id) FROM event_entities ee WHERE ee.entity_id = e.id) AS event_count
            FROM entities e {where_sql} ORDER BY event_count DESC, e.name
            """,
            tuple(params),
        ).fetchall()
        return [self._hydrate_entity(dict(row)) for row in rows]

    def get_entity(self, entity_id: int) -> Optional[Dict]:
        row = self.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
        return self._hydrate_entity(dict(row)) if row else None

    def get_entity_by_slug(self, slug: str) -> Optional[Dict]:
        row = self.execute("SELECT * FROM entities WHERE slug = ?", (slug,)).fetchone()
        return self._hydrate_entity(dict(row)) if row else None

    def _hydrate_entity(self, item: Dict) -> Dict:
        item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        item["aliases"] = [
            row["alias"]
            for row in self.execute(
                "SELECT alias FROM entity_aliases WHERE entity_id = ? ORDER BY alias", (item["id"],)
            ).fetchall()
        ]
        return item

    def save_entity(self, values: Dict, entity_id: int | None = None) -> int:
        payload = (
            values["entity_type"],
            values["slug"],
            values["name"],
            values.get("symbol"),
            values.get("description", ""),
            json.dumps(values.get("metadata") or {}, ensure_ascii=False),
        )
        if entity_id is None:
            cursor = self.execute(
                """
                INSERT INTO entities(entity_type, slug, name, symbol, description, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                payload,
            )
            entity_id = int(cursor.lastrowid)
        else:
            cursor = self.execute(
                """
                UPDATE entities SET entity_type = ?, slug = ?, name = ?, symbol = ?,
                    description = ?, metadata_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (*payload, entity_id),
            )
            if cursor.rowcount <= 0:
                return 0
        if "aliases" in values:
            self.execute("DELETE FROM entity_aliases WHERE entity_id = ?", (entity_id,))
            for alias in values["aliases"]:
                normalized = " ".join(alias.casefold().split())
                self.execute(
                    "INSERT INTO entity_aliases(entity_id, alias, normalized_alias) VALUES (?, ?, ?)",
                    (entity_id, alias, normalized),
                )
        return entity_id

    def list_entity_events(self, entity_id: int, public_only: bool, limit: int, offset: int) -> Dict:
        public_join = (
            f"AND EXISTS (SELECT 1 FROM {REVIEW_TABLE} r WHERE r.event_id = e.id AND r.review_status = 'selected' AND {published_entry_sql()})"
            if public_only else ""
        )
        total = self.execute(
            f"SELECT COUNT(*) AS total FROM event_entities ee JOIN {EVENT_TABLE} e ON e.id = ee.event_id WHERE ee.entity_id = ? {public_join}",
            (entity_id,),
        ).fetchone()["total"]
        rows = self.execute(
            f"""
            SELECT e.*, ee.role, ee.confidence
            FROM event_entities ee JOIN {EVENT_TABLE} e ON e.id = ee.event_id
            WHERE ee.entity_id = ? {public_join}
            ORDER BY e.last_seen_at DESC LIMIT ? OFFSET ?
            """,
            (entity_id, limit, offset),
        ).fetchall()
        return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}

    def attach_entity(self, event_id: int, entity_id: int, role: str, confidence: float, source: str) -> None:
        self.execute(
            """
            INSERT INTO event_entities(event_id, entity_id, role, confidence, source)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(event_id, entity_id, role) DO UPDATE SET
                confidence = CASE
                    WHEN event_entities.source = 'manual' AND excluded.source != 'manual'
                    THEN event_entities.confidence ELSE excluded.confidence END,
                source = CASE
                    WHEN event_entities.source = 'manual' AND excluded.source != 'manual'
                    THEN event_entities.source ELSE excluded.source END
            """,
            (event_id, entity_id, role, confidence, source),
        )
        self.execute(f"UPDATE {EVENT_TABLE} SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (event_id,))

    def list_narratives(self, enabled_only: bool = False) -> list[Dict]:
        where = "WHERE n.enabled = 1" if enabled_only else ""
        rows = self.execute(
            f"""
            SELECT n.*, (SELECT COUNT(*) FROM event_narratives en WHERE en.narrative_id = n.id) AS event_count
            FROM narratives n {where} ORDER BY event_count DESC, n.name
            """
        ).fetchall()
        return [self._hydrate_narrative(dict(row)) for row in rows]

    @staticmethod
    def _hydrate_narrative(item: Dict) -> Dict:
        item["keywords"] = json.loads(item.pop("keywords_json", None) or "[]")
        return item

    def get_narrative(self, narrative_id: int) -> Optional[Dict]:
        row = self.execute("SELECT * FROM narratives WHERE id = ?", (narrative_id,)).fetchone()
        return self._hydrate_narrative(dict(row)) if row else None

    def get_narrative_by_slug(self, slug: str) -> Optional[Dict]:
        row = self.execute("SELECT * FROM narratives WHERE slug = ?", (slug,)).fetchone()
        return self._hydrate_narrative(dict(row)) if row else None

    def save_narrative(self, values: Dict, narrative_id: int | None = None) -> int:
        payload = (
            values["slug"], values["name"], values.get("description", ""),
            json.dumps(values.get("keywords") or [], ensure_ascii=False),
            bool(values.get("enabled", True)),
        )
        if narrative_id is None:
            cursor = self.execute(
                "INSERT INTO narratives(slug, name, description, keywords_json, enabled) VALUES (?, ?, ?, ?, ?)", payload
            )
            return int(cursor.lastrowid)
        cursor = self.execute(
            """
            UPDATE narratives SET slug = ?, name = ?, description = ?, keywords_json = ?, enabled = ?,
                updated_at = CURRENT_TIMESTAMP WHERE id = ?
            """,
            (*payload, narrative_id),
        )
        return narrative_id if cursor.rowcount > 0 else 0

    def attach_narrative(self, event_id: int, narrative_id: int, confidence: float, source: str) -> None:
        self.execute(
            """
            INSERT INTO event_narratives(event_id, narrative_id, confidence, source)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(event_id, narrative_id) DO UPDATE SET
                confidence = CASE
                    WHEN event_narratives.source = 'manual' AND excluded.source != 'manual'
                    THEN event_narratives.confidence ELSE excluded.confidence END,
                source = CASE
                    WHEN event_narratives.source = 'manual' AND excluded.source != 'manual'
                    THEN event_narratives.source ELSE excluded.source END
            """,
            (event_id, narrative_id, confidence, source),
        )
        self.execute(f"UPDATE {EVENT_TABLE} SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (event_id,))

    def sync_rule_classification(
        self, event_id: int, entity_matches: list[Dict], narrative_matches: list[Dict]
    ) -> None:
        entity_ids = [int(item["entity_id"]) for item in entity_matches]
        narrative_ids = [int(item["narrative_id"]) for item in narrative_matches]
        entity_placeholders = ",".join("?" for _ in entity_ids)
        narrative_placeholders = ",".join("?" for _ in narrative_ids)
        entity_filter = f" AND entity_id NOT IN ({entity_placeholders})" if entity_ids else ""
        narrative_filter = f" AND narrative_id NOT IN ({narrative_placeholders})" if narrative_ids else ""
        self.execute(
            f"DELETE FROM event_entities WHERE event_id = ? AND source = 'rule'{entity_filter}",
            (event_id, *entity_ids),
        )
        self.execute(
            f"DELETE FROM event_narratives WHERE event_id = ? AND source = 'rule'{narrative_filter}",
            (event_id, *narrative_ids),
        )
        for item in entity_matches:
            self.attach_entity(
                event_id, int(item["entity_id"]), item["role"], float(item["confidence"]), "rule"
            )
        for item in narrative_matches:
            self.attach_narrative(
                event_id, int(item["narrative_id"]), float(item["confidence"]), "rule"
            )

    def list_narrative_trend(self, narrative_id: int, days: int = 90) -> Dict:
        rows = self.execute(
            f"""
            SELECT date(e.last_seen_at) AS date, COUNT(DISTINCT e.id) AS count
            FROM event_narratives en
            JOIN {EVENT_TABLE} e ON e.id = en.event_id
            WHERE en.narrative_id = ? AND datetime(e.last_seen_at) >= datetime('now', ?)
              AND EXISTS (
                SELECT 1 FROM {REVIEW_TABLE} r
                WHERE r.event_id = e.id AND r.review_status = 'selected'
                  AND {published_entry_sql()}
              )
            GROUP BY date(e.last_seen_at) ORDER BY date(e.last_seen_at)
            """,
            (narrative_id, f"-{days} days"),
        ).fetchall()
        points = [dict(row) for row in rows]
        return {"days": days, "total": sum(int(item["count"]) for item in points), "points": points}

    def list_narrative_events(self, narrative_id: int, public_only: bool, limit: int, offset: int) -> Dict:
        public_join = (
            f"AND EXISTS (SELECT 1 FROM {REVIEW_TABLE} r WHERE r.event_id = e.id AND r.review_status = 'selected' AND {published_entry_sql()})"
            if public_only else ""
        )
        total = self.execute(
            f"SELECT COUNT(*) AS total FROM event_narratives en JOIN {EVENT_TABLE} e ON e.id = en.event_id WHERE en.narrative_id = ? {public_join}",
            (narrative_id,),
        ).fetchone()["total"]
        rows = self.execute(
            f"""
            SELECT e.*, en.confidence FROM event_narratives en JOIN {EVENT_TABLE} e ON e.id = en.event_id
            WHERE en.narrative_id = ? {public_join}
            ORDER BY e.last_seen_at DESC LIMIT ? OFFSET ?
            """,
            (narrative_id, limit, offset),
        ).fetchall()
        return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}

    def list_watchlists(self, public_only: bool = False) -> list[Dict]:
        where = "WHERE visibility = 'public' AND enabled = 1" if public_only else ""
        rows = self.execute(f"SELECT * FROM watchlists {where} ORDER BY name").fetchall()
        return [self.get_watchlist(int(row["id"])) for row in rows]

    def get_watchlist(self, watchlist_id: int) -> Optional[Dict]:
        row = self.execute("SELECT * FROM watchlists WHERE id = ?", (watchlist_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["entity_ids"] = [row["entity_id"] for row in self.execute("SELECT entity_id FROM watchlist_entities WHERE watchlist_id = ? ORDER BY entity_id", (watchlist_id,)).fetchall()]
        item["narrative_ids"] = [row["narrative_id"] for row in self.execute("SELECT narrative_id FROM watchlist_narratives WHERE watchlist_id = ? ORDER BY narrative_id", (watchlist_id,)).fetchall()]
        return item

    def save_watchlist(self, values: Dict, watchlist_id: int | None = None) -> int:
        payload = (values["name"], values.get("description", ""), bool(values.get("enabled", True)), values.get("visibility", "private"))
        if watchlist_id is None:
            cursor = self.execute("INSERT INTO watchlists(name, description, enabled, visibility) VALUES (?, ?, ?, ?)", payload)
            watchlist_id = int(cursor.lastrowid)
        else:
            cursor = self.execute(
                "UPDATE watchlists SET name = ?, description = ?, enabled = ?, visibility = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (*payload, watchlist_id),
            )
            if cursor.rowcount <= 0:
                return 0
        if "entity_ids" in values:
            self.execute("DELETE FROM watchlist_entities WHERE watchlist_id = ?", (watchlist_id,))
            for entity_id in values["entity_ids"]:
                self.execute("INSERT INTO watchlist_entities(watchlist_id, entity_id) VALUES (?, ?)", (watchlist_id, entity_id))
        if "narrative_ids" in values:
            self.execute("DELETE FROM watchlist_narratives WHERE watchlist_id = ?", (watchlist_id,))
            for narrative_id in values["narrative_ids"]:
                self.execute("INSERT INTO watchlist_narratives(watchlist_id, narrative_id) VALUES (?, ?)", (watchlist_id, narrative_id))
        return watchlist_id

    def list_alert_policies(self, enabled_only: bool = False) -> list[Dict]:
        where = "WHERE a.enabled = 1" if enabled_only else ""
        rows = self.execute(
            f"""
            SELECT a.*, w.name AS watchlist_name, c.name AS channel_name, c.channel_type
            FROM alert_policies a
            LEFT JOIN watchlists w ON w.id = a.watchlist_id
            JOIN publication_channels c ON c.id = a.channel_id
            {where} ORDER BY a.enabled DESC, a.name
            """
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["conditions"] = json.loads(item.pop("conditions_json") or "{}")
            item["quiet_hours"] = json.loads(item.pop("quiet_hours_json") or "{}")
            result.append(item)
        return result

    def get_alert_policy(self, policy_id: int) -> Optional[Dict]:
        item = next((item for item in self.list_alert_policies() if int(item["id"]) == policy_id), None)
        return item

    def save_alert_policy(self, values: Dict, policy_id: int | None = None) -> int:
        payload = (
            values["name"], values.get("description", ""), bool(values.get("enabled", True)),
            values.get("watchlist_id"), values.get("profile_slug"),
            json.dumps(values.get("conditions") or {}, ensure_ascii=False),
            values.get("schedule_type", "instant"),
            json.dumps(values.get("quiet_hours") or {}, ensure_ascii=False), values["channel_id"],
        )
        if policy_id is None:
            cursor = self.execute(
                """
                INSERT INTO alert_policies(name, description, enabled, watchlist_id, profile_slug,
                    conditions_json, schedule_type, quiet_hours_json, channel_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, payload
            )
            return int(cursor.lastrowid)
        cursor = self.execute(
            """
            UPDATE alert_policies SET name = ?, description = ?, enabled = ?, watchlist_id = ?,
                profile_slug = ?, conditions_json = ?, schedule_type = ?, quiet_hours_json = ?,
                channel_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?
            """, (*payload, policy_id)
        )
        return policy_id if cursor.rowcount > 0 else 0

    def channel_exists(self, channel_id: int) -> bool:
        return self.execute(
            "SELECT 1 FROM publication_channels WHERE id = ?", (channel_id,)
        ).fetchone() is not None

    def list_candidate_events(self, hours: int) -> list[int]:
        rows = self.execute(
            f"""
            SELECT DISTINCT e.id FROM {EVENT_TABLE} e
            JOIN {REVIEW_TABLE} r ON r.event_id = e.id
            WHERE r.review_status = 'selected' AND e.last_seen_at >= datetime('now', ?)
            ORDER BY e.last_seen_at ASC
            """,
            (f"-{hours} hours",),
        ).fetchall()
        return [int(row["id"]) for row in rows]

    def save_alert_match(self, policy_id: int, event_id: int) -> bool:
        cursor = self.execute(
            "INSERT OR IGNORE INTO alert_matches(policy_id, event_id) VALUES (?, ?)",
            (policy_id, event_id),
        )
        return cursor.rowcount > 0

    def update_policy_evaluated(self, policy_id: int) -> None:
        self.execute("UPDATE alert_policies SET last_evaluated_at = CURRENT_TIMESTAMP WHERE id = ?", (policy_id,))

    def list_alert_matches(self, status: str | None = None, limit: int = 200) -> list[Dict]:
        where = "WHERE m.status = ?" if status else ""
        params = (status, limit) if status else (limit,)
        rows = self.execute(
            f"""
            SELECT m.*, a.name AS policy_name, e.title AS event_title, e.content_type,
                   c.slug AS channel_slug, c.channel_type
            FROM alert_matches m JOIN alert_policies a ON a.id = m.policy_id
            JOIN content_events e ON e.id = m.event_id
            JOIN publication_channels c ON c.id = a.channel_id
            {where} ORDER BY m.matched_at DESC LIMIT ?
            """, params
        ).fetchall()
        return [dict(row) for row in rows]

    def update_alert_match(self, policy_id: int, event_id: int, status: str, operation_key: str | None = None) -> bool:
        cursor = self.execute(
            """
            UPDATE alert_matches SET status = ?, operation_key = COALESCE(?, operation_key),
                delivered_at = CASE WHEN ? = 'sent' THEN CURRENT_TIMESTAMP ELSE delivered_at END
            WHERE policy_id = ? AND event_id = ?
            """,
            (status, operation_key, status, policy_id, event_id),
        )
        return cursor.rowcount > 0
