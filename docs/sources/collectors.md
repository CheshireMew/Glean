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

2026-10-05 更新了加密媒体的固定采集入口。运行名称、数据库来源名、快讯／文章类型以及已有数量、频率配置保持原值，不需要迁移或删除历史记录。固定入口仍由原注册表、worker、手动命令和调度器运行，不额外创建一套 `rss__` 来源。

| 媒体 | 快讯入口 | 文章入口 | 筛选与内容 |
| --- | --- | --- | --- |
| 深潮 | 官方 RSS | 官方 RSS | 快讯用 `type=newsflash&tag=featured`；文章用 `type=article&tag=all`，主题维持 `topic=all`，语言为中文 |
| Odaily | 官方开放 API | 官方开放 API | 本地检查实际 `isImportant=true`，接口参数本身会混入普通快讯；分页读取，保存实际正文及作者名 |
| 链捕手 | 官网 JSON 接口 | 官方 `/rss/clist` | 快讯按与旧网页精选样式对应的 `newsFlashType=2` 过滤；文章按 RSS `category=文章` 过滤，不能用 `/article/` 路径区分快讯 |
| PANews | 官方 RSS | 官方 RSS | 经用户确认，快讯从旧“首发”规则改为官方精选 `featured=true`；文章保留深度 `in-depth=true` |
| 火星财经 | 官网 JSON 接口 | 官网 JSON 接口 | 快讯检查 `tag=2`，与网页重要图标对应；文章仅保存接口已有 `synopsis`，其中 `【GPT】` 标记原样保留，不称为全文 |
| 吴说 | 无原快讯入口 | 官方 RSS | 只收录 `category=深度` 且链接属于 `/articles/` 的条目；快讯、周报等不混进原深度栏目 |
| 律动 | 有 Key 用新版 API；无 Key 用普通 HTTP | 有 Key 用新版 API；无 Key 用普通 HTTP | 快讯保留重要或首发筛选；文章保留精选栏目，无 Key 时直接读取官网公开页面中的实际正文、日期和标记 |
| Foresight | 原浏览器入口 | 原浏览器入口 | 当前网络仍被上游拦截，RSSHub 也未验证可用；保留为待处理来源，不报告采集恢复 |

RSS 检查订阅中全部条目后再跳过已知 URL，避免已知内容置顶或排序变化导致漏掉后面的新条目。API 每页最多 50 条，最多检查 10 页，一整页都是已知内容时仍会继续检查后续页，结果仍遵守原来源配置的采集数量。它们是近期更新采集，不承诺全量历史回补。旧深潮语言路径、律动手机版与电脑版链接按同一内容比较，已有记录不会因为这两种链接变化而重复收录。正文或摘要为空时保留空值，不用标题补造正文；纯文本字段保留 `<GO>` 等原文，只有 HTML 字段去除标签。格式变化、业务失败或缺少必要标记会报告错误，按栏目筛选的 RSS 缺少分类字段时也不会当作无更新。

