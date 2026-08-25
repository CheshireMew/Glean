"""ChainCatcher爬虫 - 使用样式判断"""
from .base import BaseScraper
from typing import List, Dict
from datetime import datetime

class ChainCatcherScraper(BaseScraper):
    def __init__(self):
        super().__init__(
            site_name='chaincatcher',
            base_url='https://www.chaincatcher.com/news'
        )
    
    async def scrape_important_news(self) -> List[Dict]:
        """抓取ChainCatcher的重要新闻"""
        await self.fetch_page_with_delay(self.base_url)
        await self.page.wait_for_timeout(3000)
        
        # 1. 点击"只看精选"开关
        try:
            # 查找 label "只看精选" 并点击其关联的 input 或直接点击 label
            # 用户提供的HTML: <label ...>只看精选</label>
            filter_label = await self.page.query_selector('label:text("只看精选")')
            if filter_label:
                # 检查 input 状态
                # input ID 通常在 label 的 for 属性中，或者在 label 旁边
                input_id = await filter_label.get_attribute('for')
                if input_id:
                    input_el = await self.page.query_selector(f'#{input_id}')
                    if input_el:
                        is_checked = await input_el.get_attribute('aria-checked')
                        if is_checked != 'true':
                            # 点击 label 或 input wrapper
                            await self.page.evaluate("el => el.click()", filter_label)
                            await self.page.wait_for_timeout(2000)
                            print("[DEBUG] 已点击'只看精选'筛选")
            else:
                 # 备用方案：直接找 text
                 element = await self.page.query_selector('text=只看精选')
                 if element:
                     await self.page.evaluate("el => el.click()", element)
                     await self.page.wait_for_timeout(2000)
                     
        except Exception as e:
            print(f"点击筛选按钮失败: {e}")
        
        collector = self.create_candidate_collector()
        news_list = collector.results
        
        # 2. 获取所有新闻项
        # 遍历所有可能的文章容器，查找包含 selectedClass 的
        # 通常文章列表是一个个 item
        items = await self.page.query_selector_all('.article-item, .news-item, .item') 
        if not items:
             # 如果没有特定的 class，尝试更通用的选择器
             items = await self.page.query_selector_all('div[class*="item"], div[class*="list"]')
             
        # 如果还是找不到，尝试直接找带有 selectedClass 的元素，然后向上找容器
        if not items:
            important_spans = await self.page.query_selector_all('.selectedClass')
            # 这里的逻辑稍微不同：我们直接从重要标记反推
            items = []
            for span in important_spans:
                # 向上找容器
                container = await span.evaluate_handle('el => el.closest("div[class*=\'item\']") || el.closest("a") || el.parentElement')
                if container:
                    items.append(container)

        print(f"[DEBUG] 找到 {len(items)} 个潜在新闻条目")
        
        for item in items:
            try:
                # 3. 检查是否有重要标记 (class="text selectedClass")
                # 这是一个 span，内容是标题
                title_el = await item.query_selector('.selectedClass')
                
                # 如果开启了"只看精选"，理论上列表里的都是精选，但我们需要确认
                # 如果没有 title_el (即没有红色高亮/精选标记)，可能不是重要新闻
                if not title_el:
                     # 再次检查：也许 item 本身就是那个 link
                     is_selected = await item.evaluate('el => el.classList.contains("selectedClass") || el.querySelector(".selectedClass")')
                     if not is_selected:
                         continue
                     if await item.evaluate('el => el.classList.contains("selectedClass")'):
                         title_el = item
                
                # 提取标题
                title = await self.safe_extract_text(title_el)
                if not title:
                    # 尝试从 item 中找其他标题元素
                    title = await self.safe_extract_text(item)
                    
                if not title or len(title) < 5:
                    continue
                    
                # 4. 提取链接
                # 链接可能在 item 本身 (是 a 标签) 或者在其内部
                link_el = item
                tag_name = await item.evaluate('el => el.tagName')
                if tag_name != 'A':
                    link_el = await item.query_selector('a')
                
                if not link_el:
                    # 尝试从 title_el 向上找 a 标签
                    link_el = await title_el.evaluate_handle('el => el.closest("a")')
                    
                if not link_el:
                    continue
                    
                url = await self.safe_get_attribute(link_el, 'href')
                if not url:
                    continue
                    
                if not url.startswith('http'):
                    url = f"https://www.chaincatcher.com{url}"
                
                # 5. 提取时间 - ChainCatcher有完整的timeattr属性（例如："2025-12-26 18:35:38"）
                time_str = await item.evaluate('''
                    el => {
                        // 优先使用 timeattr 属性（完整时间戳）
                        const timeEl = el.querySelector('[timeattr]');
                        if (timeEl) {
                            return timeEl.getAttribute('timeattr');
                        }
                        // 降级：查找时间文本
                        const textEl = el.querySelector('.time') || el.querySelector('.date') || el.querySelector('.dateTime');
                        return textEl ? textEl.textContent : '';
                    }
                ''')
                
                # 解析时间
                if time_str and len(time_str) > 10:  # 完整时间戳格式
                    try:
                        published_at = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
                    except Exception:
                        published_at = self.parse_relative_time(time_str)
                else:
                    published_at = self.parse_relative_time(time_str) if time_str else datetime.now()
                
                decision = collector.consider(title, url, published_at)
                if decision == "skip":
                    continue
                if decision == "stop":
                    break
                
                # 8. 获取完整内容
                content = ''
                if url:
                    # 使用用户提供的选择器 .rich_text_content
                    content_selectors = ['.rich_text_content', '.article-content']
                    content = await self.fetch_full_content(url, content_selectors)
                
                collector.append_standard(
                    title=title,
                    content=content,
                    url=url,
                    published_at=published_at.strftime('%Y-%m-%d %H:%M:%S'),
                    site_importance_flag='selected_class',
                )
                print(f"[DEBUG] 添加重要新闻: {title[:20]}...")
                
            except Exception as e:
                print(f"解析ChainCatcher新闻项失败: {e}")
                continue
        
        print(f"ChainCatcher: 抓取到 {len(news_list)} 条重要新闻")
        return news_list
