from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict

from ..core.exceptions import ValidationError


class AnalystDataService:
    def __init__(self, access, event_repository, entity_repository, market_repository, tag_repository):
        self._access = access
        self._event_repository = event_repository
        self._entity_repository = entity_repository
        self._market_repository = market_repository
        self._tag_repository = tag_repository

    def _authenticate(self, api_key: str) -> None:
        self._access.authenticate(api_key)

    def _event(self, event_id: int) -> Dict | None:
        detail = self._event_repository().get_detail(event_id)
        if detail:
            detail["markets"] = self._market_repository().list_event_market(event_id)
        return detail

    @staticmethod
    def _cursor(value: str | None) -> str | None:
        if value is None:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValidationError("增量游标必须是 ISO-8601 时间") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()

    def list_events(self, api_key: str, page: int, limit: int, content_kind: str | None, updated_after: str | None) -> Dict:
        self._authenticate(api_key)
        result = self._event_repository().list_selected_event_ids(
            page, limit, content_kind, self._cursor(updated_after)
        )
        result["items"] = [self._event(event_id) for event_id in result.pop("ids")]
        return result

    def get_event(self, api_key: str, event_id: int) -> Dict | None:
        self._authenticate(api_key)
        return self._event(event_id)

    def list_entities(self, api_key: str, entity_type: str | None, query: str | None) -> list[Dict]:
        self._authenticate(api_key)
        return self._entity_repository().list_entities(entity_type, query)

    def list_narratives(self, api_key: str) -> list[Dict]:
        self._authenticate(api_key)
        return self._entity_repository().list_narratives(enabled_only=True)

    def list_tags(self, api_key: str) -> list[Dict]:
        self._authenticate(api_key)
        return self._tag_repository().list_tags()

    def delta(self, api_key: str, since: str, limit: int) -> Dict:
        self._authenticate(api_key)
        next_cursor = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        result = self._event_repository().delta(self._cursor(since), limit)
        result["events"] = [self._event(event_id) for event_id in result.pop("event_ids")]
        result["next_cursor"] = next_cursor
        return result
