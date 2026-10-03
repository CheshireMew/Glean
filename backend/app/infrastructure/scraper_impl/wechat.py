from datetime import datetime, timezone

from ...domain.wechat import wechat_source_name
from ..wechat_gateway import article_url, plain_text
from .base import BaseScraper


class WechatScraper(BaseScraper):
    transport_kind = 'api'
    allow_empty_results = True

    def __init__(self, source, gateway):
        super().__init__(wechat_source_name(source['name']), 'https://mp.weixin.qq.com/', source['default_limit'])
        self.news_type = 'article'
        self._source = source
        self._gateway = gateway

    async def scrape_important_news(self):
        result = self.create_result_buffer()
        seen = set()
        # Each batch contains up to eight articles. Bound work even for a large history.
        for page in range((self.max_items + 4) // 5):
            items, has_more = await self._gateway.articles(self._source['fake_id'], page * 5)
            valid = 0
            fresh = 0
            for item in items:
                url = article_url(item.get('link'))
                title = plain_text(item.get('title'))
                try:
                    published = datetime.fromtimestamp(int(item['create_time']), timezone.utc).isoformat()
                except (KeyError, ValueError, TypeError, OverflowError, OSError):
                    continue
                if not url or not title:
                    continue
                valid += 1
                if url in seen:
                    continue
                seen.add(url)
                if self.incremental_mode and url in self.existing_urls:
                    continue
                fresh += 1
                result.append({'title': title, 'url': url, 'published_at': published,
                               'content': plain_text(item.get('content') or item.get('digest')),
                               'author': plain_text(item.get('author')) or self._source['name']})
                if len(result) >= self.max_items:
                    return result
            if items and not valid:
                raise RuntimeError('公众号返回了文章，但缺少有效标题、链接或发布时间')
            if not has_more or (valid and not fresh):
                break
        return result
