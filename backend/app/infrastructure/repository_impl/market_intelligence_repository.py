from __future__ import annotations

import json
from typing import Dict

from .base_repository import BaseRepository


class MarketIntelligenceRepository(BaseRepository):
    def list_instruments(self, enabled_only: bool = False) -> list[Dict]:
        where = "WHERE m.enabled = 1" if enabled_only else ""
        rows = self.execute(
            f"""
            SELECT m.*, e.name AS entity_name, e.slug AS entity_slug, e.entity_type
            FROM market_instruments m JOIN entities e ON e.id = m.entity_id
            {where} ORDER BY m.enabled DESC, e.name, m.provider
            """
        ).fetchall()
        return [self._hydrate(row) for row in rows]

    def get_instrument(self, instrument_id: int) -> Dict | None:
        row = self.execute(
            """
            SELECT m.*, e.name AS entity_name, e.slug AS entity_slug, e.entity_type
            FROM market_instruments m JOIN entities e ON e.id = m.entity_id WHERE m.id = ?
            """,
            (instrument_id,),
        ).fetchone()
        return self._hydrate(row) if row else None

    @staticmethod
    def _hydrate(row) -> Dict:
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        return item

    def save_instrument(self, values: Dict, instrument_id: int | None = None) -> int:
        payload = (
            values["entity_id"], values["provider"], values["symbol"].upper(),
            values.get("quote_symbol", "USDT").upper(), bool(values.get("enabled", True)),
            json.dumps(values.get("metadata") or {}, ensure_ascii=False),
        )
        if instrument_id is None:
            cursor = self.execute(
                """
                INSERT INTO market_instruments(entity_id, provider, symbol, quote_symbol, enabled, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                payload,
            )
            return int(cursor.lastrowid)
        cursor = self.execute(
            """
            UPDATE market_instruments SET entity_id = ?, provider = ?, symbol = ?, quote_symbol = ?,
                enabled = ?, metadata_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?
            """,
            (*payload, instrument_id),
        )
        return instrument_id if cursor.rowcount > 0 else 0

    def event_instruments(self, event_id: int) -> list[Dict]:
        rows = self.execute(
            """
            SELECT DISTINCT m.*, e.name AS entity_name, e.slug AS entity_slug, e.entity_type
            FROM event_entities ee JOIN market_instruments m ON m.entity_id = ee.entity_id AND m.enabled = 1
            JOIN entities e ON e.id = m.entity_id WHERE ee.event_id = ? ORDER BY m.id
            """,
            (event_id,),
        ).fetchall()
        return [self._hydrate(row) for row in rows]

    def list_tracked_event_ids(self, limit: int = 50) -> list[int]:
        rows = self.execute(
            """
            SELECT DISTINCT ee.event_id
            FROM event_entities ee JOIN market_instruments m ON m.entity_id = ee.entity_id AND m.enabled = 1
            JOIN content_events e ON e.id = ee.event_id
            WHERE e.published_at >= datetime('now', '-8 days')
            ORDER BY e.published_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [int(row["event_id"]) for row in rows]

    def save_snapshot(self, values: Dict) -> int:
        self.execute(
            """
            INSERT INTO market_snapshots(event_id, instrument_id, observation_window, observed_at,
                price, volume, funding_rate, open_interest, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id, instrument_id, observation_window) DO UPDATE SET
                observed_at = excluded.observed_at, price = excluded.price, volume = excluded.volume,
                funding_rate = excluded.funding_rate, open_interest = excluded.open_interest,
                metadata_json = excluded.metadata_json
            """,
            (
                values["event_id"], values["instrument_id"], values["observation_window"],
                values["observed_at"], values.get("price"), values.get("volume"),
                values.get("funding_rate"), values.get("open_interest"),
                json.dumps(values.get("metadata") or {}, ensure_ascii=False),
            ),
        )
        row = self.execute(
            "SELECT id FROM market_snapshots WHERE event_id = ? AND instrument_id = ? AND observation_window = ?",
            (values["event_id"], values["instrument_id"], values["observation_window"]),
        ).fetchone()
        self.execute(
            "UPDATE content_events SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (values["event_id"],),
        )
        return int(row["id"])

    def list_event_market(self, event_id: int) -> list[Dict]:
        instruments = self.event_instruments(event_id)
        result = []
        for instrument in instruments:
            snapshots = self.execute(
                "SELECT * FROM market_snapshots WHERE event_id = ? AND instrument_id = ? ORDER BY observed_at",
                (event_id, instrument["id"]),
            ).fetchall()
            assessment = self.execute(
                "SELECT * FROM market_impact_assessments WHERE event_id = ? AND instrument_id = ?",
                (event_id, instrument["id"]),
            ).fetchone()
            hydrated_snapshots = []
            for row in snapshots:
                item = dict(row)
                item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
                hydrated_snapshots.append(item)
            hydrated_assessment = dict(assessment) if assessment else None
            if hydrated_assessment:
                hydrated_assessment["metadata"] = json.loads(hydrated_assessment.pop("metadata_json") or "{}")
            result.append({"instrument": instrument, "snapshots": hydrated_snapshots, "assessment": hydrated_assessment})
        return result

    def save_expectation(self, event_id: int, instrument_id: int, values: Dict) -> None:
        self.execute(
            """
            INSERT INTO market_impact_assessments(event_id, instrument_id, expected_direction,
                expected_impact, confidence, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id, instrument_id) DO UPDATE SET
                expected_direction = excluded.expected_direction,
                expected_impact = excluded.expected_impact,
                confidence = excluded.confidence,
                metadata_json = excluded.metadata_json
            """,
            (
                event_id, instrument_id, values.get("expected_direction"), values.get("expected_impact"),
                values.get("confidence"), json.dumps(values.get("metadata") or {}, ensure_ascii=False),
            ),
        )
        self.execute("UPDATE content_events SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (event_id,))

    def recalculate(self, event_id: int, instrument_id: int) -> Dict:
        rows = self.execute(
            "SELECT observation_window, price FROM market_snapshots WHERE event_id = ? AND instrument_id = ? AND price IS NOT NULL",
            (event_id, instrument_id),
        ).fetchall()
        prices = {row["observation_window"]: float(row["price"]) for row in rows}
        base = prices.get("t0")
        def change(window: str):
            return ((prices[window] / base) - 1) if base and window in prices else None
        return_15m, return_1h, return_24h = change("t+15m"), change("t+1h"), change("t+24h")
        realized_value = return_24h if return_24h is not None else return_1h if return_1h is not None else return_15m
        realized_direction = None
        if realized_value is not None:
            realized_direction = "neutral" if abs(realized_value) < 0.002 else "positive" if realized_value > 0 else "negative"
        instrument = self.get_instrument(instrument_id)
        abnormal_return_24h = None
        benchmark_id = (instrument or {}).get("metadata", {}).get("benchmark_instrument_id")
        if return_24h is not None and benchmark_id:
            benchmark_rows = self.execute(
                "SELECT observation_window, price FROM market_snapshots WHERE event_id = ? AND instrument_id = ? AND observation_window IN ('t0','t+24h') AND price IS NOT NULL",
                (event_id, int(benchmark_id)),
            ).fetchall()
            benchmark_prices = {row["observation_window"]: float(row["price"]) for row in benchmark_rows}
            if benchmark_prices.get("t0") and benchmark_prices.get("t+24h"):
                abnormal_return_24h = return_24h - (benchmark_prices["t+24h"] / benchmark_prices["t0"] - 1)
        self.execute(
            """
            INSERT INTO market_impact_assessments(event_id, instrument_id, realized_direction,
                return_15m, return_1h, return_24h, abnormal_return_24h, evaluated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(event_id, instrument_id) DO UPDATE SET
                realized_direction = excluded.realized_direction, return_15m = excluded.return_15m,
                return_1h = excluded.return_1h, return_24h = excluded.return_24h,
                abnormal_return_24h = excluded.abnormal_return_24h,
                evaluated_at = CURRENT_TIMESTAMP
            """,
            (event_id, instrument_id, realized_direction, return_15m, return_1h, return_24h, abnormal_return_24h),
        )
        return next(item for item in self.list_event_market(event_id) if int(item["instrument"]["id"]) == instrument_id)
