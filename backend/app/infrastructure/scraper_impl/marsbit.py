import re
from urllib.parse import urlencode

from .media_feed import MediaApiScraper, html_text


class MarsBitScraper(MediaApiScraper):
    source_name = 'marsbit'
    homepage = 'https://news.marsbit.co'
    endpoint = 'https://api.marsbit.co/info/lives/showlives'

    async def fetch_items_page(self, page):
        params = {'currentPage': page, 'pageSize': self.page_size}
        if self.news_type == 'news':
            params['important'] = 1
        payload = await self.transport.fetch_json(self.api_url + '?' + urlencode(params))
        if not isinstance(payload, dict) or payload.get('code') != 1:
            raise RuntimeError('MarsBit API 未返回成功结果')
        data = payload.get('obj')
        if not isinstance(data, dict) or not isinstance(data.get('inforList'), list):
            raise RuntimeError('MarsBit API 列表格式已变化')
        return data['inforList'], page < int(data.get('pageCount', 0))

    def parse_item(self, raw):
        if self.news_type == 'news' and 'tag' not in raw:
            raise RuntimeError('MarsBit 快讯缺少重要标记')
        if self.news_type == 'news' and raw.get('tag') != 2:
            return None
        identifier = raw.get('id')
        if not identifier:
            raise RuntimeError('MarsBit 条目缺少 ID')
        if self.news_type == 'article':
            return self.make_item(title=raw.get('title'), content=raw.get('synopsis'),
                                  url=f'https://news.marsbit.co/{identifier}.html',
                                  date=raw.get('publishTime') or raw.get('createTime'),
                                  author=raw.get('nickName') or raw.get('author'), content_is_html=False)
        content = html_text(raw.get('content'))
        match = re.match(r'^【([^】]+)】', content)
        title = raw.get('title') or (match.group(1) if match else '')
        if match:
            content = content[match.end():].strip()
        return self.make_item(title=title, content=content,
                              url=f'https://news.marsbit.co/flash/{identifier}.html',
                              date=raw.get('createdTime'), author=raw.get('author'),
                              importance_flag='tag=2', content_is_html=False)
