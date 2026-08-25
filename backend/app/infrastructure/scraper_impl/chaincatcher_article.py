"""
ChainCatcher 文章爬虫（使用 Playwright）
抓取 ChainCatcher 深度文章
"""

from .article_base import ArticleScraper
from typing import List, Dict, Optional

class ChainCatcherArticleScraper(ArticleScraper):
    """ChainCatcher 文章爬虫"""
    
    def __init__(self):
        super().__init__('ChainCatcher Article', 'https://www.chaincatcher.com', max_items=20)
        self.base_url = 'https://www.chaincatcher.com'
        self.list_url = 'https://www.chaincatcher.com/article'
        self.list_wait_selector = '.article_wraper'
    
    async def _scrape_list_articles(self) -> List[Dict]:
        """抓取列表文章"""
        articles = self.create_result_buffer()
        
        # 查找文章容器 (List Page)
        # 结构: .items.pb-2 -> .article_wraper
        items = await self.page.query_selector_all('.items')
        
        print(f"找到 {len(items)} 个列表项")
        
        for item in items:
            try:
                # 1. 提取标题和链接
                title_elem = await item.query_selector('.article_title_span')
                link_elem = await item.query_selector('a.content') # 链接容器
                
                if not title_elem or not link_elem:
                    continue
                
                title = await title_elem.text_content()
                title = title.strip()
                href = await link_elem.get_attribute('href')
                
                if not title or not href:
                    continue
                    
                full_url = self.base_url + href if href.startswith('/') else href
                
                # 2. 提取摘要（List Page）
                summary = ""
                summary_elem = await item.query_selector('.article_content.small_article')
                if summary_elem:
                    summary = await summary_elem.text_content()
                    summary = summary.strip()

                # 3. 提取列表页隐藏时间 (e.g. 2025-12-31 12:41:28)
                publish_time = None
                time_elem = await item.query_selector('.hiddenTime')
                if time_elem:
                    raw_time = await time_elem.text_content()
                    publish_time = raw_time.strip()
                
                # 检查增量抓取
                if self.should_stop_scraping(title, full_url):
                    print(f"  [增量抓取] 停止: {title}")
                    break
                
                # 4. 获取详情页信息 (作者、正文、更准确的时间)
                details = await self._fetch_article_details(full_url)
                
                if details:
                    # 如果详情页有更准确的时间/作者，覆盖之
                    if details.get('author'):
                        author = details['author']
                    else:
                        author = 'ChainCatcher'
                        
                    content = details.get('content', '') or summary
                    
                    # 优先使用详情页时间，如果缺失则使用列表页时间
                    published_at = details.get('published_at') or publish_time
                    
                    articles.append({
                        'title': title,
                        'content': content,
                        'url': full_url,
                        'published_at': published_at,
                        'source_site': self.site_name,
                        'author': author,
                        'summary': summary,
                        'type': self.news_type
                    })
                    print(f"  ✅ 抓取成功: {title} ({author})")
                
            except Exception as e:
                print(f"  ⚠️ 处理单条失败: {e}")
                continue
                
        return articles

    async def _fetch_article_details(self, url: str) -> Optional[Dict]:
        """获取文章详情"""
        try:
            async with self.detail_page(url, load_delay_seconds=1) as page:
                author = "ChainCatcher"
                try:
                    author_elem = await page.query_selector('.information .name')
                    if author_elem:
                        author = (await author_elem.text_content()).strip()
                except Exception:
                    pass

                published_at = None
                try:
                    time_elem = await page.query_selector('.information .time')
                    if time_elem:
                        published_at = (await time_elem.text_content()).strip()
                except Exception:
                    pass

                content = ""
                try:
                    content_elem = (
                        await page.query_selector('.article_content')
                        or await page.query_selector('#content')
                        or await page.query_selector('.main-content')
                    )
                    if content_elem:
                        content = await content_elem.inner_text()
                except Exception:
                    pass

                return {
                    'author': author,
                    'published_at': published_at,
                    'content': content,
                }
        except Exception as e:
            print(f"    ⚠️ 详情页加载失败: {e}")
            return None
