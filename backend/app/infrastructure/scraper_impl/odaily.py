"""Odaily星球日报爬虫"""
from .base import BaseScraper
from typing import List, Dict
from datetime import datetime

class OdailyScraper(BaseScraper):
    def __init__(self):
        super().__init__(
            site_name='odaily',
            base_url='https://www.odaily.news/zh-CN/newsflash'
        )
    
    async def scrape_important_news(self) -> List[Dict]:
        """抓取Odaily的重要新闻（火焰图标标记）"""
        await self.fetch_page_with_delay(self.base_url)
        await self.page.wait_for_timeout(3000)
        
        # 1. 点击"重要快讯"筛选按钮
        try:
            # 根据用户提供的ID查找按钮
            important_btn = await self.page.query_selector('#import_checkbox')
            if important_btn:
                # 检查 `aria-checked` 属性
                is_checked = await important_btn.get_attribute('aria-checked')
                if is_checked != 'true':
                    await self.page.evaluate("el => el.click()", important_btn)
                    await self.page.wait_for_timeout(2000)
                    print("[DEBUG] 已点击'重要快讯'筛选")
            else:
                print("[DEBUG] 未找到'重要快讯'筛选按钮，尝试文本匹配")
                # 备用方案
                btn = await self.page.query_selector('text=重要快讯')
                if btn:
                    await self.page.evaluate("el => el.click()", btn)
                    await self.page.wait_for_timeout(2000)
        except Exception as e:
            print(f"点击筛选按钮失败: {e}")
        
        collector = self.create_candidate_collector()
        news_list = collector.results
        
        # 2. 遍历新闻条目
        # 用户提供的结构：div.newsflash-item -> div.data-list
        items = await self.page.query_selector_all('.newsflash-item .data-list')
        print(f"[DEBUG] 找到 {len(items)} 个新闻条目")
        
        for item in items:
            try:
                # 3. 检查是否有火焰图标（重要标记）
                has_hot_icon = await item.evaluate('''
                    el => {
                        const img = el.querySelector('img[src*="hot"]');
                        return img !== null;
                    }
                ''')
                
                # 如果开启了筛选，理论上所有显示的都是重要的，但再次检查更保险
                # 如果没有筛选成功，这步过滤就很重要
                if not has_hot_icon:
                    continue
                
                # 4. 提取链接和标题
                link_el = await item.query_selector('a[href*="/newsflash/"]')
                if not link_el:
                    continue
                    
                url = await self.safe_get_attribute(link_el, 'href')
                if not url:
                    continue
                    
                if not url.startswith('http'):
                    url = f"https://www.odaily.news{url}"
                
                title = await self.safe_extract_text(link_el)
                if not title:
                    continue
                
                # 5. 提取时间
                # 时间在一个包含 "13:22" 这种格式的 span 里，通常是第一个 span
                time_text = await item.evaluate(r'''
                    el => {
                        const timeSpan = el.querySelector('.text-14'); // 基于提供的class片段
                        if (timeSpan) return timeSpan.textContent;
                        
                        // 备用：找任何类似时间的文本
                        const spans = el.querySelectorAll('span');
                        for (const span of spans) {
                            if (/^\d{2}:\d{2}$/.test(span.textContent.trim())) {
                                return span.textContent;
                            }
                        }
                        return '';
                    }
                ''')
                
                published_at = self.parse_relative_time(time_text) if time_text else datetime.now()
                
                decision = collector.consider(title, url, published_at)
                if decision == "skip":
                    continue
                if decision == "stop":
                    break
                
                # 8. 获取完整内容
                content = ''
                if url:
                    content_selectors = [
                        '#newsflash-content', 
                        '.newsflash-text', 
                        '.description', 
                        'div[class*="content"]'
                    ]
                    content = await self.fetch_full_content(url, content_selectors)
                
                collector.append_standard(
                    title=title,
                    content=content,
                    url=url,
                    published_at=published_at,
                    site_importance_flag='hot_icon',
                )
                print(f"[DEBUG] 添加重要新闻: {title[:20]}...")
                
            except Exception as e:
                print(f"解析Odaily新闻项失败: {e}")
                continue
        
        print(f"Odaily: 抓取到 {len(news_list)} 条重要新闻")
        return news_list
