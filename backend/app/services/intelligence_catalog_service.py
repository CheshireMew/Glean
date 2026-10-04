from __future__ import annotations

import re
from typing import Dict

from ..core.exceptions import NotFoundError, ValidationError


class IntelligenceCatalogService:
    def __init__(self, repository, event_repository, transaction):
        self._repository = repository
        self._event_repository = event_repository
        self._transaction = transaction

    @staticmethod
    def _slug(value: str) -> str:
        slug = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            raise ValidationError("标识只能包含小写字母、数字和连字符")
        return slug

    def list_entities(self, entity_type: str | None, query: str | None) -> list[Dict]:
        return self._repository().list_entities(entity_type, query)

    def get_entity(self, entity_id: int) -> Dict:
        entity = self._repository().get_entity(entity_id)
        if not entity:
            raise NotFoundError("实体不存在")
        return entity

    def get_public_entity(self, slug: str, limit: int, offset: int) -> Dict:
        entity = self._repository().get_entity_by_slug(slug)
        if not entity:
            raise NotFoundError("实体不存在")
        events = self._repository().list_entity_events(entity["id"], True, limit, offset)
        if not events["total"]:
            raise NotFoundError("实体不存在")
        fields = ("id", "entity_type", "slug", "name", "symbol", "description")
        return {**{key: entity.get(key) for key in fields}, "events": events}

    def save_entity(self, values: Dict, entity_id: int | None = None) -> Dict:
        normalized = {
            **values,
            "slug": self._slug(values["slug"]),
            "name": values["name"].strip(),
            "symbol": (values.get("symbol") or "").strip().upper() or None,
            "aliases": list(dict.fromkeys(alias.strip() for alias in values.get("aliases", []) if alias.strip())),
        }
        saved_id = self._repository().save_entity(normalized, entity_id)
        if not saved_id:
            raise NotFoundError("实体不存在")
        return self.get_entity(saved_id)

    def attach_entity(self, event_id: int, values: Dict) -> Dict:
        if not self._event_repository().get_detail(event_id):
            raise NotFoundError("事件不存在")
        if not self._repository().get_entity(values["entity_id"]):
            raise NotFoundError("实体不存在")
        self._repository().attach_entity(event_id, **values)
        return self._event_repository().get_detail(event_id)

    def list_narratives(self, enabled_only: bool = False) -> list[Dict]:
        return self._repository().list_narratives(enabled_only)

    def get_public_narrative(self, slug: str, limit: int, offset: int) -> Dict:
        narrative = self._repository().get_narrative_by_slug(slug)
        if not narrative or not narrative.get("enabled"):
            raise NotFoundError("叙事不存在")
        return {
            **narrative,
            "events": self._repository().list_narrative_events(narrative["id"], True, limit, offset),
            "trend": self._repository().list_narrative_trend(narrative["id"]),
        }

    def save_narrative(self, values: Dict, narrative_id: int | None = None) -> Dict:
        normalized = {
            **values,
            "slug": self._slug(values["slug"]),
            "name": values["name"].strip(),
            "keywords": list(
                dict.fromkeys(
                    keyword.strip() for keyword in values.get("keywords", []) if keyword.strip()
                )
            ),
        }
        saved_id = self._repository().save_narrative(normalized, narrative_id)
        if not saved_id:
            raise NotFoundError("叙事不存在")
        return self._repository().get_narrative(saved_id)

    def attach_narrative(self, event_id: int, values: Dict) -> Dict:
        if not self._event_repository().get_detail(event_id):
            raise NotFoundError("事件不存在")
        if not self._repository().get_narrative(values["narrative_id"]):
            raise NotFoundError("叙事不存在")
        self._repository().attach_narrative(event_id, **values)
        return self._event_repository().get_detail(event_id)

    @staticmethod
    def _contains_term(text: str, term: str) -> bool:
        normalized_term = term.strip().casefold()
        if not normalized_term:
            return False
        if normalized_term.isascii() and normalized_term.replace("-", "").isalnum():
            return re.search(
                rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])", text
            ) is not None
        return normalized_term in text

    def classify_event(self, event_id: int) -> Dict:
        detail = self._event_repository().get_detail(event_id)
        if not detail:
            raise NotFoundError("事件不存在")
        title = (detail["event"].get("title") or "").casefold()
        body = " ".join(
            [
                detail["event"].get("content") or "",
                *(item.get("title") or "" for item in detail.get("sources") or []),
                *(item.get("content") or "" for item in detail.get("sources") or []),
                *(item.get("review_summary") or "" for item in detail.get("reviews") or []),
            ]
        ).casefold()
        entity_matches = []
        for entity in self._repository().list_entities():
            terms = [entity.get("name"), entity.get("symbol"), *(entity.get("aliases") or [])]
            title_terms = [term for term in terms if term and self._contains_term(title, term)]
            body_terms = [term for term in terms if term and self._contains_term(body, term)]
            if title_terms or body_terms:
                entity_matches.append(
                    {
                        "entity_id": int(entity["id"]),
                        "name": entity["name"],
                        "role": "subject" if title_terms else "mentioned",
                        "confidence": 0.95 if title_terms else 0.8,
                        "matched_terms": list(dict.fromkeys([*title_terms, *body_terms])),
                    }
                )
        narrative_matches = []
        for narrative in self._repository().list_narratives(enabled_only=True):
            terms = [narrative.get("name"), *(narrative.get("keywords") or [])]
            title_terms = [term for term in terms if term and self._contains_term(title, term)]
            body_terms = [term for term in terms if term and self._contains_term(body, term)]
            if title_terms or body_terms:
                narrative_matches.append(
                    {
                        "narrative_id": int(narrative["id"]),
                        "name": narrative["name"],
                        "confidence": 0.9 if title_terms else 0.75,
                        "matched_terms": list(dict.fromkeys([*title_terms, *body_terms])),
                    }
                )
        with self._transaction() as tx:
            tx.intelligence_catalog.sync_rule_classification(
                event_id, entity_matches, narrative_matches
            )
        return {
            "event_id": event_id,
            "entities": entity_matches,
            "narratives": narrative_matches,
            "detail": self._event_repository().get_detail(event_id),
        }

    def classify_recent(self, hours: int = 168, limit: int = 500) -> Dict:
        event_ids = self._repository().list_candidate_events(hours)[:limit]
        results = []
        errors = []
        for event_id in event_ids:
            try:
                result = self.classify_event(event_id)
                results.append(
                    {
                        "event_id": event_id,
                        "entity_count": len(result["entities"]),
                        "narrative_count": len(result["narratives"]),
                    }
                )
            except Exception as exc:
                errors.append({"event_id": event_id, "error": str(exc)})
        return {
            "scanned": len(event_ids),
            "classified": len(results),
            "errors": errors,
            "results": results,
        }

    def list_watchlists(self, public_only: bool = False) -> list[Dict]:
        return self._repository().list_watchlists(public_only)

    def save_watchlist(self, values: Dict, watchlist_id: int | None = None) -> Dict:
        entity_ids = set(values.get("entity_ids") or [])
        known_entities = {item["id"] for item in self._repository().list_entities()}
        if not entity_ids <= known_entities:
            raise ValidationError("关注列表包含不存在的实体")
        narrative_ids = set(values.get("narrative_ids") or [])
        known_narratives = {item["id"] for item in self._repository().list_narratives()}
        if not narrative_ids <= known_narratives:
            raise ValidationError("关注列表包含不存在的叙事")
        saved_id = self._repository().save_watchlist(values, watchlist_id)
        if not saved_id:
            raise NotFoundError("关注列表不存在")
        return self._repository().get_watchlist(saved_id)

    def list_alert_policies(self) -> list[Dict]:
        return self._repository().list_alert_policies()

    def save_alert_policy(self, values: Dict, policy_id: int | None = None) -> Dict:
        if values.get("watchlist_id") and not self._repository().get_watchlist(values["watchlist_id"]):
            raise NotFoundError("关注列表不存在")
        if not self._repository().channel_exists(values["channel_id"]):
            raise NotFoundError("投递渠道不存在")
        saved_id = self._repository().save_alert_policy(values, policy_id)
        if not saved_id:
            raise NotFoundError("提醒规则不存在")
        return self._repository().get_alert_policy(saved_id)

    @staticmethod
    def _matches(detail: Dict, policy: Dict, watchlist: Dict | None) -> bool:
        conditions = policy.get("conditions") or {}
        reviews = detail.get("reviews") or []
        review = next((item for item in reviews if not policy.get("profile_slug") or item.get("profile_slug") == policy["profile_slug"]), None)
        if not review:
            return False
        if int(review.get("review_score") or 0) < int(conditions.get("min_score") or 0):
            return False
        if conditions.get("categories") and review.get("review_category") not in conditions["categories"]:
            return False
        if conditions.get("content_types") and detail["event"].get("content_type") not in conditions["content_types"]:
            return False
        if int(detail.get("independent_source_count") or 0) < int(conditions.get("min_independent_sources") or 0):
            return False
        if conditions.get("verified_only") and not any(source.get("verification_status") == "verified" for source in detail["sources"]):
            return False
        if conditions.get("source_sites") and not any(source.get("source_site") in conditions["source_sites"] for source in detail["sources"]):
            return False
        haystack = " ".join([detail["event"].get("title") or "", detail["event"].get("content") or "", review.get("review_summary") or ""]).casefold()
        if conditions.get("keywords") and not any(str(keyword).casefold() in haystack for keyword in conditions["keywords"]):
            return False
        entity_ids = {int(item["id"]) for item in detail.get("entities") or []}
        narrative_ids = {int(item["id"]) for item in detail.get("narratives") or []}
        required_entities = set(conditions.get("entity_ids") or []) | set((watchlist or {}).get("entity_ids") or [])
        required_narratives = set(conditions.get("narrative_ids") or []) | set((watchlist or {}).get("narrative_ids") or [])
        if required_entities and not (required_entities & entity_ids):
            return False
        if required_narratives and not (required_narratives & narrative_ids):
            return False
        return True

    def evaluate_alerts(self, policy_id: int | None, hours: int) -> Dict:
        policies = self._repository().list_alert_policies(enabled_only=True)
        if policy_id is not None:
            policies = [policy for policy in policies if int(policy["id"]) == policy_id]
            if not policies:
                raise NotFoundError("启用的提醒规则不存在")
        event_ids = self._repository().list_candidate_events(hours)
        matches = []
        for policy in policies:
            watchlist = self._repository().get_watchlist(policy["watchlist_id"]) if policy.get("watchlist_id") else None
            for event_id in event_ids:
                detail = self._event_repository().get_detail(event_id)
                if detail and self._matches(detail, policy, watchlist):
                    if self._repository().save_alert_match(policy["id"], event_id):
                        matches.append({"policy_id": policy["id"], "event_id": event_id})
            self._repository().update_policy_evaluated(policy["id"])
        return {"policies": len(policies), "events_scanned": len(event_ids), "new_matches": len(matches), "matches": matches}

    def list_alert_matches(self, status: str | None, limit: int) -> list[Dict]:
        return self._repository().list_alert_matches(status, limit)
