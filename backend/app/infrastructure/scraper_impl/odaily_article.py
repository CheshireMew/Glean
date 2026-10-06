from .odaily import OdailyScraper


class OdailyArticleScraper(OdailyScraper):
    source_name = 'Odaily Article'
    endpoint = 'https://api.odaily.news/api/v1/article'
    content_kind = 'article'
