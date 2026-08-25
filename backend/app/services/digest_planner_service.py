from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Dict, Iterable, List


@dataclass(frozen=True)
class DigestPolicy:
    max_items: int
    max_per_category: int
    max_per_source: int
    critical_score: int = 9


DEFAULT_POLICIES = {
    "news": DigestPolicy(max_items=12, max_per_category=4, max_per_source=4),
    "article": DigestPolicy(max_items=8, max_per_category=3, max_per_source=3),
}


class DigestPlannerService:
    """Build a finite, diverse digest from already selected events."""

    @staticmethod
    def _section(entry: Dict) -> str:
        category = (entry.get("review_category") or "其他").strip()
        return category[:20] or "其他"

    @staticmethod
    def _ranking_score(entry: Dict) -> float:
        editorial_score = float(entry.get("review_score") or 0)
        corroboration_bonus = min(max(int(entry.get("source_count") or 1) - 1, 0), 3) * 0.25
        return editorial_score + corroboration_bonus

    def plan(self, entries: Iterable[Dict], content_kind: str, policy: DigestPolicy | None = None) -> List[Dict]:
        policy = policy or DEFAULT_POLICIES.get(content_kind, DEFAULT_POLICIES["news"])
        ranked = []
        for raw in entries:
            entry = dict(raw)
            entry["digest_section"] = self._section(entry)
            entry["ranking_score"] = self._ranking_score(entry)
            ranked.append(entry)
        ranked.sort(key=lambda item: (item["ranking_score"], item.get("published_at") or ""), reverse=True)

        selected: List[Dict] = []
        category_counts: Counter[str] = Counter()
        source_counts: Counter[str] = Counter()
        for entry in ranked:
            if len(selected) >= policy.max_items:
                break
            category = entry["digest_section"]
            source = entry.get("source_site") or "未知来源"
            critical = int(entry.get("review_score") or 0) >= policy.critical_score
            if not critical and (
                category_counts[category] >= policy.max_per_category
                or source_counts[source] >= policy.max_per_source
            ):
                continue
            selected.append(entry)
            category_counts[category] += 1
            source_counts[source] += 1

        return selected
