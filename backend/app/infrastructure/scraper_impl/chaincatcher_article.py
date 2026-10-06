from .media_feed import MediaRssScraper


class ChainCatcherArticleScraper(MediaRssScraper):
    source_name = 'ChainCatcher Article'
    homepage = 'https://www.chaincatcher.com'
    feed = 'https://www.chaincatcher.com/rss/clist'
    content_kind = 'article'
    required_category = '文章'
    importance_flag = ''
