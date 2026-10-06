from .marsbit import MarsBitScraper


class MarsBitArticleScraper(MarsBitScraper):
    source_name = 'MarsBit Article'
    endpoint = 'https://api.marsbit.co/info/news/shownews'
    content_kind = 'article'
