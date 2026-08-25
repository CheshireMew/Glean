"""
WuBlock123 Article Scraper
Target: https://www.wublock123.com/html/shendu/
"""
from .article_base import ArticleScraper
from typing import List, Dict, Optional
from datetime import datetime

class WuBlockArticleScraper(ArticleScraper):
    """WuBlock123 深度文章爬虫"""
    
    def __init__(self):
        super().__init__('WuBlock Article', 'https://www.wublock123.com', max_items=20)
        self.base_url = 'https://www.wublock123.com'
        self.list_url = 'https://www.wublock123.com/html/shendu/'
        self.list_wait_selector = '.list ul li'
        self.list_wait_timeout = 15000

    async def _scrape_list_articles(self) -> List[Dict]:
        """抓取列表文章"""
        articles = self.create_result_buffer()
        
        # 查找所有文章列表项
        items = await self.page.query_selector_all('.list ul li')
        print(f"找到 {len(items)} 个文章项")
        
        for item in items:
            try:
                # Title & Link
                title_elem = await item.query_selector('.listTit a')
                if not title_elem:
                    continue
                
                heading = await title_elem.text_content()
                heading = heading.strip()
                
                href = await title_elem.get_attribute('href')
                if not href:
                    continue
                    
                # href is usually absolute: https://www.wublock123.com/...
                full_url = href if href.startswith('http') else self.base_url + href
                
                # Date
                date_span = await item.query_selector('span')
                published_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                if date_span:
                    date_str = await date_span.text_content() # "2025-12-31"
                    date_str = date_str.strip()
                    
                    try:
                        # User request: "具体时间点就选择抓取的北京时间即可"
                        # Logic: Use Date from page + Current Time
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                        now = datetime.now()
                        combined_dt = datetime.combine(date_obj.date(), now.time())
                        published_at = combined_dt.strftime('%Y-%m-%d %H:%M:%S')
                    except Exception as e:
                        print(f"  ⚠️ 日期解析失败 ({date_str}): {e}")
                        pass
                
                # Check Incremental
                if self.should_stop_scraping(heading, full_url):
                    print(f"  [增量抓取] 停止: {heading}")
                    break
                
                # Author (Hardcoded)
                author = "吴说发布"
                
                # Content (Empty)
                content = ""
                
                articles.append({
                    'title': heading,
                    'content': content,
                    'url': full_url,
                    'published_at': published_at,
                    'source_site': self.site_name,
                    'author': author,
                    'type': self.news_type
                })
                print(f"  ✅ 抓取成功: {heading} ({published_at})")
                
            except Exception as e:
                print(f"  ⚠️ 处理单条失败: {e}")
                continue
                
        return articles

    async def _fetch_article_details(self, url: str) -> Optional[Dict]:
        """列表页信息足够，内容留空"""
        return None
