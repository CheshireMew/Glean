from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Dict

from .base_repository import BaseRepository


class SourceOperationsRepository(BaseRepository):
    def sync_catalog(self, definitions: list[Dict]) -> int:
        changed = 0
        for definition in definitions:
            metadata = {
                "source_site": definition["source_site"],
                "content_kind": definition["content_kind"],
                "transport_kind": definition["transport_kind"],
                "default_limit": definition["default_limit"],
                "default_interval": definition["default_interval"],
            }
            cursor = self.execute(
                """
                INSERT INTO source_catalog(
                    source_key, display_name, source_type, authority_type, homepage_url,
                    is_official, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_key) DO UPDATE SET
                    display_name = excluded.display_name,
                    source_type = excluded.source_type,
                    authority_type = excluded.authority_type,
                    homepage_url = COALESCE(source_catalog.homepage_url, excluded.homepage_url),
                    is_official = excluded.is_official,
                    metadata_json = json_patch(source_catalog.metadata_json, excluded.metadata_json),
                    updated_at = CURRENT_TIMESTAMP
                WHERE source_catalog.display_name IS NOT excluded.display_name
                   OR source_catalog.source_type IS NOT excluded.source_type
                   OR source_catalog.authority_type IS NOT excluded.authority_type
                   OR source_catalog.homepage_url IS NOT COALESCE(source_catalog.homepage_url, excluded.homepage_url)
                   OR source_catalog.is_official IS NOT excluded.is_official
                   OR source_catalog.metadata_json IS NOT json_patch(source_catalog.metadata_json, excluded.metadata_json)
                """,
                (
                    definition["name"], definition["display_name"], definition["source_type"],
                    definition.get("authority_type") or "media", definition.get("homepage_url"),
                    bool(definition.get("is_official")), json.dumps(metadata, ensure_ascii=False),
                ),
            )
            changed += max(0, cursor.rowcount)
        return changed

    def list_sources(self) -> list[Dict]:
        rows = self.execute(
            """
            SELECT s.*, r.status AS runtime_status, r.last_run, r.last_result, r.last_error,
                   r.items_scraped, r.updated_at AS runtime_updated_at,
                   (SELECT COUNT(*) FROM source_incidents i WHERE i.source_key = s.source_key AND i.status != 'resolved') AS open_incident_count
            FROM source_catalog s
            LEFT JOIN scraper_runtime_state r ON r.scraper_name = s.source_key
            ORDER BY s.enabled DESC, s.is_official DESC, s.display_name COLLATE NOCASE
            """
        ).fetchall()
        result = []
        for row in rows:
            item = self._hydrate_source(row)
            snapshot = self.execute(
                "SELECT * FROM source_health_snapshots WHERE source_key = ? ORDER BY window_end DESC, id DESC LIMIT 1",
                (item["source_key"],),
            ).fetchone()
            item["latest_health"] = dict(snapshot) if snapshot else None
            result.append(item)
        return result

    def get_source(self, source_key: str) -> Dict | None:
        row = self.execute("SELECT * FROM source_catalog WHERE source_key = ?", (source_key,)).fetchone()
        return self._hydrate_source(row) if row else None

    @staticmethod
    def _hydrate_source(row) -> Dict:
        item = dict(row)
        try:
            item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            item["metadata"] = {}
        return item

    def update_source(self, source_key: str, values: Dict) -> bool:
        allowed = {"display_name", "authority_type", "homepage_url", "is_official", "enabled"}
        changes = {key: value for key, value in values.items() if key in allowed}
        metadata = values.get("metadata") if "metadata" in values else None
        if not changes and metadata is None:
            return False
        assignments = [f"{key} = ?" for key in changes]
        params = list(changes.values())
        if metadata is not None:
            assignments.append("metadata_json = json_patch(metadata_json, ?)")
            params.append(json.dumps(metadata or {}, ensure_ascii=False))
        cursor = self.execute(
            f"UPDATE source_catalog SET {', '.join(assignments)}, updated_at = CURRENT_TIMESTAMP WHERE source_key = ?",
            (*params, source_key),
        )
        return cursor.rowcount > 0

    def calculate_health(self, source_key: str, hours: int) -> Dict | None:
        source = self.get_source(source_key)
        if not source:
            return None
        source_site = source.get("metadata", {}).get("source_site") or source["display_name"]
        state = self.execute(
            "SELECT * FROM scraper_runtime_state WHERE scraper_name = ?", (source_key,)
        ).fetchone()
        metrics = self.execute(
            """
            SELECT COUNT(*) AS item_count,
                   AVG(MAX(0, (julianday(scraped_at) - julianday(published_at)) * 86400.0)) AS average_delay_seconds,
                   AVG(CASE WHEN TRIM(COALESCE(title, '')) != '' AND TRIM(COALESCE(content, '')) != '' THEN 1.0 ELSE 0.0 END) AS content_completeness,
                   AVG(CASE WHEN event_id IS NOT NULL THEN 1.0 ELSE 0.0 END) AS cluster_join_rate,
                   AVG(CASE WHEN EXISTS (
                       SELECT 1 FROM review_entries r
                       WHERE r.source_item_id = news.id AND r.review_status = 'selected'
                   ) THEN 1.0 ELSE 0.0 END) AS selection_rate
            FROM news
            WHERE source_site = ? AND scraped_at >= datetime('now', ?)
            """,
            (source_site, f"-{hours} hours"),
        ).fetchone()
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(hours=hours)
        run_count = 0
        success_count = 0
        error_count = 0
        zero_result_count = 0
        if state and state["last_run"]:
            try:
                last_run = datetime.fromisoformat(str(state["last_run"]).replace("Z", "+00:00"))
                if last_run.tzinfo is None:
                    last_run = last_run.replace(tzinfo=timezone.utc)
                if last_run >= window_start:
                    run_count = 1
                    if state["status"] == "error" or state["last_error"]:
                        error_count = 1
                    else:
                        success_count = 1
                    zero_result_count = 1 if int(state["items_scraped"] or 0) == 0 else 0
            except ValueError:
                pass
        item_count = int(metrics["item_count"] or 0)
        return {
            "source_key": source_key,
            "window_start": window_start.isoformat(),
            "window_end": now.isoformat(),
            "run_count": run_count,
            "success_count": success_count,
            "error_count": error_count,
            "zero_result_count": zero_result_count,
            "item_count": item_count,
            "average_delay_seconds": metrics["average_delay_seconds"],
            "content_completeness": metrics["content_completeness"] if item_count else None,
            "cluster_join_rate": metrics["cluster_join_rate"] if item_count else None,
            "selection_rate": metrics["selection_rate"] if item_count else None,
            "last_run": state["last_run"] if state else None,
            "last_error": state["last_error"] if state else None,
        }

    def save_health_snapshot(self, values: Dict) -> int:
        cursor = self.execute(
            """
            INSERT INTO source_health_snapshots(
                source_key, window_start, window_end, run_count, success_count, error_count,
                zero_result_count, item_count, average_delay_seconds, content_completeness,
                cluster_join_rate, selection_rate
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(values.get(key) for key in (
                "source_key", "window_start", "window_end", "run_count", "success_count",
                "error_count", "zero_result_count", "item_count", "average_delay_seconds",
                "content_completeness", "cluster_join_rate", "selection_rate",
            )),
        )
        return int(cursor.lastrowid)

    def latest_health_snapshot(self, source_key: str) -> Dict | None:
        row = self.execute(
            """
            SELECT * FROM source_health_snapshots
            WHERE source_key = ? ORDER BY window_end DESC, id DESC LIMIT 1
            """,
            (source_key,),
        ).fetchone()
        return dict(row) if row else None

    def list_health(self, source_key: str | None, limit: int) -> list[Dict]:
        where = "WHERE source_key = ?" if source_key else ""
        params = (source_key, limit) if source_key else (limit,)
        rows = self.execute(
            f"SELECT * FROM source_health_snapshots {where} ORDER BY window_end DESC, id DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def open_incident(self, source_key: str, incident_type: str, summary: str, details: Dict) -> bool:
        existing = self.execute(
            "SELECT id FROM source_incidents WHERE source_key = ? AND incident_type = ? AND status != 'resolved' LIMIT 1",
            (source_key, incident_type),
        ).fetchone()
        if existing:
            self.execute(
                "UPDATE source_incidents SET summary = ?, details_json = ? WHERE id = ?",
                (summary, json.dumps(details, ensure_ascii=False), existing["id"]),
            )
            return False
        self.execute(
            "INSERT INTO source_incidents(source_key, incident_type, summary, details_json) VALUES (?, ?, ?, ?)",
            (source_key, incident_type, summary, json.dumps(details, ensure_ascii=False)),
        )
        return True

    def list_incidents(self, status: str | None, limit: int) -> list[Dict]:
        where = "WHERE i.status = ?" if status else ""
        params = (status, limit) if status else (limit,)
        rows = self.execute(
            f"""
            SELECT i.*, s.display_name FROM source_incidents i
            JOIN source_catalog s ON s.source_key = i.source_key
            {where} ORDER BY CASE i.status WHEN 'open' THEN 0 WHEN 'acknowledged' THEN 1 ELSE 2 END,
                     i.detected_at DESC LIMIT ?
            """,
            params,
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["details"] = json.loads(item.pop("details_json") or "{}")
            result.append(item)
        return result

    def update_incident(self, incident_id: int, status: str) -> bool:
        cursor = self.execute(
            """
            UPDATE source_incidents SET status = ?,
                resolved_at = CASE WHEN ? = 'resolved' THEN CURRENT_TIMESTAMP ELSE NULL END
            WHERE id = ?
            """,
            (status, status, incident_id),
        )
        return cursor.rowcount > 0
