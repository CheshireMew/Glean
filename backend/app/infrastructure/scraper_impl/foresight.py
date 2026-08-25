"""Foresight News爬虫"""
from .base import BaseScraper
from typing import List, Dict
from datetime import datetime

class ForesightScraper(BaseScraper):
    def __init__(self):
        super().__init__(
            site_name='foresight',
            base_url='https://foresightnews.pro/news'
        )
    
    async def scrape_important_news(self) -> List[Dict]:
        """抓取Foresight News的重要新闻"""
        await self.fetch_page_with_delay(self.base_url)
        await self.page.wait_for_timeout(3000)
        
        # 点击"只看重要"开关
        try:
            important_switch = await self.page.query_selector('text=只看重要')
            if important_switch:
                # 检查是否已开启
                # Foresight的开关可能没有明确的aria-checked，简单起见先强制点击
                await self.page.evaluate("el => el.click()", important_switch)
                await self.page.wait_for_timeout(2000)
        except Exception as e:
            print(f"点击筛选按钮失败: {e}")
        
        collector = self.create_candidate_collector()
        news_list = collector.results
        
        # 先获取当前页面的日期标题（如"12月24日"）
        date_headers = await self.page.query_selector_all('.collapse-title-month')
        current_date_str = None
        if date_headers:
            # 通常第一个就是最新的日期
            current_date_str = await self.safe_extract_text(date_headers[0])
            print(f"[DEBUG] 当前日期区块: {current_date_str}")
        
        # 获取所有新闻标题
        title_elements = await self.page.query_selector_all('.news_body_title')
        print(f"[DEBUG] 找到 {len(title_elements)} 个新闻标题")
        
        for title_el in title_elements:
            try:
                # 检查是否有redcolor类
                class_name = await title_el.get_attribute('class')
                has_red_class = 'redcolor' in class_name if class_name else False
                
                # 样式检查（通用方法）
                style_check = await self.check_importance_by_style(title_el)
                
                # 只要满足任一条件即为重要
                if not (has_red_class or style_check['is_important']):
                    continue
                
                # 提取信息
                title = await self.safe_extract_text(title_el)
                url = await self.safe_get_attribute(title_el, 'href')
                
                if url and not url.startswith('http'):
                    print(f"  [DEBUG] Raw URL: {url}")
                    # Remove /foresightnews prefix if present, then add base URL
                    if url.startswith('/foresightnews/'):
                        # 暂时保留两种策略，打印出来确认
                        # 策略A: 去掉前缀 (当前逻辑)
                        url_stripped = f"https://foresightnews.pro{url[len('/foresightnews'):]}"
                        # 默认使用去掉前缀的，但也可能有变
                        url = url_stripped
                        print(f"  [DEBUG] Processed URL (Stripped): {url}")
                    else:
                        if not url.startswith('/'):
                            url = f"/{url}"
                        url = f"https://foresightnews.pro{url}"
                        print(f"  [DEBUG] Processed URL (Normal): {url}")
                
                # 提取时间：查找最近的时间戳元素
                published_at = None
                try:
                    # 向上找父容器，然后找时间戳
                    time_element = await title_el.evaluate('''
                        el => {
                            // 向上找到包含时间戳的容器
                            let parent = el.closest('.el-timeline-item') || el.closest('div');
                            if (parent) {
                                let timeEl = parent.querySelector('.el-timeline-item__timestamp.is-top');
                                return timeEl ? timeEl.textContent.trim() : '';
                            }
                            return '';
                        }
                    ''')
                    
                    if time_element and current_date_str:
                        # 解析日期和时间，组合成完整的datetime
                        # current_date_str 格式: "12月24日"
                        # time_element 格式: "19:56"
                        import re
                        date_match = re.search(r'(\d+)月(\d+)日', current_date_str)
                        time_match = re.search(r'(\d+):(\d+)', time_element)
                        
                        if date_match and time_match:
                            month = int(date_match.group(1))
                            day = int(date_match.group(2))
                            hour = int(time_match.group(1))
                            minute = int(time_match.group(2))
                            
                            now = datetime.now()
                            
                            # 构造完整的datetime对象（避免使用replace导致的跨年问题）
                            try:
                                published_at = datetime(now.year, month, day, hour, minute, 0)
                            except ValueError:
                                # 日期无效（如2月30日），使用当前时间
                                published_at = now
                            else:
                                # 如果时间在未来（跨年情况），使用去年
                                if published_at > now:
                                    published_at = published_at.replace(year=now.year - 1)
                except Exception as e:
                    print(f"  时间提取失败: {e}")
                
                # 如果时间提取失败，使用当前时间
                if published_at is None:
                    published_at = datetime.now()
                
                # 确定重要标识
                if has_red_class:
                    importance_flag = 'redcolor_class'
                else:
                    importance_flag = style_check['style_flag']
                
                decision = collector.consider(title, url, published_at)
                if decision == "skip":
                    continue
                if decision == "stop":
                    break
                
                # 获取完整内容
                content = ''
                if url:
                    content = await self.fetch_full_content(
                        url,
                        content_selectors=['.detail-body', '.news_body_content', '.article-content'],
                        extract_paragraphs=True
                    )
                
                collector.append_standard(
                    title=title,
                    content=content,
                    url=url,
                    published_at=published_at,
                    site_importance_flag=importance_flag,
                    source_site=self.site_name,
                )
                print(f"[DEBUG] 添加重要新闻: {title[:30]}...")
                
            except Exception as e:
                print(f"解析Foresight新闻项失败: {e}")
                continue
        
        print(f"Foresight News: 抓取到 {len(news_list)} 条重要新闻")
        return news_list
