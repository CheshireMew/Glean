"""深潮TechFlow爬虫"""
from .base import BaseScraper
from typing import List, Dict
from datetime import datetime

class TechFlowScraper(BaseScraper):
    def __init__(self):
        super().__init__(
            site_name='techflow',
            base_url='https://www.techflowpost.com/newsletter/index.html'
        )
    
    async def scrape_important_news(self) -> List[Dict]:
        """抓取深潮的重要新闻"""
        await self.fetch_page_with_delay(self.base_url)
        
        # 点击"只看精选"
        try:
            # 找到"只看精选"按钮并点击
            filter_btn = await self.page.query_selector('.chose')
            if filter_btn:
                # 检查是否已激活
                class_name = await filter_btn.get_attribute('class')
                if 'crently' not in class_name:
                    await self.page.evaluate("el => el.click()", filter_btn)
                    await self.page.wait_for_timeout(2000)
        except Exception as e:
            print(f"点击筛选按钮失败: {e}")
        
        collector = self.create_candidate_collector()
        news_list = collector.results
        
        # 获取所有新闻项
        dl_elements = await self.page.query_selector_all('dl')
        print(f"[DEBUG] 找到 {len(dl_elements)} 个dl元素")
        
        for dl in dl_elements:
            try:
                # 获取时间（dt元素）
                dt = await dl.query_selector('dt')
                if not dt:
                    continue
                
                time_text = await self.safe_extract_text(dt)
                
                # 获取新闻内容（dd元素）
                dd = await dl.query_selector('dd')
                if not dd:
                    continue
                
                #获取标题链接
                title_link = await dd.query_selector('a.dfont.f18')
                if not title_link:
                    continue
                
                # 检查是否有重要标识
                class_name = await title_link.get_attribute('class')
                has_important_class = 'c002CCC' in class_name
                
                # 检查是否有"首发"图标
                first_pub_icon = await title_link.query_selector('img[src*="first_pub_ico"]')
                has_first_pub = first_pub_icon is not None
                
                # 只有标记为重要的才添加
                if not (has_important_class or has_first_pub):
                    continue
                
                title = await self.safe_extract_text(title_link)
                url = await self.safe_get_attribute(title_link, 'href')
                
                # 补全URL
                if url and not url.startswith('http'):
                    url = f"https://www.techflowpost.com{url}"
                
                # 解析时间
                published_at = self.parse_relative_time(time_text) if time_text else datetime.now()

                decision = collector.consider(title, url, published_at)
                if decision == "skip":
                    continue
                if decision == "stop":
                    break
                
                # 获取快讯摘要作为fallback
                content_div = await dd.query_selector('.f12.line18')
                summary = await self.safe_extract_text(content_div) if content_div else ""
                

                
                # 访问详情页获取完整内容（使用正确的选择器）
                full_content = await self.fetch_full_content(
                    url, 
                    content_selectors=['.art_detail_content']  # TechFlow特定选择器
                ) if url else ""
                
                collector.append_standard(
                    title=title,
                    content=full_content,
                    fallback_content=summary,
                    min_content_length=50,
                    url=url,
                    published_at=published_at,
                    site_importance_flag=(
                        'c002CCC' if has_important_class else 'first_pub'
                    ),
                )
                print(f"[DEBUG] 添加重要新闻: {title[:30]}...")
                
            except Exception as e:
                print(f"[DEBUG] 解析新闻项失败: {e}")
                continue
        
        print(f"深潮TechFlow: 抓取到 {len(news_list)} 条重要新闻")
        return news_list
