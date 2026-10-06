from .media_feed import MediaApiScraper


class ChainCatcherScraper(MediaApiScraper):
    source_name = 'chaincatcher'
    homepage = 'https://www.chaincatcher.com'
    endpoint = 'https://www.api.chaincatcher.com/pc/content/page'

    async def fetch_items_page(self, page):
        payload = await self.transport.fetch_json(self.api_url, method='POST', json_body={
            'type': 2, 'newsFlashTypes': [2], 'pageNumber': page, 'pageSize': self.page_size,
        })
        if not isinstance(payload, dict) or payload.get('result') != 1:
            raise RuntimeError('ChainCatcher API 未返回成功结果')
        data = payload.get('data')
        if not isinstance(data, dict) or not isinstance(data.get('items'), list):
            raise RuntimeError('ChainCatcher API 列表格式已变化')
        return data['items'], page * self.page_size < int(data.get('total', 0))

    def parse_item(self, raw):
        # This is the exact field used by the site's selectedClass and filter switch.
        if 'type' not in raw or 'newsFlashType' not in raw:
            raise RuntimeError('ChainCatcher 快讯缺少类型或精选标记')
        if raw.get('type') != 2 or raw.get('newsFlashType') != 2:
            return None
        identifier = raw.get('id')
        if not identifier:
            raise RuntimeError('ChainCatcher 快讯缺少 ID')
        return self.make_item(title=raw.get('title'), content=raw.get('description'),
                              url=f'https://www.chaincatcher.com/article/{identifier}',
                              date=raw.get('releaseTime') or raw.get('createTime'),
                              importance_flag='newsFlashType=2', content_is_html=False)
