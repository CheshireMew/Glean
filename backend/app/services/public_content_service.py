from __future__ import annotations

from datetime import datetime, timezone
from email.utils import format_datetime
from html import escape
from typing import Dict, Optional
import base64
import json

from ..core.exceptions import ValidationError


class PublicContentService:
    def __init__(
        self,
        editorial_profile_repository,
        review_public_repository,
        daily_report_repository,
        publication_repository,
        public_site_url: str,
        public_links: dict[str, str],
    ):
        self._editorial_profile_repository = editorial_profile_repository
        self._review_public_repository = review_public_repository
        self._daily_report_repository = daily_report_repository
        self._publication_repository = publication_repository
        self._public_site_url = public_site_url
        self._public_links = dict(public_links)

    def _public_publication(self, public_slug: str | None, require_rss: bool = False) -> Dict | None:
        if not public_slug:
            return None
        publication = self._publication_repository().get_publication_by_public_slug(public_slug)
        if not publication or not publication.get("enabled") or not publication.get("is_public"):
            return None
        if require_rss and not publication.get("rss_enabled"):
            return None
        return publication

    def get_public_config(self) -> Dict:
        publications = self._publication_repository().list_publications(public_only=True)
        return {
            "site_url": self._public_site_url,
            "links": dict(self._public_links),
            "publications": [
                {
                    "public_slug": item["public_slug"],
                    "display_name": item["display_name"],
                    "description": item["description"],
                    "content_type": item["content_type"],
                    "rss_enabled": item["rss_enabled"],
                }
                for item in publications
            ],
        }

    def get_public_content(
        self,
        content_kind: str,
        limit: int,
        offset: int,
        cursor: str | None = None,
        known_revision: str | None = None,
        publication_slug: str | None = None,
    ) -> Dict:
        if publication_slug:
            publication = self._public_publication(publication_slug)
            profile = (
                self._editorial_profile_repository().get(publication["profile_slug"])
                if publication and publication["content_type"] == content_kind
                else None
            )
        else:
            profile = self._editorial_profile_repository().get_default(content_kind)
        if not profile:
            return {
                "items": [], "total": 0, "limit": limit, "offset": offset,
                "next_cursor": None, "revision": f"{content_kind}:none", "not_modified": False,
            }
        decoded_cursor = self._decode_cursor(cursor) if cursor else None
        repository = self._review_public_repository()
        for _attempt in range(2):
            revision = repository.get_public_revision(content_kind, profile["slug"])
            if known_revision and known_revision == revision:
                return {
                    "items": [], "total": 0, "limit": limit, "offset": offset,
                    "next_cursor": None, "revision": revision, "not_modified": True,
                }
            result = repository.list_public_entries(
                content_kind, profile["slug"], limit, offset, decoded_cursor
            )
            current_revision = repository.get_public_revision(content_kind, profile["slug"])
            if current_revision == revision:
                next_cursor_data = result.pop("next_cursor_data", None)
                result["next_cursor"] = self._encode_cursor(next_cursor_data) if next_cursor_data else None
                result["revision"] = revision
                result["not_modified"] = False
                return result
            known_revision = None
        raise RuntimeError("公开内容在读取期间持续变化，请稍后重试")

    def get_public_reports(
        self,
        content_kind: Optional[str],
        limit: int,
        offset: int,
        query: str | None = None,
        publication_slug: str | None = None,
    ) -> Dict:
        publication_id = None
        if publication_slug:
            publication = self._public_publication(publication_slug)
            if not publication or (content_kind and publication["content_type"] != content_kind):
                return {"items": [], "total": 0, "limit": limit, "offset": offset}
            publication_id = int(publication["id"])
        return self._daily_report_repository().list_reports(content_kind, limit, offset, query, publication_id)

    def search_public_content(
        self, query_text: str, content_kind: str, limit: int, offset: int,
        publication_slug: str | None = None,
    ) -> Dict:
        requested_kinds = (content_kind,) if content_kind in {"news", "article"} else ("news", "article")
        if publication_slug:
            publication = self._public_publication(publication_slug)
            profiles = {
                publication["content_type"]: self._editorial_profile_repository().get(publication["profile_slug"])
            } if publication and publication["content_type"] in requested_kinds else {}
        else:
            profiles = {
                kind: profile
                for kind in requested_kinds
                if (profile := self._editorial_profile_repository().get_default(kind))
            }
        if not profiles:
            return {"items": [], "total": 0, "limit": limit, "offset": offset, "query": query_text}
        return self._review_public_repository().search_public_entries(
            query_text,
            content_kind,
            {kind: profile["slug"] for kind, profile in profiles.items()},
            limit,
            offset,
        )

    def build_public_rss(self, content_kind: str, limit: int, publication_slug: str | None = None) -> str:
        publication = self._public_publication(publication_slug, require_rss=True) if publication_slug else None
        if publication_slug and not publication:
            items = []
        else:
            payload = self.get_public_content(content_kind, limit, 0, publication_slug=publication_slug)
            items = payload.get("items", [])
        title = publication["display_name"] if publication else ("Glean 快讯" if content_kind == "news" else "Glean 文章")
        description = "Glean 公开内容 RSS"
        pub_date = format_datetime(datetime.now(timezone.utc))
        xml_items = "\n".join(self._rss_item_xml(item) for item in items)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0">\n'
            "  <channel>\n"
            f"    <title>{escape(title)}</title>\n"
            f"    <link>{escape(self._public_site_url)}/</link>\n"
            f"    <description>{escape(description)}</description>\n"
            "    <language>zh-cn</language>\n"
            f"    <lastBuildDate>{pub_date}</lastBuildDate>\n"
            f"{xml_items}\n"
            "  </channel>\n"
            "</rss>\n"
        )

    def _rss_item_xml(self, item: Dict) -> str:
        link = item.get("source_url") or ""
        description = item.get("review_summary") or item.get("review_reason") or ""
        pub_date = self._rss_pub_date(item.get("published_at"))
        return (
            "    <item>\n"
            f"      <title>{escape(item.get('title') or '')}</title>\n"
            f"      <link>{escape(link)}</link>\n"
            f"      <guid>{escape(link or str(item.get('id') or ''))}</guid>\n"
            f"      <description>{escape(description)}</description>\n"
            f"      <category>{escape(item.get('review_category') or item.get('source_site') or '')}</category>\n"
            f"      <pubDate>{pub_date}</pubDate>\n"
            "    </item>"
        )

    @staticmethod
    def _rss_pub_date(value: str | None) -> str:
        if not value:
            return format_datetime(datetime.now(timezone.utc))
        for parser in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return format_datetime(datetime.strptime(value, parser).replace(tzinfo=timezone.utc))
            except Exception:
                continue
        return format_datetime(datetime.now(timezone.utc))

    @staticmethod
    def _encode_cursor(value: tuple[str, int]) -> str:
        payload = json.dumps({"published_at": value[0], "id": value[1]}, separators=(",", ":"))
        return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_cursor(value: str) -> tuple[str, int]:
        try:
            padded = value + "=" * (-len(value) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
            return str(payload["published_at"]), int(payload["id"])
        except Exception as exc:
            raise ValidationError("公开流游标无效") from exc
