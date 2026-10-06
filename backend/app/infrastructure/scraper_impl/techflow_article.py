from .media_feed import MediaRssScraper


class TechflowArticleScraper(MediaRssScraper):
    source_name = 'Techflow Article'
    homepage = 'https://www.techflowpost.com'
    feed = 'https://www.techflowpost.com/rss/v2/feed.xml?lang=zh-CN&type=article&topic=all&tag=all'
    content_kind = 'article'
    required_category = None
    importance_flag = ''