2026-10-06 补查后，律动快讯也支持无 Key 运行：普通 HTTP 读取 [官网快讯页](https://www.theblockbeats.info/newsflash)，根据页面重要样式（官网模板对应 `ios > 0`）和首发图标（`is_first=1`）筛选，日期按各个日期区块与条目时间组合，保存页面已有正文。仅检查首屏实际提供的近期列表，当前约 10 条；会继续检查首屏内已知条目后的新内容，但不承诺分页或历史回补。无 Key 时快讯与文章均可手动运行或参与原定时调度，不需要启动浏览器。通过实际 worker 在隔离数据库中验证，两次运行分别保存 5 条和 4 条，共 9 个不同 URL，自动化总开关未启用。

如需新版 API，可在 [官网 API 文档](https://www.theblockbeats.info/apiDoc)申请 Key。把 `BLOCKBEATS_API_KEY` 填入项目实际使用的 `.env.development`（生产为 `.env.production`），或同名系统环境变量，然后重启 API 与 worker。Key 通过请求头传递，不放进 URL 或采集日志。有 Key 后使用 `/v1/newsflash/important`、`/v1/newsflash/first`、`/v1/article/important`；已经选用 API 的进程若失去 Key，会显示“待配置”并拒绝提交任务。授权响应已按官方示例做测试，本机尚未完成真实 Key 的授权联网验证。旧公开 RSS 和旧开放 API 此次实测仍只返回空数组；Foresight 网页返回 567，API 与 RSSHub 公共实例返回 403 或超时，未接入这些不可用入口。

可用原命令手动验证，例如 `.\glean.ps1 scraper run techflow --items 5 --wait --timeout 600`。需要 worker 就绪；定时采集仍遵守原自动化总开关，本次改动不自动启用调度。

剩余浏览器来源继续使用共享传输层。预取请求在发出前取消，不占内容请求的等待队列；关闭详情页或浏览器时取消未完成的请求，正常关闭不再误记成网站冷却。真实网站拦截、限流和网络错误仍保留原有处理。

2026-10-06 修正了采集去重：固定媒体使用与入库相同的文章身份规则，只合并已确认的链接别名，并移除已知追踪参数；文章 ID、语言、有效片段和非默认端口保留。`news_source_identities` 持久记录文章身份，因此最近 2000 条历史 URL 只是采集预检缓存，缓存之外的新旧链接也不能重复入库。`2026.10.06.1` 迁移保留全部历史新闻、原始链接和引用；历史别名若已经重复，会保留原记录并阻止后续重复写入。浏览器列表遇到已知 URL 时继续检查后续条目，不再因连续三条旧内容提前停止；相同标题的新 URL 也不会被标题比较直接跳过。

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
| `rss__baochipianjian` | 保持偏见 | [RSS](https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/663e3c95af1e22bb157dcee3) |

这些 RSS 来源无需 Key，默认启用，归入文章采集，随 AI 资讯页面自动更新，通常每次最多 20 条，同一来源 5 分钟内复用结果，不使用旧定时调度。V2EX 两个栏目每次最多 30 条、10 分钟内复用结果。可在后台 RSS 管理中编辑或停用。

新数据库自动包含这些来源；已有数据库在启动 API 或执行 `.\glean.ps1 system init` 时通过追加式迁移补齐。迁移保留同标识或同订阅地址的用户配置，不重复创建来源。采集器列表、手动运行和定时调度共用现有注册表。

`2026.10.03.1` 迁移接入本次筛选出的五个入口：V2EX 首页、V2EX 技术板块、Hacker News 中文每日摘要、Acquired 和保持偏见。其中技术板块复用已有配置，其余四个新增。按用户要求停用量子位和钛媒体的现有 RSS 配置，不删除历史内容；量子位同时从前台来源和页面自动刷新中移出，其历史记录不回流到其他公开频道。本轮筛选的原始地址与说明保存在 [RSS 主清单](curated-rss.md)。

2026-10-04 按用户要求移除 Acquired：不再预置订阅，不出现在 AI 资讯来源栏，也不参与页面自动更新。旧记录继续保留原来源分类，不回流到其他公开频道。

RSS 仅保存订阅源实际提供的正文或摘要。InfoQ 的摘要较短，Hugging Face 的部分条目只有标题和链接；它们不应被视为已取得文章全文。增量采集检查本次请求数量内的全部条目，跳过已收录和重复 URL，避免源调整顺序后漏掉新条目。

Hacker News、Lobsters、WaytoAGI 和以上 RSS 来源通过首页频道栏中的“AI 资讯”展示，地址为 `/?channel=ai`，使用原有页面的导航、搜索、列表和明暗主题。页面直接展示采集记录，不需要填写审核摘要或创建日报；没有正文或摘要时只展示已有字段，不添加缺失提示或标题导读。原来的公开文章与日报不混入这些来源。当前前台暂时隐藏快讯、快讯日报、文章日报、精选快讯频道和右侧快讯栏，数据及后台能力保留。

V2EX 使用首页“技术”栏提供的官方 Atom，保留订阅源顺序（可能与网页实时回复排序不同），展示原帖内容，不抓评论。忽略链接中会随回复数变化的 `#replyN`，避免同一帖子重复入库。worker 按管理员设置的频率采集，默认取前 30 条，数据库保存当前列表和历史记录。公开页面轮询更新状态；自动采集需开启自动化总开关，来源设为“仅手动”时不会定时采集。`2026.09.27.4` 迁移为已有数据库添加此订阅，保留用户已有配置。Reddit 未接入。

V2EX 首页也保留订阅源列表与顺序；它与技术栏分开保存，同一帖子出现在两栏时不会覆盖彼此的来源、正文或榜单成员，阅读链接仍指向原帖。保持偏见保存节目标题、单集链接和节目简介，不抓取音视频或生成转写。Hacker News 中文摘要保存来源实际提供的每日整理内容；原来的 Hacker News 官网采集器继续保留。

## 新增来源

如果来源提供稳定 RSS，优先在后台添加 RSS 源。如果需要固定站点解析器，则继承 `BaseScraper` 或 `ArticleScraper`，显式声明 `transport_kind`，实现来源解析，并在 `scrapers.py` 注册。只有依赖 JavaScript 或页面交互时才选择 `browser`；静态页面、RSS 和 JSON API 应分别使用 `http`、`rss` 或 `api`。

## 微信公众号采集

后台入口：`/admin?tab=wechat`。无需部署额外的 WeRSS 服务，也无需付费 API Key。

使用管理公众号的微信扫码登录（需要有可登录的公众号，未认证也可），搜索目标公众号并添加。每个来源默认每 240 分钟采集最多 10 篇，可配置 30～10080 分钟、1～100 篇，或停用。复用现有 worker、任务队列、定时器与运行日志；自动更新遵循系统自动化开关及工作时段，手动采集也需要 worker 运行。

通过公众平台 `searchbiz`、`appmsgpublish` 网页接口获取名称、标题、原文链接、真实发布时间和接口已有摘要。不会生成导读、伪造摘要，也不会为补齐摘要逐篇访问正文。文章去掉链接中的跟踪参数后去重，保存在现有 `news` 表，来源名为 `公众号：名称`，通过 `wechat__<id>` 在 AI 资讯频道筛选，不混入原来的默认频道。停用来源或断开登录均保留历史文章。

订阅保存在 `wechat_sources`；登录凭据仅保存在本机数据库 `system_config` 的 `integration.wechat.session`，管理 API 不返回 Cookie/token。二维码只保留在内存，登录结束或取消后关闭浏览器。微信要求重新登录时停止请求并提示扫码；遇到限流暂停请求 30 分钟，API 与 worker 共用请求间隔。电脑休眠或退出服务期间不会更新；不承诺全量历史回补。网页接口可能变化，失败会报告错误，不当作空列表成功。
