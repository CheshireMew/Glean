"""
Odaily 文章爬虫
Target: https://www.odaily.news/zh-CN/post
"""
from .article_base import ArticleScraper
from typing import List, Dict, Optional
import re

class OdailyArticleScraper(ArticleScraper):
    """Odaily 深度文章爬虫"""
    
    def __init__(self):
        super().__init__('Odaily Article', 'https://www.odaily.news', max_items=20)
        self.base_url = 'https://www.odaily.news'
        self.list_url = 'https://www.odaily.news/zh-CN/post'
        self.list_wait_selector = 'a[href*="/zh-CN/post/"]'

    async def _scrape_list_articles(self) -> List[Dict]:
        """抓取列表文章"""
        articles = self.create_result_buffer()
        
        # 查找所有文章链接
        # 策略：找到包含 /zh-CN/post/ 数字ID 的链接
        # href 例如: /zh-CN/post/5208487
        link_elems = await self.page.query_selector_all('a[href*="/zh-CN/post/"]')
        print(f"找到 {len(link_elems)} 个潜在链接")
        
        processed_urls = set()
        
        for link in link_elems:
            try:
                href = await link.get_attribute('href')
                if not href or '/post/' not in href:
                    continue
                    
                # 简单的去重（避免同一个链接多次出现）
                if href in processed_urls:
                    continue
                processed_urls.add(href)
                
                full_url = self.base_url + href if href.startswith('/') else href
                
                # Title: 链接内的 span
                title_elem = await link.query_selector('span')
                if not title_elem:
                    # 尝试直接获取 text
                    title_text = await link.text_content()
                else:
                    title_text = await title_elem.text_content()
                
                if not title_text:
                    continue
                title = title_text.strip()
                
                # Summary: 链接父级的兄弟元素
                # HTML结构:
                # <div>
                #   <a href="...">...</a>
                #   <div class="mt-[4px] ...">摘要内容</div>
                # </div>
                # 所以我们要找 link 的下一个兄弟 div
                summary = ""
                # Playwright 没有直接的 "next_sibling" 选择器，得用 xpath 或者 eval
                # 这里尝试用 evaluate 获取下一个兄弟元素的文本
                summary = await self.page.evaluate("""(element) => {
                    const next = element.nextElementSibling;
                    return next ? next.textContent : "";
                }""", link)
                
                summary = summary.strip()
                
                # 列表页没有准确的时间（只有日期），去详情页拿
                
                # 检查增量抓取
                if self.should_stop_scraping(title, full_url):
                    print(f"  [增量抓取] 停止: {title}")
                    break
                
                # 进入详情页
                details = await self._fetch_article_details(full_url)
                
                if details:
                    published_at = details.get('published_at')
                    author = details.get('author') or 'Odaily'
                    
                    # 用户要求：摘要作为数据内容
                    content = summary
                    
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
            async with self.detail_page(url, load_delay_seconds=2) as page:
                author = "Odaily"
                try:
                    author_elem = await page.query_selector('a[href*="/author/"]')
                    if author_elem:
                        author = (await author_elem.text_content()).strip()
                except Exception:
                    pass

                published_at = None
                try:
                    time_elem = await page.query_selector(
                        'div.flex.flex-col.justify-end.items-end > div'
                    )
                    if time_elem:
                        time_text = await time_elem.text_content()
                        if re.search(r'\d{4}-\d{2}-\d{2}', time_text):
                            published_at = time_text.strip()
                except Exception:
                    pass

                return {'author': author, 'published_at': published_at}
        except Exception as e:
            print(f"    ⚠️ 详情页加载失败: {e}")
            return None
