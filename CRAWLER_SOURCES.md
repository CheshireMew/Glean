# AINews 采集来源

采集器的唯一注册表是 [`backend/app/infrastructure/scrapers.py`](backend/app/infrastructure/scrapers.py)。运行时还会把后台配置且已启用的 RSS 源合并进同一注册表。

## 固定站点采集器

### 快讯

- `techflow`
- `odaily`
- `blockbeats`
- `foresight`
- `chaincatcher`
- `panews`
- `marsbit`

### 文章

- `foresight_exclusive`
- `foresight_express`
- `foresight_depth`
- `blockbeats_article`
- `chaincatcher_article`
- `marsbit_article`
- `odaily_article`
- `panews_article`
- `techflow_article`
- `wublock_article`

这些站点当前都依赖页面交互或动态内容，使用 `browser` 传输。每个采集器只负责站点解析，浏览器启动、关闭和异常清理由共享传输层负责。

## RSS 源

RSS 源通过后台配置维护，不需要新增 Python 类。运行时名称使用 `rss__{slug}`，传输方式为共享异步 HTTP 客户端，支持：

- 超时与有限重试
- HTTP 429 `Retry-After`
- 5xx 退避
- 随机请求间隔
- RSS XML 解析

## 新增来源

如果来源提供稳定 RSS，优先在后台添加 RSS 源。如果需要固定站点解析器，则继承 `BaseScraper` 或 `ArticleScraper`，显式声明 `transport_kind`，实现来源解析，并在 `scrapers.py` 注册。只有依赖 JavaScript 或页面交互时才选择 `browser`；静态页面、RSS 和 JSON API 应分别使用 `http`、`rss` 或 `api`。
