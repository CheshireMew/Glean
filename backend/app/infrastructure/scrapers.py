from __future__ import annotations

from dataclasses import dataclass

from .scraper_impl.blockbeats import BlockBeatsScraper
from .scraper_impl.blockbeats_article import BlockBeatsArticleScraper
from .scraper_impl.chaincatcher import ChainCatcherScraper
from .scraper_impl.chaincatcher_article import ChainCatcherArticleScraper
from .scraper_impl.foresight import ForesightScraper
from .scraper_impl.foresight_article import (
    ForesightDepthScraper,
    ForesightExclusiveScraper,
    ForesightExpressScraper,
)
from .scraper_impl.hacker_news import HackerNewsScraper
from .scraper_impl.lobsters import LobstersScraper
from .scraper_impl.waytoagi import WaytoAGIScraper
from .scraper_impl.juejin_ai import JuejinAIScraper
from .scraper_impl.marsbit import MarsBitScraper
from .scraper_impl.marsbit_article import MarsBitArticleScraper
from .scraper_impl.odaily import OdailyScraper
from .scraper_impl.odaily_article import OdailyArticleScraper
from .scraper_impl.panews import PANewsScraper
from .scraper_impl.panews_article import PANewsArticleScraper
from .scraper_impl.techflow import TechFlowScraper
from .scraper_impl.techflow_article import TechflowArticleScraper
from .scraper_impl.wublock_article import WuBlockArticleScraper


@dataclass(frozen=True)
class ScraperDefinition:
    name: str
    scraper_cls: type
    content_kind: str
    default_limit: int
    default_interval: int
    homepage_url: str | None = None
    authority_type: str = "media"

    def display_name(self) -> str:
        try:
            return self.scraper_cls().site_name
        except Exception:
            return self.name

    def source_site(self) -> str:
        return self.display_name()


class ScraperCatalog:
    def __init__(self):
        definitions = [
            ScraperDefinition("techflow", TechFlowScraper, "news", 5, 60),
            ScraperDefinition("odaily", OdailyScraper, "news", 5, 60),
            ScraperDefinition("blockbeats", BlockBeatsScraper, "news", 5, 60),
            ScraperDefinition("foresight", ForesightScraper, "news", 5, 60),
            ScraperDefinition("chaincatcher", ChainCatcherScraper, "news", 5, 60),
            ScraperDefinition("panews", PANewsScraper, "news", 5, 60),
            ScraperDefinition("marsbit", MarsBitScraper, "news", 5, 60),
            ScraperDefinition("foresight_exclusive", ForesightExclusiveScraper, "article", 20, 240),
            ScraperDefinition("foresight_express", ForesightExpressScraper, "article", 20, 240),
            ScraperDefinition("foresight_depth", ForesightDepthScraper, "article", 20, 240),
            ScraperDefinition("blockbeats_article", BlockBeatsArticleScraper, "article", 20, 240),
            ScraperDefinition("chaincatcher_article", ChainCatcherArticleScraper, "article", 20, 240),
            ScraperDefinition("marsbit_article", MarsBitArticleScraper, "article", 20, 240),
            ScraperDefinition("odaily_article", OdailyArticleScraper, "article", 20, 240),
            ScraperDefinition("panews_article", PANewsArticleScraper, "article", 20, 240),
            ScraperDefinition("techflow_article", TechflowArticleScraper, "article", 20, 240),
            ScraperDefinition("wublock_article", WuBlockArticleScraper, "article", 20, 240),
            ScraperDefinition("hacker_news", HackerNewsScraper, "article", 30, 60,
                              "https://news.ycombinator.com/", "aggregator"),
            ScraperDefinition("lobsters", LobstersScraper, "article", 20, 240,
                              "https://lobste.rs/recent", "aggregator"),
            ScraperDefinition("waytoagi", WaytoAGIScraper, "article", 100, 240,
                              "https://waytoagi.feishu.cn/wiki/QPe5w5g7UisbEkkow8XcDmOpn8e", "aggregator"),
            ScraperDefinition("juejin_ai", JuejinAIScraper, "article", 20, 240,
                              "https://juejin.cn/ai", "aggregator"),
        ]
        self._items = {item.name: item for item in definitions}

    def get(self, name: str) -> ScraperDefinition | None:
        return self._items.get(name)

    def names(self) -> list[str]:
        return list(self._items.keys())

    def definitions(self) -> list[ScraperDefinition]:
        return list(self._items.values())


scraper_catalog = ScraperCatalog()
