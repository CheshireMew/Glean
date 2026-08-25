"""
Techflow 文章爬虫
Target: https://www.techflowpost.com/zh-CN/article
"""
from .article_base import ArticleScraper
from typing import List, Dict, Optional
import re
from datetime import datetime, timedelta

class TechflowArticleScraper(ArticleScraper):
    """Techflow 深度文章爬虫"""
    
    def __init__(self):
        super().__init__('Techflow Article', 'https://www.techflowpost.com', max_items=20)
        self.base_url = 'https://www.techflowpost.com'
        self.list_url = 'https://www.techflowpost.com/zh-CN/article'
        self.list_wait_selector = 'a[href^="/zh-CN/article/"]'
        self.list_wait_timeout = 15000

    async def _scrape_list_articles(self) -> List[Dict]:
        """抓取列表文章"""
        articles = self.create_result_buffer()
        
        # 查找所有文章链接容器
        # user snippet: <a class="group flex ..." href="/zh-CN/article/29751">
        items = await self.page.query_selector_all('a[href^="/zh-CN/article/"].group')
        print(f"找到 {len(items)} 个文章项")
        
        for item in items:
            try:
                # Link
                href = await item.get_attribute('href')
                if not href:
                    continue
                full_url = self.base_url + href if href.startswith('/') else href
                
                # Title: h3
                title_elem = await item.query_selector('h3')
                if not title_elem:
                    continue
                title = await title_elem.text_content()
                title = title.strip()
                
                # Summary: p
                summary = ""
                p_elem = await item.query_selector('p')
                if p_elem:
                    summary = await p_elem.text_content()
                    summary = summary.strip()
                
                # Time Parsing
                # Structure:
                # <div class="inline-flex items-center gap-1">
                #   <span class="text-gray-4 ...">2025.12.31</span>
                #   <span class="text-gray-6 ...">- 6分钟前</span>
                # </div>
                published_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                date_elem = await item.query_selector('.text-gray-4.text-\\[14px\\]')
                relative_elem = await item.query_selector('.text-gray-6.text-\\[12px\\]')
                
                date_str = ""
                relative_str = ""
                
                if date_elem:
                    date_str = await date_elem.text_content() # "2025.12.31"
                    date_str = date_str.strip()
                
                if relative_elem:
                    relative_str = await relative_elem.text_content() # "- 6分钟前" or "-昨天"
                    relative_str = relative_str.replace('-', '').replace(' ', '').strip()
                
                if date_str:
                    # Parse date part first
                    # "2025.12.31"
                    try:
                        date_obj = datetime.strptime(date_str, '%Y.%m.%d')
                        
                        # Logic based on user request:
                        # 1. If relative_str has "分钟前/小时前", calculate exact time
                        # 2. If relative_str has "昨天", use date_obj + current time
                        
                        now = datetime.now()
                        
                        if '分钟前' in relative_str:
                            minutes = int(re.search(r'(\d+)分钟前', relative_str).group(1))
                            time_part = (now - timedelta(minutes=minutes)).time()
                            # Combine date_obj with calculated time
                            combined_dt = datetime.combine(date_obj.date(), time_part)
                            published_at = combined_dt.strftime('%Y-%m-%d %H:%M:%S')
                            
                        elif '小时前' in relative_str:
                            hours = int(re.search(r'(\d+)小时前', relative_str).group(1))
                            time_part = (now - timedelta(hours=hours)).time()
                            # Combine date_obj with calculated time
                            combined_dt = datetime.combine(date_obj.date(), time_part)
                            published_at = combined_dt.strftime('%Y-%m-%d %H:%M:%S')
                            
                        else:
                            # "昨天" or just date, or unknown relative
                            # User said: "时间就直接用现在的北京时间" (combined with date)
                            combined_dt = datetime.combine(date_obj.date(), now.time())
                            published_at = combined_dt.strftime('%Y-%m-%d %H:%M:%S')
                            
                    except Exception as e:
                        print(f"  ⚠️ 时间解析失败 ({date_str}, {relative_str}): {e}")
                        pass

                # Check Incremental
                if self.should_stop_scraping(title, full_url):
                    print(f"  [增量抓取] 停止: {title}")
                    break

                # Author (Hardcoded)
                author = "Techflow 发布"
                
                # Content (Use Summary)
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
                print(f"  ✅ 抓取成功: {title} ({published_at})")
                
            except Exception as e:
                print(f"  ⚠️ 处理单条失败: {e}")
                continue
                
        return articles

    async def _fetch_article_details(self, url: str) -> Optional[Dict]:
        """列表页信息足够"""
        return None
