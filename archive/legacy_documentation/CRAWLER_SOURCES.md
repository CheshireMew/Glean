# AINEWS 已配置爬虫平台列表

## 快讯类爬虫 (News)

### 1. BlockBeats (律动)
- **URL**: https://www.theblockbeats.info/newsflash
- **文件**: `backend/app/infrastructure/scraper_impl/blockbeats.py`
- **重要标识**: `first` 徽章/样式检查
- **内容选择器**: `.flash-content`
- **特点**: 使用样式检查判断重要性

### 2. ChainCatcher (链捕手)
- **URL**: https://www.chaincatcher.com/news
- **文件**: `backend/app/infrastructure/scraper_impl/chaincatcher.py`
- **重要标识**: `selectedClass` 类（红色高亮）
- **内容选择器**: `.rich_text_content`
- **特点**: 支持"只看精选"筛选

### 3. Foresight News (预见未来)
- **URL**: https://foresightnews.pro/news
- **文件**: `backend/app/infrastructure/scraper_impl/foresight.py`
- **重要标识**: `redcolor` 类/样式检查
- **内容选择器**: `.detail-body`
- **特点**: 支持"只看重要"筛选

### 4. MarsBit (火星财经)
- **URL**: https://news.marsbit.co/flash
- **文件**: `backend/app/infrastructure/scraper_impl/marsbit.py`
- **重要标识**: `.item-icons.import` 类
- **内容选择器**: `.content-words`
- **特点**: 使用复选框筛选重要快讯

### 5. Odaily (星球日报)
- **URL**: https://www.odaily.news/zh-CN/newsflash
- **文件**: `backend/app/infrastructure/scraper_impl/odaily.py`
- **重要标识**: 火焰图标 (`hot_icon`)
- **内容选择器**: `#newsflash-content`
- **特点**: 使用 `#import_checkbox` 筛选

### 6. PANews (PANews)
- **URL**: https://www.panewslab.com/zh/newsflash
- **文件**: `backend/app/infrastructure/scraper_impl/panews.py`
- **重要标识**: "首发"标记
- **内容选择器**: `article.prose`
- **特点**: 支持"只看重要/首发"筛选

### 7. TechFlow (深潮)
- **URL**: https://www.techflowpost.com/newsletter/index.html
- **文件**: `backend/app/infrastructure/scraper_impl/techflow.py`
- **重要标识**: `c002CCC` 类/`first_pub` 图标
- **内容选择器`: `.art_detail_content`
- **特点**: 蓝色文字标识重要性

---

## 深度文章类爬虫 (Article)

### 8. MarsBit Article (火星财经 - 深度)
- **URL**: https://news.marsbit.cc/feature
- **文件**: `backend/app/infrastructure/scraper_impl/marsbit_article.py`
- **数据类型**: `article`
- **内容选择器**: `.detail-content`
- **特点**: 抓取时事/专栏类深度文章

---

## 统计总结

| 类型 | 数量 | 说明 |
|------|------|------|
| **快讯爬虫** | 7 个 | BlockBeats, ChainCatcher, Foresight, MarsBit, Odaily, PANews, TechFlow |
| **文章爬虫** | 1 个 | MarsBit Article |
| **总计** | 8 个 | 覆盖主流中文 Web3 资讯平台 |

---

## 技术特点

### 通用特性
- 每个来源显式声明 `rss/http/api/browser` 传输方式
- RSS 使用共享异步 HTTP 传输，支持 429 `Retry-After`、5xx 退避和超时重试
- 只有依赖 JavaScript 与站内交互的来源才使用 Playwright
- 支持增量抓取（避免重复）
- 智能时间解析（相对时间转绝对时间）
- 内容清理和事件聚合
- 样式/徽章/图标等多种重要性判断方法

### 内容筛选机制
1. **徽章/图标**: Odaily火焰图标, MarsBit import图标
2. **CSS类名**: ChainCatcher selectedClass, Foresight redcolor
3. **文字标记**: PANews "首发", TechFlow "首发"
4. **颜色样式**: TechFlow蓝色 (c002CCC)

### 增量抓取
- 记录最后一次抓取的新闻
- 遇到已抓取的新闻时停止
- 避免浪费资源和重复数据

---

## 使用建议

### 已有爬虫优化
如需添加新特性，可以参考：
- `base.py`: 基类包含通用方法
- `article_base.py`: 文章类爬虫基类

### 添加新平台
参考现有爬虫结构，主要需要：
1. 继承 `BaseScraper` 或 `ArticleScraper`
2. 实现 `scrape_important_news()` 方法
3. 确定重要性判断逻辑
4. 配置内容选择器
5. 处理时间解析
