"""
BlockBeats 文章爬虫（使用 Playwright）
抓取 BlockBeats 深度文章（非快讯）

特点：
- 双列表结构：热榜 + 普通列表
- 使用 Playwright 支持 JavaScript 渲染
- 智能作者提取：正文关键词优先
- 多段摘要：200-300字
"""

from .article_base import ArticleScraper
from typing import List, Dict
from datetime import datetime
import re


class BlockBeatsArticleScraper(ArticleScraper):
    """BlockBeats 文章爬虫"""
    
    def __init__(self):
        super().__init__('BlockBeats Article', 'https://www.theblockbeats.info', max_items=20)
        # 修改为精选文章页面
        self.article_list_url = 'https://www.theblockbeats.info/article_choice'
        self.base_url = 'https://www.theblockbeats.info'
        self.list_url = self.article_list_url
        self.list_load_delay = 2
        self.list_wait_selector = '.article-item'
        self.list_wait_timeout = 5000

    async def _prepare_list_page(self) -> None:
        await self.page.evaluate('window.scrollTo(0, 500)')
        await self.page.wait_for_timeout(1000)
    
    async def _scrape_list_articles(self) -> List[Dict]:
        """抓取普通列表文章"""
        articles = self.create_result_buffer()
        
        # 查找文章列表项
        article_items = await self.page.query_selector_all('.article-item')
        print(f"找到 {len(article_items)} 篇列表文章")
        
        for item in article_items:
            try:
                # 提取标题和链接
                title_elem = await item.query_selector('.article-item-title')
                if not title_elem:
                    continue
                
                title = await title_elem.text_content()
                title = title.strip()
                href = await title_elem.get_attribute('href')
                
                if not href or not title:
                    continue
                
                # 构建完整URL
                article_url = self.base_url + href if href.startswith('/') else href
                
                # 检查增量抓取
                if self.should_stop_scraping(title, article_url):
                    print("  [增量抓取] 匹配到历史记录，停止抓取")
                    break
                
                # 获取详情
                details = await self._fetch_article_details(article_url)
                if not details:
                    continue
                
                # 增量抓取检查：如果遇到已抓取的文章，停止抓取
                if self.should_stop_scraping(title, article_url, details['published_at']):
                    print("  [增量抓取] 遇到已抓取文章，停止")
                    break
                
                article_item = {
                    'title': title,
                    'url': article_url,
                    'content': details['summary'],
                    'published_at': details['published_at'],
                    'is_marked_important': False,
                    'site_importance_flag': '',
                    'type': self.news_type,
                    'author': details['author']
                }
                
                articles.append(article_item)
                print(f"  ✅ {title[:40]}...")
                
                # 检查数量限制
                if len(articles) >= self.max_items:
                    break
            
            except Exception as e:
                print(f"  解析列表文章失败: {e}")
                continue
        
        return articles
    
    async def _fetch_article_details(self, url: str) -> Dict:
        """
        获取文章详情（作者、时间、摘要）
        在新标签页中打开避免影响列表页
        """
        try:
            async with self.detail_page(url, load_delay_seconds=1) as detail_page:
                published_at = await self._extract_publish_time(detail_page)
                author = await self._extract_author(detail_page)
                summary = await self._extract_summary(detail_page)
                return {
                    'published_at': published_at,
                    'author': author,
                    'summary': summary,
                }
        except Exception as e:
            print(f"    ⚠️ 详情页解析失败: {e}")
            return None
    
    async def _extract_publish_time(self, page) -> str:
        """提取发布时间"""
        try:
            time_elem = await page.query_selector('.news-read-time')
            if time_elem:
                time_text = await time_elem.text_content()
                time_text = time_text.strip()
                # 验证格式: "2025-12-29 17:10"
                datetime.strptime(time_text, '%Y-%m-%d %H:%M')
                return time_text
        except Exception:
            pass
        
        # 默认当前时间
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    async def _extract_author(self, page) -> str:
        """
        智能提取作者
        优先级：blockquote(原文作者/作者) > 正文关键词 > 作者区域 > 默认值
        """
        try:
            # 优先级0: 检查 blockquote (专门处理转载/编译声明)
            # 使用 inner_text() 以保留 <br> 带来的换行，这对于后续正则非常重要
            bq_elem = await page.query_selector('.news-content blockquote')
            content_text = ""
            
            if bq_elem:
                content_text = await bq_elem.inner_text()
                print(f"  [作者提取] 找到blockquote内容: {content_text[:50]}...")
            else:
                # 优先级1: 正文全文
                content_elem = await page.query_selector('.news-content')
                if content_elem:
                    content_text = await content_elem.inner_text()

            if content_text:
                # 搜索关键词（按优先级顺序）
                patterns = [
                    r'原文作者[：:]\s*([^\n\r]+)',      # 原文作者（最高优先级）
                    r'作者[：:]\s*([^\n\r]+)',          # 作者
                    r'原文来源[：:]\s*([^\n\r]+)'       # 原文来源
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, content_text)
                    if match:
                        author = match.group(1).strip()
                        print(f"  [作者提取] 正则匹配到: '{author}' (长度:{len(author)})")
                        
                        # 清理：只取第一行，合并多余空格
                        author = author.split('\n')[0].strip()
                        author = re.sub(r'\s+', ' ', author)
                        
                        # 合理性检查：长度2-50字符
                        if author and 2 <= len(author) <= 50:
                            print(f"  [作者提取] ✓ 最终采用: '{author}'")
                            return author
                        else:
                            print(f"  [作者提取] ✗ 长度不符({len(author)}), 跳过")
        except Exception as e:
            print(f"  [作者提取] 正文提取失败: {e}")
        
        # 优先级2: 作者区域元素
        try:
            author_elem = await page.query_selector('.news-author .author-item span')
            if author_elem:
                author = await author_elem.text_content()
                author = author.strip()
                if author and 2 <= len(author) <= 30:
                    return author
        except Exception:
            pass
        
        # 默认值
        return 'BlockBeats'
    
    async def _extract_summary(self, page, min_chars: int = 200, max_chars: int = 300) -> str:
        """
        提取摘要：多段拼接
        目标：200-300字
        """
        try:
            content_elem = await page.query_selector('.news-content')
            if not content_elem:
                return "BlockBeats 深度文章"
            
            # 获取所有段落
            paragraphs = await content_elem.query_selector_all('p')
            
            summary_parts = []
            total_length = 0
            
            for p in paragraphs:
                text = await p.text_content()
                text = text.strip()
                
                # 跳过太短的段落
                if len(text) < 10:
                    continue
                
                # 跳过特殊标记
                if any(keyword in text for keyword in ['作者：', '原文来源：', '原文作者：', '免责声明', '风险提示']):
                    continue
                
                summary_parts.append(text)
                total_length += len(text)
                
                # 达到字数要求
                if (total_length >= min_chars and len(summary_parts) > 1) or total_length >= max_chars:
                    break
            
            # 拼接并截断
            summary = ''.join(summary_parts)
            
            if len(summary) > max_chars:
                summary = summary[:max_chars] + '...'
            
            return summary if summary else "BlockBeats 深度文章"
        
        except Exception as exc:
            print(f"生成文章摘要失败: {exc}")
            return "BlockBeats 深度文章"
