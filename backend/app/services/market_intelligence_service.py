from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict

from ..core.exceptions import NotFoundError, ValidationError


WINDOWS = {
    "t-1h": timedelta(hours=-1),
    "t0": timedelta(0),
    "t+15m": timedelta(minutes=15),
    "t+1h": timedelta(hours=1),
    "t+24h": timedelta(hours=24),
    "t+7d": timedelta(days=7),
}


class MarketIntelligenceService:
    def __init__(self, repository, entity_repository, event_repository, gateway, transaction):
        self._repository = repository
        self._entity_repository = entity_repository
        self._event_repository = event_repository
        self._gateway = gateway
        self._transaction = transaction

    def list_instruments(self) -> list[Dict]:
        return self._repository().list_instruments()

    def save_instrument(self, values: Dict, instrument_id: int | None = None) -> Dict:
        if not self._entity_repository().get_entity(values["entity_id"]):
            raise NotFoundError("实体不存在")
        provider = values["provider"].strip().lower()
        if provider not in {"binance", "manual"}:
            raise ValidationError("行情提供方只支持 binance 或 manual")
        normalized = {**values, "provider": provider, "symbol": values["symbol"].strip().upper()}
        saved_id = self._repository().save_instrument(normalized, instrument_id)
        if not saved_id:
            raise NotFoundError("行情品种不存在")
        return self._repository().get_instrument(saved_id)

    def get_event_market(self, event_id: int) -> Dict:
        detail = self._event_repository().get_detail(event_id)
        if not detail:
            raise NotFoundError("事件不存在")
        return {"event": detail["event"], "markets": self._repository().list_event_market(event_id)}

    async def refresh_event(self, event_id: int) -> Dict:
        detail = self._event_repository().get_detail(event_id)
        if not detail:
            raise NotFoundError("事件不存在")
        instruments = self._repository().event_instruments(event_id)
        if not instruments:
            raise ValidationError("事件关联的实体还没有配置行情品种")
        event_time = datetime.fromisoformat(str(detail["event"]["published_at"]).replace("Z", "+00:00"))
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        saved = 0
        errors = []
        for instrument in instruments:
            if instrument["provider"] == "manual":
                continue
            existing = {
                item["observation_window"]
                for market in self._repository().list_event_market(event_id)
                if int(market["instrument"]["id"]) == int(instrument["id"])
                for item in market["snapshots"]
            }
            for window, delta in WINDOWS.items():
                target = event_time + delta
                if target > now or window in existing:
                    continue
                try:
                    observation = await self._gateway.observe(instrument, target)
                    self._repository().save_snapshot({
                        **observation,
                        "event_id": event_id,
                        "instrument_id": instrument["id"],
                        "observation_window": window,
                    })
                    saved += 1
                except Exception as exc:
                    errors.append({"instrument_id": instrument["id"], "window": window, "error": str(exc)})
            self._repository().recalculate(event_id, instrument["id"])
        return {**self.get_event_market(event_id), "saved": saved, "errors": errors}

    async def refresh_due_events(self, limit: int = 50) -> Dict:
        event_ids = self._repository().list_tracked_event_ids(limit)
        results = []
        for event_id in event_ids:
            result = await self.refresh_event(event_id)
            results.append({"event_id": event_id, "saved": result["saved"], "errors": result["errors"]})
        return {"events": len(event_ids), "results": results}

    def save_snapshot(self, event_id: int, instrument_id: int, values: Dict) -> Dict:
        if not self._event_repository().get_detail(event_id):
            raise NotFoundError("事件不存在")
        if not self._repository().get_instrument(instrument_id):
            raise NotFoundError("行情品种不存在")
        self._repository().save_snapshot({**values, "event_id": event_id, "instrument_id": instrument_id})
        return self._repository().recalculate(event_id, instrument_id)

    def save_expectation(self, event_id: int, instrument_id: int, values: Dict) -> Dict:
        if not self._event_repository().get_detail(event_id):
            raise NotFoundError("事件不存在")
        if not self._repository().get_instrument(instrument_id):
            raise NotFoundError("行情品种不存在")
        self._repository().save_expectation(event_id, instrument_id, values)
        return self._repository().recalculate(event_id, instrument_id)
