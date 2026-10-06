import re
from urllib.parse import urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup

from ...core.config import settings
from .media_feed import MediaApiScraper, media_identity


class BlockBeatsScraper(MediaApiScraper):
    source_name = 'blockbeats'
    homepage = 'https://www.theblockbeats.info'
    endpoint = 'https://api-pro.theblockbeats.info/v1/newsflash'
    transport_kind = 'api' if settings.BLOCKBEATS_API_KEY else 'http'

    def __init__(self):
        super().__init__()
        if self.transport_kind == 'http':
            self.api_url = self.homepage + '/newsflash'

    def configuration_error(self):
        if self.transport_kind == 'api' and not settings.BLOCKBEATS_API_KEY:
            return f'律动采集需要 BLOCKBEATS_API_KEY；请在 .env.{settings.ENV} 或系统环境变量中配置后重启 API 和 worker'
        return None

    def prepare(self):
        error = self.configuration_error()
        if error:
            raise RuntimeError(error)
        self.api_key = settings.BLOCKBEATS_API_KEY

    async def scrape_important_news(self):
        if self.transport_kind == 'api':
            return await super().scrape_important_news()
        return self.select_new_items(self.parse_public_news(await self.fetch_text(self.api_url)))

    def parse_public_news(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        groups = soup.select('.flash-list')
        if not groups or not soup.select('.flash-list .news-flash-wrapper'):
            raise RuntimeError('律动公开快讯列表结构已变化')
        items = []
        for group in groups:
            date = group.select_one('.flash-list-today')
            day = date.get_text(strip=True) if date else ''
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
                raise RuntimeError('律动公开快讯缺少日期')
            for node in group.select('.news-flash-wrapper'):
                link = node.select_one('a.news-flash-title[href]')
                title = node.select_one('.news-flash-title-text')
                if not link or not title:
                    raise RuntimeError('律动公开快讯缺少标题或链接')
                flags = []
                # The site's template uses ios > 0 for this class and
                # is_first == 1 for the first-published icon.
                if 'news-flash-title-text-active' in title.get('class', []):
                    flags.append('important')
                if node.select_one('.home-first-png'):
                    flags.append('first')
                if not flags or node.select_one('.premium-unlock-btn'):
                    continue
                url = urljoin(self.homepage, link['href'])
                if urlsplit(url).hostname != 'www.theblockbeats.info' or not re.fullmatch(r'/flash/\d+', urlsplit(url).path):
                    raise RuntimeError('律动公开快讯链接格式已变化')
                clock = re.match(r'^(\d{1,2}:\d{2})\b', link.get_text(' ', strip=True))
                content = node.select_one('.news-flash-item-content')
                if not clock or content is None:
                    raise RuntimeError('律动公开快讯缺少时间或正文节点')
                items.append(self.make_item(
                    title=title.get_text(' ', strip=True), content=str(content), url=media_identity(url),
                    date=f'{day} {clock.group(1)}:00', importance_flag='+'.join(flags),
                ))
        return items

    async def fetch_items_page(self, page):
        self.prepare()
        items = []
        has_more = False
        kinds = ('important', 'first') if self.news_type == 'news' else ('important',)
        for kind in kinds:
            url = self.api_url + '/' + kind + '?' + urlencode({'page': page, 'size': self.page_size, 'lang': 'cn'})
            payload = await self.transport.fetch_json(url, headers={'api-key': self.api_key})
            if not isinstance(payload, dict) or payload.get('status') != 0:
                # Do not echo an arbitrary provider response that could contain credentials.
                raise RuntimeError('律动 API 认证、额度或业务请求失败，请检查 Key 和官网额度')
            data = payload.get('data')
            if not isinstance(data, dict) or not isinstance(data.get('data'), list):
                raise RuntimeError('律动 API 列表格式已变化')
            rows = data['data']
            if any(not isinstance(row, dict) for row in rows):
                raise RuntimeError('律动 API 条目格式已变化')
            items.extend(dict(row, _glean_kind=kind) for row in rows)
            has_more = has_more or len(rows) >= self.page_size
        # Merge important and first-published lists before applying the configured limit.
        items.sort(key=lambda row: self.item_date(row), reverse=True)
        return items, has_more

    @staticmethod
    def item_date(raw):
        from .media_feed import published_at
        return published_at(raw.get('create_time'))

    def parse_item(self, raw):
        url = raw.get('link')
        if not url:
            raise RuntimeError('律动 API 条目缺少站内链接')
        return self.make_item(title=raw.get('title'), content=raw.get('content') or raw.get('description'),
                              url=media_identity(url), date=raw.get('create_time'), author=raw.get('author'),
                              content_is_html=bool(raw.get('content')),
                              importance_flag=raw.get('_glean_kind', '') if self.news_type == 'news' else '')
