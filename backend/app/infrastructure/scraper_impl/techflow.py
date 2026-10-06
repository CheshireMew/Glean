from .media_feed import MediaRssScraper


class TechFlowScraper(MediaRssScraper):
    source_name = 'techflow'
    homepage = 'https://www.techflowpost.com'
    feed = 'https://www.techflowpost.com/rss/v2/feed.xml?lang=zh-CN&type=newsflash&topic=all&tag=featured'
    content_kind = 'news'
    required_category = None
    importance_flag = 'featured'
