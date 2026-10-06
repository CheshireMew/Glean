from .media_feed import MediaRssScraper


class PANewsScraper(MediaRssScraper):
    source_name = 'panews'
    homepage = 'https://www.panewslab.com'
    feed = 'https://www.panewslab.com/rss.xml?lang=zh&type=NEWS&featured=true'
    content_kind = 'news'
    required_category = None
    importance_flag = 'featured'
