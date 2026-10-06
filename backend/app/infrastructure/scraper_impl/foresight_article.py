"""ForesightNews 文章爬虫 - 独立专栏版"""
from .article_base import ArticleScraper
from typing import List, Dict
from datetime import datetime

class BaseForesightColumnScraper(ArticleScraper):
    """Foresight 专栏爬虫基类"""
    
    def __init__(self, column_name: str, column_url: str):
        # site_name 直接使用专栏名，确保数据库中 source_site 区分开，实现独立增量
        # e.g. "ForesightNews 独家"
        self.column_name = column_name
        self.column_url = column_url
        super().__init__(column_name, column_url, max_items=20)
        self.news_type = 'article'
        self.list_url = column_url

    async def _scrape_list_articles(self) -> List[Dict]:
        """解析单个专栏的列表页。"""
        print(f"\n📚 抓取专栏: {self.column_name}")
        articles = self.create_result_buffer()
        processed_urls = set()
        article_elements = await self.page.query_selector_all(
            '.article-content.TopicItem'
        )
        print(f"  [DEBUG] {self.column_name}: 找到 {len(article_elements)} 个文章")

        for article_el in article_elements:
            try:
                title_el = await article_el.query_selector('.article-body-title')
                if not title_el:
                    continue
                title = await self.safe_extract_text(title_el)
                if not title or len(title) < 5:
                    continue

                link_el = await article_el.query_selector(
                    'a[href^="/article/detail/"]'
                )
                if not link_el:
                    continue
                url = await self.safe_get_attribute(link_el, 'href')
                if not url:
                    continue
                if not url.startswith('http'):
                    url = f"https://foresightnews.pro{url}"

                if url in processed_urls:
                    continue
                processed_urls.add(url)

                summary_el = await article_el.query_selector('.article-body-content')
                summary = (
                    await self.safe_extract_text(summary_el) if summary_el else ''
                )
                time_el = await article_el.query_selector('.article-time')
                time_str = await self.safe_extract_text(time_el) if time_el else ''

                published_at = datetime.now()
                if time_str and len(time_str) >= 10:
                    try:
                        published_at = datetime.strptime(time_str, '%Y-%m-%d %H:%M')
                    except Exception:
                        try:
                            published_at = datetime.strptime(time_str[:10], '%Y-%m-%d')
                        except Exception:
                            pass

                if self.should_stop_scraping(title, url, published_at):
                    print("  [增量抓取] 遇到已抓取文章，停止")
                    break
                if self.incremental_mode and (url in self.existing_urls or url == self.last_news_url):
                    continue
                if len(articles) >= self.max_items:
                    print(f"  [数量限制] 已抓取 {self.max_items} 篇，停止")
                    break

                content = summary if summary and len(summary) > 10 else title
                content = self.clean_content(content, title)
                article_item = {
                    'title': title,
                    'content': content,
                    'url': url,
                    'published_at': published_at,
                    'is_marked_important': False,
                    'site_importance_flag': '',
                    'type': self.news_type,
                    'author': self.column_name,
                }
                articles.append(article_item)
                print(f"  ✅ {title[:30]}...")
            except Exception as e:
                print(f"  解析文章失败: {e}")
                continue

        print(f"  {self.column_name}: 抓取到 {len(articles)} 篇文章")
        return articles

class ForesightExclusiveScraper(BaseForesightColumnScraper):
    def __init__(self):
        super().__init__('ForesightNews 独家', 'https://foresightnews.pro/column/detail/1')

class ForesightExpressScraper(BaseForesightColumnScraper):
    def __init__(self):
        super().__init__('ForesightNews 速递', 'https://foresightnews.pro/column/detail/2')

class ForesightDepthScraper(BaseForesightColumnScraper):
    def __init__(self):
        super().__init__('ForesightNews 深度', 'https://foresightnews.pro/column/detail/894')
