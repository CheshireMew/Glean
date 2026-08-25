"""MarsBit爬虫 - 使用样式判断"""
from .base import BaseScraper
from typing import List, Dict
from datetime import datetime

class MarsBitScraper(BaseScraper):
    def __init__(self):
        super().__init__(
            site_name='marsbit',
            base_url='https://news.marsbit.co/flash'
        )
    
    async def scrape_important_news(self) -> List[Dict]:
        """抓取MarsBit的重要新闻"""
        await self.fetch_page_with_delay(self.base_url)
        await self.page.wait_for_timeout(3000)
        
        # 点击"只要重要快讯"复选框
        try:
            important_checkbox = await self.page.query_selector('.flash-only-important input[type="checkbox"]')
            if important_checkbox:
                # 检查是否已经选中
                is_checked = await important_checkbox.is_checked()
                if not is_checked:
                    await self.page.evaluate("el => el.click()", important_checkbox)
                    await self.page.wait_for_timeout(2000)
                    print("[DEBUG] 已点击'只要重要快讯'筛选")
        except Exception as e:
            print(f"点击筛选按钮失败: {e}")
        
        collector = self.create_candidate_collector()
        news_list = collector.results
        
        # 获取所有带有 "item-icons import" 类的重要新闻容器
        important_items = await self.page.query_selector_all('.item-icons.import')
        print(f"[DEBUG] 找到 {len(important_items)} 个重要新闻")
        
        for item in important_items:
            try:
                # 从容器中找到新闻链接（通常在父元素或相邻元素中）
                container = await item.evaluate_handle('el => el.closest(".flash-item") || el.parentElement')
                if not container:
                    continue
                
                # 在容器中查找链接
                link = await container.query_selector('a[href*="/flash/"]')
                if not link:
                    continue
                
                url = await self.safe_get_attribute(link, 'href')
                if not url or 'flash' not in url:
                    continue
                
                # 提取标题
                title = await self.safe_extract_text(link)
                if not title or len(title) < 10:
                    continue
                
                if url and not url.startswith('http'):
                    url = f"https://news.marsbit.co{url}"
                
                # 从 item-icons import 元素中提取时间
                time_text = ''
                try:
                    time_el = await item.query_selector('.time-left')
                    if time_el:
                        time_text = await self.safe_extract_text(time_el)
                except Exception:
                    pass
                
                published_at = self.parse_relative_time(time_text) if time_text else datetime.now()
                
                decision = collector.consider(title, url, published_at)
                if decision == "skip":
                    continue
                if decision == "stop":
                    break
                
                # 获取完整内容
                content = ''
                if url:
                    # MarsBit的内容选择器
                    content_selectors = [
                        '.content-words',  # MarsBit快讯内容（正确选择器）
                        '.flash-content',
                        '.article-content',
                    ]
                    content = await self.fetch_full_content(url, content_selectors)
                
                collector.append_standard(
                    title=title,
                    content=content,
                    url=url,
                    published_at=published_at,
                    site_importance_flag='import_icon',
                )
                
            except Exception as e:
                print(f"解析 MarsBit 新闻项失败: {e}")
                continue
        
        print(f"MarsBit: 抓取到 {len(news_list)} 条重要新闻")
        return news_list
