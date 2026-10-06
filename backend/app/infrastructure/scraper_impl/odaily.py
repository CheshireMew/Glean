from urllib.parse import urlencode

from .media_feed import MediaApiScraper


class OdailyScraper(MediaApiScraper):
    source_name = 'odaily'
    homepage = 'https://www.odaily.news'
    endpoint = 'https://api.odaily.news/api/v1/newsflash'

    async def fetch_items_page(self, page):
        params = {'page': page, 'size': self.page_size, 'lang': 'zh-cn'}
        if self.news_type == 'news':
            params['isImportant'] = 'true'
        payload = await self.transport.fetch_json(self.api_url + '?' + urlencode(params))
        if not isinstance(payload, dict) or payload.get('code') != 200 or payload.get('success') is not True:
            raise RuntimeError('Odaily API 未返回成功结果')
        data = payload.get('data')
        if not isinstance(data, dict) or not isinstance(data.get('list'), list):
            raise RuntimeError('Odaily API 列表格式已变化')
        return data['list'], data.get('hasMore', False)

    def parse_item(self, raw):
        # The server currently ignores isImportant=true; check the actual boolean.
        if self.news_type == 'news' and not isinstance(raw.get('isImportant'), bool):
            raise RuntimeError('Odaily 快讯缺少重要标记')
        if self.news_type == 'news' and raw.get('isImportant') is not True:
            return None
        return self.make_item(title=raw.get('title'), content=raw.get('content') or raw.get('summary'),
                              url=raw.get('link'), date=raw.get('publishTimestamp') or raw.get('publishDate'),
                              author=raw.get('author'),
                              content_is_html=bool(raw.get('content')),
                              importance_flag='isImportant' if self.news_type == 'news' else '')
