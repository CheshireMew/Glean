from .media_feed import MediaRssScraper


class PANewsArticleScraper(MediaRssScraper):
    source_name = 'PANews Article'
    homepage = 'https://www.panewslab.com'
    feed = 'https://www.panewslab.com/rss.xml?lang=zh&type=NORMAL&in-depth=true'
    content_kind = 'article'
    required_category = None
    importance_flag = ''
