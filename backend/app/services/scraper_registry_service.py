from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..core.exceptions import NotFoundError
from .rss_source_service import rss_runtime_name


@dataclass(frozen=True)
class RegisteredScraper:
    name: str
    display_name: str
    source_site: str
    content_kind: str
    default_limit: int
    default_interval: int
    source_type: str
    transport_kind: str
    build_scraper: Callable[[], object]
    homepage_url: str | None = None
    authority_type: str = "media"
    is_official: bool = False


class ScraperRegistryService:
    def __init__(self, rss_sources, site_definitions, rss_scraper_factory):
        self._rss_sources = rss_sources
        self._site_definitions = tuple(site_definitions)
        self._rss_scraper_factory = rss_scraper_factory

    def list_definitions(self) -> list[RegisteredScraper]:
        definitions = list(self._site_definitions)

        for source in self._rss_sources.list_enabled_sources():
            definitions.append(
                RegisteredScraper(
                    name=rss_runtime_name(source["slug"]),
                    display_name=source["display_name"],
                    source_site=source["display_name"],
                    content_kind=source["content_kind"],
                    default_limit=source["default_limit"],
                    default_interval=source["default_interval"],
                    source_type="rss",
                    transport_kind="rss",
                    build_scraper=lambda source=source: self._rss_scraper_factory(source),
                    homepage_url=source["site_url"],
                    authority_type=source.get("authority_type") or "media",
                    is_official=bool(source.get("is_official")),
                )
            )

        return definitions

    def names(self) -> list[str]:
        return [definition.name for definition in self.list_definitions()]

    def get(self, name: str) -> RegisteredScraper | None:
        for definition in self.list_definitions():
            if definition.name == name:
                return definition
        return None

    def require(self, name: str) -> RegisteredScraper:
        definition = self.get(name)
        if not definition:
            raise NotFoundError("爬虫不存在")
        return definition
