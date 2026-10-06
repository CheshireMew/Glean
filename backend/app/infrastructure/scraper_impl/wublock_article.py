from .media_feed import MediaRssScraper


class WuBlockArticleScraper(MediaRssScraper):
    source_name = 'WuBlock Article'
    homepage = 'https://www.wublock123.com'
    feed = 'https://www.wublock123.com/rss'
    content_kind = 'article'
    required_category = '深度'
    importance_flag = ''

    def accepts_entry(self, entry):
        return super().accepts_entry(entry) and '/articles/' in self._extract_url(entry)
