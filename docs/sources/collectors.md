# Glean 采集来源

采集器的唯一注册表是 [`backend/app/infrastructure/scrapers.py`](../../backend/app/infrastructure/scrapers.py)。运行时还会把后台配置且已启用的 RSS 源合并进同一注册表。

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

以上站点当前都依赖页面交互或动态内容，使用 `browser` 传输。每个采集器只负责站点解析，浏览器启动、关闭和异常清理由共享传输层负责。

### Hacker News

- 运行名称：`hacker_news`，显示在文章采集器中。
- 读取 [Hacker News 官网首页](https://news.ycombinator.com/)，使用共享 `http` 传输，一次请求解析首页，无需 API Key。
- 随 AI 资讯页面自动更新，读取首页最多 30 条，保留官网选择和排行，不额外限定主题或帖子类型；同一来源 5 分钟内复用结果。
- 以 HN 讨论页 URL 标识投稿，保存首页外链、提交者和提交时间。前台“阅读原文”仍直达外链；首页没有正文或摘要，因此留空，不抓文章或评论补写。
- 数据库保存最近一次成功的首页条目和顺序；Hacker News 来源页按此顺序显示，全部来源按时间混排。旧的最新投稿和已离开首页的条目不再混入公开列表，历史数据保留。
- 即使没有新文章也更新首页排序；网络失败或页面无效时保留上次成功列表，不清空页面。

### Lobsters

- 运行名称：`lobsters`，出现在后台文章采集器和前台 AI 资讯来源筛选中。
- 读取用户指定的 [Recent Stories](https://lobste.rs/recent)，使用共享 HTTP 传输，无需账号或 API Key。该页面提供的 RSS 指向 `/newest.rss`，并不等同于 `/recent`，因此直接解析一次列表页面。
- 随 AI 资讯页面自动更新，每次最多收录 20 条新内容，保留列表中的全部技术话题；不依赖旧定时采集总开关，更新遵守同站请求间隔和冷却。
- 保存真实标题、外链、提交者和提交时间，按原文 URL 去重。列表不提供文章摘要，因此正文留空，不抓评论、外链全文或生成导读；英文标题沿用现有 DeepSeek 批量翻译并保存译文。

### 掘金本周最热

- 运行名称：`rss__juejin-weekly`，读取用户指定的[掘金本周最热 RSS](https://rsshub.bestblogs.dev/juejin/trending/all/weekly)，覆盖全站技术内容。
- 使用共享 RSS 采集器，一次获取前 20 条，保存来源实际提供的标题、作者、正文或摘要与发布日期，按周榜顺序展示，不逐篇抓正文。
- 随 AI 页面检查更新，5 分钟内复用结果；每次成功刷新榜单成员和顺序，失败保留上次列表。
- `2026.09.27.5` 迁移添加周榜订阅。原来的掘金 AI 推荐采集器、配置与历史内容完整保留，仅从前台隐藏，也不参与页面自动刷新。两种来源独立保存记录，文章重合时不会互相覆盖。

### 掘金 AI 推荐（前台隐藏）

- 保留 `juejin_ai` 采集器，读取 `https://api.juejin.cn/recommend_api/v1/article/recommend_cate_feed`，使用 AI 分类 `6809637773935378440` 和推荐参数 `sort_type=200`。
- 后台仍可手动采集；前台不展示、不自动触发，历史数据及原有解析逻辑保留。

### WaytoAGI

- 运行名称：`waytoagi`，读取用户指定的[公开飞书文档](https://waytoagi.feishu.cn/wiki/QPe5w5g7UisbEkkow8XcDmOpn8e)。
- 读取公开页返回的内嵌 JSON 文档块，只读取“近 7 日更新日志”区域，不执行远端脚本，不登录，不调用私有接口或逐篇抓全文。
- 还原内嵌文档链接的真实标题和介绍，日期使用日志日期，保留文档中的顺序与实际日期范围；显示的文章链接指向文档提供的原链接。以稳定文档块识别更新，修改已有介绍也会同步。
- 随 AI 页面检查更新，30 分钟缓存，一次最多 100 条；若日志所需文档块不完整或页面结构改变，报错并保留上次成功列表。公开页面结构并非承诺稳定的 API。

## RSS 源

RSS 源通过后台配置维护，不需要新增 Python 类。运行时名称使用 `rss__{slug}`，传输方式为共享异步 HTTP 客户端，支持：

- 超时与有限重试
- HTTP 429 `Retry-After`
- 5xx 退避
- 随机请求间隔
- RSS XML 解析

### 预置 AI 与技术资讯

| 运行名称 | 来源 | 订阅地址 |
| --- | --- | --- |
| `rss__infoq-cn` | InfoQ 中文 | [RSS](https://www.infoq.cn/feed) |
| `rss__huggingface-blog` | Hugging Face Blog | [RSS](https://huggingface.co/blog/feed.xml) |
| `rss__juejin-weekly` | 掘金本周最热 | [RSS](https://rsshub.bestblogs.dev/juejin/trending/all/weekly) |
| `rss__v2ex-tech` | V2EX · 技术 | [官方 Atom](https://www.v2ex.com/feed/tab/tech.xml) |
| `rss__v2ex-main` | V2EX · 首页 | [官方 Atom](https://v2ex.com/index.xml) |
| `rss__hn-chinese-digest` | Hacker News 中文每日摘要 | [RSS](https://www.supertechfans.com/cn/index.xml) |
| `rss__acquired-video` | Acquired | [YouTube Atom](https://www.youtube.com/feeds/videos.xml?channel_id=UCyFqFYfTW2VoIQKylJ04Rtw) |
| `rss__baochipianjian` | 保持偏见 | [RSS](https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/663e3c95af1e22bb157dcee3) |

这些 RSS 来源无需 Key，默认启用，归入文章采集，随 AI 资讯页面自动更新，通常每次最多 20 条，同一来源 5 分钟内复用结果，不使用旧定时调度。V2EX 两个栏目每次最多 30 条、10 分钟内复用结果。可在后台 RSS 管理中编辑或停用。

新数据库自动包含这些来源；已有数据库在启动 API 或执行 `.\glean.ps1 system init` 时通过追加式迁移补齐。迁移保留同标识或同订阅地址的用户配置，不重复创建来源。采集器列表、手动运行和定时调度共用现有注册表。

`2026.10.03.1` 迁移接入本次筛选出的五个入口：V2EX 首页、V2EX 技术板块、Hacker News 中文每日摘要、Acquired 和保持偏见。其中技术板块复用已有配置，其余四个新增。按用户要求停用量子位和钛媒体的现有 RSS 配置，不删除历史内容；量子位同时从前台来源和页面自动刷新中移出，其历史记录不回流到其他公开频道。本轮筛选的原始地址与说明保存在 [RSS 主清单](curated-rss.md)。

RSS 仅保存订阅源实际提供的正文或摘要。InfoQ 的摘要较短，Hugging Face 的部分条目只有标题和链接；它们不应被视为已取得文章全文。增量采集检查本次请求数量内的全部条目，跳过已收录和重复 URL，避免源调整顺序后漏掉新条目。

Hacker News、Lobsters、WaytoAGI 和以上 RSS 来源通过首页频道栏中的“AI 资讯”展示，地址为 `/?channel=ai`，使用原有页面的导航、搜索、列表和明暗主题。页面直接展示采集记录，不需要填写审核摘要或创建日报；没有正文或摘要时只展示已有字段，不添加缺失提示或标题导读。原来的公开文章与日报不混入这些来源。当前前台暂时隐藏快讯、快讯日报、文章日报、精选快讯频道和右侧快讯栏，数据及后台能力保留。

V2EX 使用首页“技术”栏提供的官方 Atom，保留订阅源顺序（可能与网页实时回复排序不同），展示原帖内容，不抓评论。忽略链接中会随回复数变化的 `#replyN`，避免同一帖子重复入库。页面触发更新每 10 分钟复用一次，取前 30 条，数据库保存当前列表和历史记录。`2026.09.27.4` 迁移为已有数据库添加此订阅，保留用户已有配置。Reddit 未接入。

V2EX 首页也保留订阅源列表与顺序；它与技术栏分开保存，同一帖子出现在两栏时不会覆盖彼此的来源、正文或榜单成员，阅读链接仍指向原帖。Acquired 保存 YouTube 订阅源提供的标题、视频链接和介绍，保持偏见保存节目标题、单集链接和节目简介，不抓取音视频或生成转写。Hacker News 中文摘要保存来源实际提供的每日整理内容；原来的 Hacker News 官网采集器继续保留。

## 新增来源

如果来源提供稳定 RSS，优先在后台添加 RSS 源。如果需要固定站点解析器，则继承 `BaseScraper` 或 `ArticleScraper`，显式声明 `transport_kind`，实现来源解析，并在 `scrapers.py` 注册。只有依赖 JavaScript 或页面交互时才选择 `browser`；静态页面、RSS 和 JSON API 应分别使用 `http`、`rss` 或 `api`。

## 微信公众号采集

后台入口：`/admin?tab=wechat`。无需部署额外的 WeRSS 服务，也无需付费 API Key。

使用管理公众号的微信扫码登录（需要有可登录的公众号，未认证也可），搜索目标公众号并添加。每个来源默认每 240 分钟采集最多 10 篇，可配置 30～10080 分钟、1～100 篇，或停用。复用现有 worker、任务队列、定时器与运行日志；自动更新遵循系统自动化开关及工作时段，手动采集也需要 worker 运行。

通过公众平台 `searchbiz`、`appmsgpublish` 网页接口获取名称、标题、原文链接、真实发布时间和接口已有摘要。不会生成导读、伪造摘要，也不会为补齐摘要逐篇访问正文。文章去掉链接中的跟踪参数后去重，保存在现有 `news` 表，来源名为 `公众号：名称`，通过 `wechat__<id>` 在 AI 资讯频道筛选，不混入原来的默认频道。停用来源或断开登录均保留历史文章。

订阅保存在 `wechat_sources`；登录凭据仅保存在本机数据库 `system_config` 的 `integration.wechat.session`，管理 API 不返回 Cookie/token。二维码只保留在内存，登录结束或取消后关闭浏览器。微信要求重新登录时停止请求并提示扫码；遇到限流暂停请求 30 分钟，API 与 worker 共用请求间隔。电脑休眠或退出服务期间不会更新；不承诺全量历史回补。网页接口可能变化，失败会报告错误，不当作空列表成功。
