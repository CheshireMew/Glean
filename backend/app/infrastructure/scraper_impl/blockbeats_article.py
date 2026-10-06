import json
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ...core.config import settings
from .blockbeats import BlockBeatsScraper
from .media_feed import media_identity


class BlockBeatsArticleScraper(BlockBeatsScraper):
    source_name = 'BlockBeats Article'
    endpoint = 'https://api-pro.theblockbeats.info/v1/article'
    content_kind = 'article'
    transport_kind = 'api' if settings.BLOCKBEATS_API_KEY else 'http'

    def __init__(self):
        super().__init__()
        if self.transport_kind == 'http':
            self.api_url = self.homepage + '/article_choice'

    def configuration_error(self):
        return super().configuration_error() if self.transport_kind == 'api' else None

    async def scrape_important_news(self):
        if self.transport_kind == 'api':
            return await super().scrape_important_news()
        # This already-working column is also present in the HTTP response.
        # Keep it usable until a Key is configured, without launching Chromium.
        soup = BeautifulSoup(await self.fetch_text(self.api_url), 'html.parser')
        links = soup.select('.article-item-title[href]')
        if not links:
            raise RuntimeError('律动精选文章列表结构已变化')
        known = {media_identity(url) for url in self.existing_urls}
        if self.last_news_url:
            known.add(media_identity(self.last_news_url))
        results = self.create_result_buffer()
        seen = set()
        for link in links:
            url = urljoin(self.homepage, link['href'])
            identity = media_identity(url)
            if identity in seen:
                continue
            seen.add(identity)
            if self.incremental_mode and identity in known:
                self.encountered_existing_items = True
                continue
            detail = BeautifulSoup(await self.fetch_text(url), 'html.parser')
            content = detail.select_one('.news-content')
            metadata = None
            for tag in detail.find_all('script', type='application/ld+json'):
                value = json.loads(tag.get_text())
                if isinstance(value, dict) and value.get('@type') == 'NewsArticle':
                    metadata = value
                    break
            if not content or not metadata:
                raise RuntimeError('律动文章正文或发布时间结构已变化')
            author = metadata.get('author')
            results.append(self.make_item(title=metadata.get('headline') or link.get_text(strip=True),
                                          content=str(content), url=url, date=metadata.get('datePublished'),
                                          author=author.get('name') if isinstance(author, dict) else None))
            if len(results) >= self.max_items:
                break
        return results
