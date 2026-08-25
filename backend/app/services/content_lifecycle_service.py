from __future__ import annotations

from typing import Dict, Optional

from shared.content_contract import (
    ARCHIVE_STATUS_BLOCKED,
    ARCHIVE_STATUS_REVIEWED,
    CONTENT_KIND_NEWS,
)

from ..domain.events import select_event_primary
from ..core.exceptions import BusinessError


class ContentLifecycleService:
    """Owns direct user-initiated entry and queue state changes."""

    def __init__(self, review_repository, transaction):
        self._review_repository = review_repository
        self._transaction = transaction

    def delete_incoming_entry(self, entry_id: int) -> bool:
        with self._transaction() as tx_repos:
            membership = tx_repos.events.get_membership(entry_id)
            if not membership:
                return tx_repos.events.delete_news(entry_id)
            event_id = int(membership["event_id"])
            sources = tx_repos.event_queries.get_sources(event_id)
            if len(sources) <= 1:
                self._delete_event_dependents(tx_repos, event_id)
                tx_repos.events.delete_event_records(event_id)
            else:
                tx_repos.events.remove_source(event_id, entry_id)
                if membership["is_primary"]:
                    replacement = select_event_primary(
                        source for source in sources if int(source["id"]) != entry_id
                    )
                    if not replacement:
                        raise BusinessError("事件主来源替换失败")
                    tx_repos.events.replace_primary_source(event_id, replacement)
                    tx_repos.archive.replace_event_source(event_id, replacement)
                    tx_repos.review.replace_event_source(event_id, replacement)
                tx_repos.events.refresh_event(event_id)
            return tx_repos.events.delete_news(entry_id)

    def delete_archive_entry(self, entry_id: int) -> bool:
        with self._transaction() as tx_repos:
            return self._delete_event_chain(tx_repos, tx_repos.archive_query.get_event_id(entry_id))

    def delete_review_entry(self, entry_id: int) -> bool:
        with self._transaction() as tx_repos:
            return tx_repos.review.delete_entry(entry_id)

    def restore_archive_entry(self, entry_id: int) -> bool:
        with self._transaction() as tx_repos:
            event_id = tx_repos.archive_query.get_event_id(entry_id)
            if not event_id:
                return False
            self._delete_event_dependents(tx_repos, event_id)
            tx_repos.events.dissolve_event_records(event_id)
            return True

    def restore_blocked_entry(self, entry_id: int) -> bool:
        with self._transaction() as tx_repos:
            row = tx_repos.archive_query.get_entry(entry_id)
            if not row or row.get("archive_status") != ARCHIVE_STATUS_BLOCKED:
                return False
            return self._restore_blocked_row(tx_repos, row) > 0

    def restore_blocked_queue(self, content_kind: str = CONTENT_KIND_NEWS) -> Dict:
        with self._transaction() as tx_repos:
            restored = 0
            while True:
                rows = tx_repos.archive_query.list_status_batch(
                    ARCHIVE_STATUS_BLOCKED, content_kind
                )
                if not rows:
                    break
                restored += sum(self._restore_blocked_row(tx_repos, row) > 0 for row in rows)
            return {"restored_count": restored}

    @staticmethod
    def _restore_blocked_row(tx_repos, row: Dict) -> int:
        profiles = tx_repos.editorial_profiles.list_profiles(row["content_type"], enabled_only=True)
        if not profiles:
            raise BusinessError(f"没有为 {row['content_type']} 配置可用的内容档案")
        from ..core.time import format_utc_time

        queued_at = format_utc_time()
        created = sum(
            tx_repos.review.create_pending_entry(row, queued_at, profile["slug"])
            for profile in profiles
        )
        tx_repos.archive.update_status(
            row["id"],
            ARCHIVE_STATUS_REVIEWED,
            block_reason=None,
            restored_from_blocklist=True,
        )
        return created or 1

    def reset_review_item(self, entry_id: int) -> Dict:
        success = self._review_repository().requeue_entry(entry_id)
        if not success:
            raise BusinessError("恢复失败")
        return {"message": "恢复成功"}

    def reset_review_queue(self, content_kind: str = CONTENT_KIND_NEWS) -> Dict:
        return {"restored_count": self._review_repository().requeue_reviewed_entries(content_kind)}

    def clear_review_results(self, content_kind: str = CONTENT_KIND_NEWS) -> Dict:
        return {"cleared_count": self._review_repository().clear_review_results(content_kind)}

    @staticmethod
    def _delete_event_dependents(tx_repos, event_id: int) -> None:
        tx_repos.review.delete_by_event(event_id)
        tx_repos.archive.delete_by_event(event_id)

    def _delete_event_chain(self, tx_repos, event_id: Optional[int]) -> bool:
        if not event_id:
            return False
        sources = tx_repos.event_queries.get_sources(event_id)
        if not sources:
            return False
        self._delete_event_dependents(tx_repos, event_id)
        tx_repos.events.delete_event_records(event_id)
        tx_repos.events.delete_news_ids(source["id"] for source in sources)
        return True
