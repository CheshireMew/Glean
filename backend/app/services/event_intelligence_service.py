from __future__ import annotations

from typing import Dict

from ..core.exceptions import NotFoundError, ValidationError


class EventIntelligenceService:
    def __init__(self, repository, transaction):
        self._repository = repository
        self._transaction = transaction

    def get_detail(self, event_id: int, public_only: bool = False) -> Dict:
        detail = self._repository().get_detail(event_id, public_only)
        if not detail or (public_only and not detail.get("reviews")):
            raise NotFoundError("事件不存在或尚未公开")
        return detail

    def update_source_evidence(self, event_id: int, news_id: int, values: Dict) -> Dict:
        origin_news_id = values.get("origin_news_id")
        detail = self._repository().get_detail(event_id)
        if not detail:
            raise NotFoundError("事件不存在")
        source_ids = {int(item["id"]) for item in detail["sources"]}
        if news_id not in source_ids:
            raise NotFoundError("来源不属于该事件")
        if origin_news_id is not None and origin_news_id not in source_ids:
            raise ValidationError("引用源必须属于同一事件")
        if origin_news_id == news_id:
            raise ValidationError("来源不能引用自身作为原始证据")
        if not self._repository().update_source_evidence(event_id, news_id, values):
            raise NotFoundError("事件来源不存在")
        return self.get_detail(event_id)

    def add_update(self, event_id: int, values: Dict, actor: str) -> Dict:
        detail = self._repository().get_detail(event_id)
        if not detail:
            raise NotFoundError("事件不存在")
        source_news_id = values.get("source_news_id")
        if source_news_id is not None and source_news_id not in {
            int(item["id"]) for item in detail["sources"]
        }:
            raise ValidationError("事件进展引用的来源不属于该事件")
        payload = dict(values)
        payload["occurred_at"] = values["occurred_at"].isoformat()
        update_id = self._repository().add_update(event_id, payload, actor)
        return {"id": update_id, "detail": self.get_detail(event_id)}

    def update_event_update(self, update_id: int, values: Dict, actor: str) -> Dict:
        payload = dict(values)
        if payload.get("occurred_at") is not None:
            payload["occurred_at"] = payload["occurred_at"].isoformat()
        if not self._repository().update_event_update(update_id, payload, actor):
            raise NotFoundError("事件进展不存在")
        return {"id": update_id, "updated": True}

    def add_fact(self, event_id: int, values: Dict, actor: str) -> Dict:
        detail = self._repository().get_detail(event_id)
        if not detail:
            raise NotFoundError("事件不存在")
        source_news_id = values.get("source_news_id")
        if source_news_id is not None and source_news_id not in {
            int(item["id"]) for item in detail["sources"]
        }:
            raise ValidationError("关键事实引用的来源不属于该事件")
        fact_id = self._repository().add_fact(event_id, values, actor)
        return {"id": fact_id, "detail": self.get_detail(event_id)}

    def update_fact(self, fact_id: int, values: Dict, actor: str) -> Dict:
        fact = self._repository().get_fact(fact_id)
        if not fact:
            raise NotFoundError("关键事实不存在")
        source_news_id = values.get("source_news_id")
        if source_news_id is not None:
            detail = self._repository().get_detail(int(fact["event_id"]))
            if source_news_id not in {int(item["id"]) for item in detail["sources"]}:
                raise ValidationError("关键事实引用的来源不属于该事件")
        if not self._repository().update_fact(fact_id, values, actor):
            raise NotFoundError("关键事实不存在或没有变化")
        return {"id": fact_id, "updated": True}

    def add_relation(self, event_id: int, values: Dict, actor: str) -> Dict:
        if event_id == values["related_event_id"]:
            raise ValidationError("事件不能关联自身")
        if not self._repository().get_detail(event_id):
            raise NotFoundError("事件不存在")
        if not self._repository().get_detail(values["related_event_id"]):
            raise NotFoundError("关联事件不存在")
        relation_id = self._repository().add_relation(event_id, values, actor)
        return {"id": relation_id, "detail": self.get_detail(event_id)}
