from __future__ import annotations

from typing import Dict, Iterable

from shared.content_contract import ARCHIVE_STATUS_BLOCKED, ARCHIVE_STATUS_REVIEWED
from ..core.time import format_utc_time, utc_cutoff


class ContentTransitionService:
    WRITE_BATCH_SIZE = 100

    def __init__(self, transaction):
        self._transaction = transaction

    def persist_event_clusters(self, clusters: Iterable, clusterer, content_kind: str, time_window_hours: int) -> Dict:
        clusters = list(clusters)
        created_events = 0
        attached_events = 0
        multi_source_events = 0
        source_count = 0
        with self._transaction() as tx_repos:
            existing_events = tx_repos.event_queries.list_recent_candidates(
                content_kind, time_window_hours
            )
        prepared_events = clusterer.prepare_existing_events(existing_events)
        for batch_start in range(0, len(clusters), self.WRITE_BATCH_SIZE):
            batch = clusters[batch_start : batch_start + self.WRITE_BATCH_SIZE]
            with self._transaction() as tx_repos:
                for cluster in batch:
                    existing, match_score = clusterer.best_existing_event(cluster.primary, prepared_events)
                    if existing:
                        event_id = existing["id"]
                        canonical_news_id = existing["canonical_news_id"]
                        attached_events += 1
                    else:
                        event_id = tx_repos.events.create_event(cluster.primary, cluster.event_key)
                        canonical_news_id = cluster.primary["id"]
                        tx_repos.archive.create_entry(cluster.primary, event_id)
                        created_events += 1
                        clusterer.add_existing_event(
                            prepared_events,
                            {
                                "id": event_id,
                                "canonical_news_id": canonical_news_id,
                                "title": cluster.primary["title"],
                                "source_count": len(cluster.members),
                            },
                        )

                    tx_repos.events.add_sources(
                        event_id,
                        cluster.members,
                        canonical_news_id,
                        event_match_score=match_score if existing else None,
                    )
                    for member in cluster.members:
                        similarity = min(member.similarity, match_score) if existing else member.similarity
                        tx_repos.news.mark_clustered(
                            member.item["id"],
                            event_id,
                            similarity,
                            member.item["id"] == canonical_news_id,
                        )
                    source_count += len(cluster.members)
                    if len(cluster.members) > 1 or (
                        existing and existing.get("source_count", 1) + len(cluster.members) > 1
                    ):
                        multi_source_events += 1

        return {
            "created_events": created_events,
            "attached_events": attached_events,
            "multi_source_events": multi_source_events,
            "sources_clustered": source_count,
        }

    def apply_blocklist(self, time_range_hours: int, content_kind: str) -> Dict:
        start_time = "1970-01-01 00:00:00" if time_range_hours <= 0 else utc_cutoff(time_range_hours)
        blocked_at = format_utc_time()

        with self._transaction() as tx_repos:
            keywords = tx_repos.blacklist.get_blacklist_keywords(content_kind)
            profiles = tx_repos.editorial_profiles.list_profiles(content_kind, enabled_only=True)
            if not profiles:
                raise RuntimeError(f"没有为 {content_kind} 配置可用的内容档案")

        scanned_count = 0
        blocked_count = 0
        review_count = 0
        while True:
            with self._transaction() as tx_repos:
                archive_rows = tx_repos.archive_query.list_filter_candidates(
                    start_time, content_kind, limit=self.WRITE_BATCH_SIZE
                )
                if not archive_rows:
                    break
                scanned_count += len(archive_rows)
                for row in archive_rows:
                    filter_reason = tx_repos.blacklist.match_keyword((row["title"] or "").lower(), keywords)
                    if filter_reason:
                        tx_repos.archive.update_status(
                            row["id"],
                            ARCHIVE_STATUS_BLOCKED,
                            block_reason=filter_reason,
                            archived_at=blocked_at,
                        )
                        blocked_count += 1
                        continue

                    for profile in profiles:
                        if tx_repos.review.create_pending_entry(row, blocked_at, profile["slug"]):
                            review_count += 1
                    tx_repos.archive.update_status(
                        row["id"],
                        ARCHIVE_STATUS_REVIEWED,
                        block_reason=None,
                    )

        retroactive_blocked_count = 0
        blocked_urls = set()
        last_review_id = 0
        while True:
            with self._transaction() as tx_repos:
                review_rows = tx_repos.review_admin.list_recent_entries(
                    start_time,
                    content_kind,
                    after_id=last_review_id,
                    limit=self.WRITE_BATCH_SIZE,
                )
                if not review_rows:
                    break
                last_review_id = review_rows[-1]["id"]
                for row in review_rows:
                    if row["source_url"] in blocked_urls:
                        continue
                    filter_reason = tx_repos.blacklist.match_keyword((row["title"] or "").lower(), keywords)
                    if not filter_reason:
                        continue
                    tx_repos.review.delete_by_source_url(row["source_url"])
                    tx_repos.archive.update_status_by_source_url(
                        row["source_url"],
                        ARCHIVE_STATUS_BLOCKED,
                        block_reason=filter_reason,
                        archived_at=blocked_at,
                    )
                    blocked_urls.add(row["source_url"])
                    retroactive_blocked_count += 1

        return {
            "scanned": scanned_count,
            "blocked": blocked_count + retroactive_blocked_count,
            "review": review_count,
            "retroactive": retroactive_blocked_count,
        }
