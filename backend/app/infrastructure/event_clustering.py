from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, localcontext
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Iterable, List
import unicodedata

from ..domain.events import event_primary_score
from .event_facts import extract_facts, facts_conflict, merge_facts

try:
    import jieba
except ImportError:  # pragma: no cover - deterministic fallback is always available
    jieba = None


_STOP_WORDS = {
    "一个", "一种", "以及", "已经", "可能", "表示", "目前", "进行", "通过", "正式",
    "the", "and", "for", "from", "into", "with", "will", "has", "have",
}


@dataclass(frozen=True)
class EventMember:
    item: Dict
    similarity: float


@dataclass(frozen=True)
class EventCluster:
    primary: Dict
    members: List[EventMember]
    event_key: str


@dataclass
class PreparedEventCandidates:
    items: List[Dict]
    features: List[Dict[str, object]]
    key_index: Dict[str, set[int]]
    normalized_index: Dict[str, int]


class EventClusterer:
    """Group source reports that describe the same real-world event."""

    MAX_CLUSTER_CANDIDATES = 64
    MAX_EXISTING_CANDIDATES = 64

    def __init__(self, similarity_threshold: float = 0.5):
        self.similarity_threshold = min(max(float(similarity_threshold), 0.0), 1.0)
        synonym_path = Path(__file__).with_name("event_clustering_data") / "synonyms.json"
        self.synonyms = json.loads(synonym_path.read_text(encoding="utf-8")) if synonym_path.exists() else {}
        # One longest-first pass, with Latin word boundaries, prevents cascades and
        # partial replacements such as ETH inside Ethereum or POS inside PostgreSQL.
        self.synonyms = {source: target for source, target in self.synonyms.items() if target and len(source) > 1}
        patterns = [rf'(?<![a-z0-9_]){re.escape(source)}(?![a-z0-9_])' if source.isascii()
                    else re.escape(source) for source in sorted(self.synonyms, key=len, reverse=True)]
        self._synonym_pattern = re.compile('|'.join(patterns), re.IGNORECASE) if patterns else None
        self._synonym_targets = {source.lower(): target for source, target in self.synonyms.items()}
        semantic_terms = {'top', 'vs', 'ceo', 'cfo', 'cto', 'pow', 'pos', 'defi', 'nft', 'dao', 'web3', 'gamefi', 'socialfi'}
        entity_targets = {target for source, target in self.synonyms.items()
                          if source.isascii() and source.lower() not in semantic_terms}
        entity_patterns = [rf'(?<![a-z0-9_]){re.escape(target.lower())}(?![a-z0-9_])' if target.isascii()
                           else re.escape(target.lower())
                           for target in sorted(entity_targets, key=len, reverse=True)]
        self._entity_pattern = re.compile('|'.join(entity_patterns) or r'(?!)')

    def normalize(self, text: str) -> str:
        value = unicodedata.normalize('NFKC', text or '').replace('−', '-')
        if self._synonym_pattern:
            value = self._synonym_pattern.sub(lambda match: self._synonym_targets[match.group().lower()], value)
        value = re.sub(r'(?<=\d),(?=\d{3}(?:\D|$))', '', value)
        value = re.sub(r'([$¥])\s*(-?\d+(?:\.\d+)?)(\s*(?:万亿|亿|万))?',
                       lambda match: match.group(2) + (match.group(3) or '')
                       + ('美元' if match.group(1) == '$' else '元'), value)
        scales = {'万': Decimal(10_000), '亿': Decimal(100_000_000), '万亿': Decimal(1_000_000_000_000)}
        def expand_unit(match):
            with localcontext() as context:
                context.prec = max(28, len(match.group(1)) + 16)
                return format(Decimal(match.group(1)) * scales[match.group(2)], 'f')
        value = re.sub(r'(\d+(?:\.\d+)?)\s*(万亿|亿|万)', expand_unit, value)
        value = re.sub(r'\d+\.\d+', lambda match: format(Decimal(match.group()), 'f').rstrip('0').rstrip('.'), value)
        value = re.sub(r'(?<!\d)\.|\.(?!\d)', ' ', value)
        value = re.sub(r'[^\w\u4e00-\u9fff.%\-]+', ' ', value.lower())
        value = re.sub(r'\s+', ' ', value).strip()
        return re.sub(r'(?<=[\u4e00-\u9fff])\s+|\s+(?=[\u4e00-\u9fff])', '', value)

    def extract_features(self, text: str) -> Dict[str, object]:
        normalized = self.normalize(text)
        if jieba:
            raw_tokens = list(jieba.cut_for_search(normalized))
        else:
            raw_tokens = re.findall(r"[a-z]+|\d+(?:\.\d+)?", normalized)
            for span in re.findall(r"[\u4e00-\u9fff]+", normalized):
                raw_tokens.extend(span[index:index + size] for size in (2, 3) for index in range(max(len(span) - size + 1, 0)))
        tokens = {token.lower().strip() for token in raw_tokens if len(token.strip()) >= 2 and token.lower() not in _STOP_WORDS}
        numbers = set(re.findall(r"\d+(?:\.\d+)?", normalized))
        entities = {
            token for token in tokens
            if not re.fullmatch(r'\d+(?:\.\d+)?', token)
            and (re.search(r"[a-z]", token) or token in set(self.synonyms.values()) or len(token) >= 4)
        }
        named_entities = {match.group() for match in self._entity_pattern.finditer(normalized)}
        facts = extract_facts(normalized, named_entities)
        entities.update(facts['subjects'] | facts['objects'] | named_entities)
        return {"normalized": normalized, "tokens": tokens, "numbers": numbers, "entities": entities,
                "facts": facts}

    @staticmethod
    def _jaccard(left: set, right: set) -> float:
        if not left and not right:
            return 0.0
        return len(left & right) / len(left | right)

    def calculate_similarity(self, left: Dict[str, object], right: Dict[str, object]) -> float:
        if not left['normalized'] or not right['normalized'] or facts_conflict(left['facts'], right['facts']):
            return 0.0
        if left['normalized'] == right['normalized']:
            return 1.0
        sequence = SequenceMatcher(None, str(left["normalized"]), str(right["normalized"])).ratio()
        token_score = self._jaccard(set(left["tokens"]), set(right["tokens"]))
        entity_score = self._jaccard(set(left["entities"]), set(right["entities"]))
        left_numbers = set(left["numbers"])
        right_numbers = set(right["numbers"])
        if left_numbers and right_numbers:
            number_score = self._jaccard(left_numbers, right_numbers)
        elif not left_numbers and not right_numbers:
            number_score = 0.5
        else:
            number_score = 0.0
        score = sequence * 0.25 + token_score * 0.35 + entity_score * 0.25 + number_score * 0.15
        return round(score, 6)

    def similarity(self, left_text: str, right_text: str) -> float:
        return self.calculate_similarity(self.extract_features(left_text), self.extract_features(right_text))

    def is_same_event(self, left_text: str, right_text: str) -> bool:
        left, right = self.extract_features(left_text), self.extract_features(right_text)
        return bool(left['normalized'] and right['normalized']
                    and not facts_conflict(left['facts'], right['facts'])
                    and self.calculate_similarity(left, right) >= self.similarity_threshold)

    def _event_features(self, item: Dict) -> Dict:
        feature = self.extract_features(item.get('title') or '')
        for title in item.get('source_titles') or []:
            feature['facts'] = merge_facts(feature['facts'], self.extract_features(title)['facts'])
        return feature

    def _event_key(self, primary: Dict) -> str:
        features = self.extract_features(primary.get("title") or "")
        meaningful = sorted(set(features["entities"]) or set(features["tokens"]))[:8]
        return "|".join(meaningful) or str(primary.get("id") or "")

    def cluster(self, items: Iterable[Dict]) -> List[EventCluster]:
        rows = list(items)
        if not rows:
            return []
        features = [self.extract_features(row.get("title") or "") for row in rows]
        clusters: List[List[int]] = []
        cluster_anchors: List[List[int]] = []
        cluster_primary: List[int] = []
        cluster_keys: List[set[str]] = []
        cluster_facts: List[Dict] = []
        key_index: Dict[str, set[int]] = {}

        for index, feature in enumerate(features):
            keys = set(feature["tokens"]) | set(feature["entities"]) | set(feature["numbers"])
            if self.similarity_threshold < 0.4:
                ranked_candidates = list(range(len(clusters)))[: self.MAX_CLUSTER_CANDIDATES]
            else:
                candidates = {cluster_index for key in keys for cluster_index in key_index.get(str(key), set())}
                ranked_candidates = sorted(
                    candidates,
                    key=lambda cluster_index: (
                        -len(keys & cluster_keys[cluster_index]),
                        cluster_index,
                    ),
                )[: self.MAX_CLUSTER_CANDIDATES]

            best_cluster = None
            best_average = -1.0
            for cluster_index in ranked_candidates:
                if (not feature['normalized'] or
                        facts_conflict(feature['facts'], cluster_facts[cluster_index])):
                    continue
                scores = [
                    self.calculate_similarity(features[index], features[anchor_index])
                    for anchor_index in cluster_anchors[cluster_index]
                ]
                if scores and min(scores) >= self.similarity_threshold:
                    average = sum(scores) / len(scores)
                    if average > best_average:
                        best_cluster, best_average = cluster_index, average

            if best_cluster is None:
                best_cluster = len(clusters)
                clusters.append([])
                cluster_anchors.append([index])
                cluster_primary.append(index)
                cluster_keys.append(set())
                cluster_facts.append(feature['facts'])
            clusters[best_cluster].append(index)
            cluster_facts[best_cluster] = merge_facts(cluster_facts[best_cluster], feature['facts'])
            if event_primary_score(rows[index]) > event_primary_score(rows[cluster_primary[best_cluster]]):
                cluster_primary[best_cluster] = index
                anchors = cluster_anchors[best_cluster]
                if index not in anchors:
                    cluster_anchors[best_cluster] = [anchors[0], index]
            cluster_keys[best_cluster].update(str(key) for key in keys)
            for key in keys:
                key_index.setdefault(str(key), set()).add(best_cluster)

        result: List[EventCluster] = []
        for cluster_index, indices in enumerate(clusters):
            primary_index = cluster_primary[cluster_index]
            primary = rows[primary_index]
            members = []
            for index in indices:
                if index == primary_index:
                    similarity = 1.0
                else:
                    similarity = self.calculate_similarity(features[primary_index], features[index])
                members.append(EventMember(item=rows[index], similarity=similarity))
            result.append(EventCluster(primary=primary, members=members, event_key=self._event_key(primary)))
        return result

    @staticmethod
    def _feature_keys(feature: Dict[str, object]) -> set[str]:
        return {
            str(key)
            for key in set(feature["tokens"]) | set(feature["entities"]) | set(feature["numbers"])
        }

    def prepare_existing_events(self, candidates: Iterable[Dict]) -> PreparedEventCandidates:
        items = list(candidates)
        features = [self._event_features(item) for item in items]
        key_index: Dict[str, set[int]] = {}
        normalized_index: Dict[str, int] = {}
        for index, feature in enumerate(features):
            if feature['normalized']:
                normalized_index.setdefault(str(feature["normalized"]), index)
            for key in self._feature_keys(feature):
                key_index.setdefault(key, set()).add(index)
        return PreparedEventCandidates(items, features, key_index, normalized_index)

    def add_existing_event(self, prepared: PreparedEventCandidates, candidate: Dict) -> None:
        index = len(prepared.items)
        feature = self._event_features(candidate)
        prepared.items.append(candidate)
        prepared.features.append(feature)
        if feature['normalized']:
            prepared.normalized_index.setdefault(str(feature["normalized"]), index)
        for key in self._feature_keys(feature):
            prepared.key_index.setdefault(key, set()).add(index)

    def extend_existing_event(self, prepared: PreparedEventCandidates, event_id: int, titles: Iterable[str]) -> None:
        index = next(index for index, item in enumerate(prepared.items) if item['id'] == event_id)
        for title in titles:
            prepared.features[index]['facts'] = merge_facts(
                prepared.features[index]['facts'], self.extract_features(title)['facts'])

    def best_existing_event(
        self,
        primary: Dict,
        candidates: Iterable[Dict] | PreparedEventCandidates,
    ) -> tuple[Dict | None, float]:
        prepared = (
            candidates
            if isinstance(candidates, PreparedEventCandidates)
            else self.prepare_existing_events(candidates)
        )
        primary_features = self._event_features(primary)
        if not primary_features['normalized']:
            return None, 0.0
        exact_index = prepared.normalized_index.get(str(primary_features["normalized"]))
        if exact_index is not None and not facts_conflict(primary_features['facts'], prepared.features[exact_index]['facts']):
            return prepared.items[exact_index], 1.0

        keys = self._feature_keys(primary_features)
        candidate_indexes = {
            index for key in keys for index in prepared.key_index.get(key, set())
        }
        if self.similarity_threshold < 0.4 and not candidate_indexes:
            candidate_indexes = set(range(len(prepared.items)))
        ranked_indexes = sorted(
            candidate_indexes,
            key=lambda index: (-len(keys & self._feature_keys(prepared.features[index])), index),
        )[: self.MAX_EXISTING_CANDIDATES]
        best = None
        best_score = 0.0
        for index in ranked_indexes:
            if facts_conflict(primary_features['facts'], prepared.features[index]['facts']):
                continue
            score = self.calculate_similarity(primary_features, prepared.features[index])
            if score > best_score:
                best, best_score = prepared.items[index], score
        if best_score < self.similarity_threshold:
            return None, best_score
        return best, best_score


def build_event_clusterer(similarity_threshold: float) -> EventClusterer:
    return EventClusterer(similarity_threshold=similarity_threshold)
