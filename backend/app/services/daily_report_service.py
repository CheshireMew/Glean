from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, List

from shared.content_contract import CONTENT_KIND_ARTICLE

from ..core.time import format_utc_time
from .digest_planner_service import DigestPolicy


@dataclass(frozen=True)
class PreparedDailyReport:
    date: str
    content_kind: str
    title: str
    entries: List[Dict]
    items: List[str]
    content: str
    parts: List[str]


class DailyReportService:
    def __init__(
        self,
        editorial_profile_repository,
        review_delivery_repository,
        digest_planner,
        telegram_messages,
        transaction,
    ):
        self._editorial_profile_repository = editorial_profile_repository
        self._review_delivery_repository = review_delivery_repository
        self._digest_planner = digest_planner
        self._telegram_messages = telegram_messages
        self._transaction = transaction

    def prepare(self, content_kind: str, now) -> PreparedDailyReport | None:
        start_time = format_utc_time(now - timedelta(hours=24))
        profile = self._editorial_profile_repository().get_default(content_kind)
        if not profile:
            return None
        min_score = int((profile or {}).get("min_score") or 5)
        eligible = [
            item for item in self._review_delivery_repository().get_ranked_entries(start_time, content_kind, profile["slug"])
            if (item.get("review_score") or 0) >= min_score
        ]
        policy = DigestPolicy(
            max_items=int((profile or {}).get("max_items") or (8 if content_kind == CONTENT_KIND_ARTICLE else 12)),
            max_per_category=int((profile or {}).get("max_per_category") or (3 if content_kind == CONTENT_KIND_ARTICLE else 4)),
            max_per_source=int((profile or {}).get("max_per_source") or (3 if content_kind == CONTENT_KIND_ARTICLE else 4)),
        )
        entries = self._digest_planner.plan(eligible, content_kind, policy)
        if not entries:
            return None
        title, items = self._telegram_messages.build_daily_report(entries, content_kind, now)
        return PreparedDailyReport(
            date=now.strftime("%Y-%m-%d"),
            content_kind=content_kind,
            title=title,
            entries=entries,
            items=items,
            content=self._telegram_messages.compose_daily_report_part(title, items),
            parts=self._telegram_messages.split_daily_report_parts(title, items),
        )

    def persist_success(self, report: PreparedDailyReport, publication_key: str | None = None) -> int:
        if not publication_key:
            import hashlib

            digest = hashlib.sha256(report.content.encode("utf-8")).hexdigest()[:20]
            publication_key = f"report:{report.content_kind}:{report.date}:{digest}"
        with self._transaction() as tx_repos:
            report_id = tx_repos.daily_reports.save_report(
                publication_key, report.date, report.content_kind, report.title, report.content, len(report.items)
            )
            tx_repos.daily_reports.save_report_items(report_id, report.entries)
            tx_repos.review.mark_delivered([entry["id"] for entry in report.entries])
            return report_id
