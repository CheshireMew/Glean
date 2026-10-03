# Glean

[GitHub](https://github.com/CheshireMew/Glean) · 原名 AINEWS。

基于 FastAPI、React 和 SQLite 的信息筛选、事件追踪与发布系统，当前内置来源以加密行业为主。系统负责采集多来源内容，将不同报道聚合为可追溯事件，经过黑名单、分档案 AI 审核、人工编辑和引用受限的内容补充后，编排为独立发布频道，并投递到 Telegram、邮件、Discord、Slack、Webhook、公开前台和 RSS。

当前源码版本以根目录 [`VERSION`](VERSION) 为唯一来源。后端健康接口、前端 `index.html` 的 `glean-version` 元数据和 `dist/release-manifest.json` 必须显示同一版本；环境变量 `APP_VERSION` 只用于明确覆盖，不能再用 `unreleased` 启动生产环境。

## 当前架构

运行时只保留一套内容 contract：

- `incoming`: 采集池
- `archive`: 归档池
- `blocked`: 已拦截
- `review`: 待审核
- `selected`: 已选入
- `discarded`: 已舍弃

后端唯一应用根是 [`backend/app`](backend/app)，当前数据库结构由 [`sqlite_schema.py`](backend/app/infrastructure/sqlite/sqlite_schema.py) 定义，版本升级顺序由 [`sqlite_migration_plan.py`](backend/app/infrastructure/sqlite/sqlite_migration_plan.py) 的追加式注册表定义。

## 主要能力

- 多站点新闻与文章采集，按来源选择 RSS/HTTP 或浏览器传输
- 微信公众号采集：后台“公众号采集”中扫码登录、搜索订阅、定时或手动采集；标题和来源已有摘要入库后显示在 AI 资讯频道
- 跨来源事件聚合，区分一手、独立报道、转载和评论，保留证据关系、核验状态、结构化关键事实、关联事件与事件时间线
- 归档池黑名单拦截与批量恢复
- 内容档案、AI 端点故障切换、并发审核、入选后二次补充，以及调用成功率、耗时、Token、费用、人工反馈和固定样例评测
- 可恢复的人工编辑、AI 原稿差异、修订历史、版本回滚、最终成稿预览、发布草稿、排期、更正、澄清和撤回
- 每个内容档案对应独立发布频道，可配置频率、模板、公开路径、RSS 和多个实时/摘要投递目标
- 实体、叙事、自动关键词识别、90 天叙事趋势、关注列表和提醒规则，支持即时、每日与每周投递及静默时段
- 官方监管、交易所、项目与治理 RSS，一手来源标记、采集健康快照、解析漂移识别和异常处理
- 事件关联行情品种、事前影响判断、T-1h 至 T+7d 价格窗口和实际影响评估
- 公开频道内容流、日报、搜索、事件、实体和叙事页面
- 面向外部研究工具的 API Key、事件/实体/叙事/标签读取、轮询增量和可靠 Webhook 变更订阅，以及完整的本机 Agent CLI

## 目录概览

```text
Glean/
├── backend/
│   ├── main.py
│   ├── worker.py
│   ├── tests/
│   └── app/
│       ├── core/
│       ├── infrastructure/
│       ├── routers/
│       └── services/
├── frontend/
│   └── src/
│       ├── api/
│       ├── components/
│       ├── hooks/
│       ├── layouts/
│       └── pages/
├── shared/
│   └── content_contract.py
├── archive/              # 不参与运行的历史实现
├── requirements.txt      # 可升级的直接依赖范围
├── requirements.lock     # 已验证的 Windows 运行依赖快照
└── requirements-dev.lock # 运行依赖加开发检查工具
```

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 22

### 安装

```powershell
Set-Location E:\Code\Glean
python -m pip install -r requirements-dev.lock
python -m playwright install chromium

Set-Location frontend
npm ci
Set-Location ..
```

### 配置

复制并填写根目录环境变量文件：

```powershell
Copy-Item .env.example .env.development
```

环境变量只负责进程级配置：

- `GLEAN_ENV` / `AINEWS_ENV`（兼容旧配置）/ `ENV`，按此顺序取首个非空值
- `APP_VERSION`
- `ALLOWED_ORIGINS`
- `JWT_SECRET_KEY`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `PUBLIC_SITE_URL`
- `PUBLIC_HOME_URL`、`PUBLIC_TELEGRAM_URL`、`PUBLIC_X_URL`、`PUBLIC_BLOG_URL`
- `PUBLIC_GITHUB_URL`、`PUBLIC_BINANCE_URL`、`PUBLIC_OKX_URL`、`PUBLIC_TUTORIAL_URL`

首次安装后，在项目根目录运行 `python -m backend.reset_admin` 设置管理员密码（至少 12 位）。该本机命令也用于忘记密码后的恢复；密码通过隐藏输入读取，不放在命令参数中。之后可以在后台“系统配置 → 账户安全设置”修改用户名和密码，修改成功会使所有已有登录失效。环境中的 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 仅作为首次初始化值，不能覆盖已有数据库账号；初始化后可留空。密码在数据库中保存为带随机盐的哈希。

`JWT_SECRET_KEY` 留空时自动生成并保存在数据库中。真实 `.env.*` 和数据库文件不得提交 Git；只保留 `.env.example` 模板。浏览器退出会撤销当前登录，其他设备不受影响；修改账号或密码会撤销全部登录。登录和改密分别限制同一访问地址在 10 分钟内失败 5 次，并有全局限制；重启服务不会清除限制。

AI 端点链、并发数、请求节流和旧版 Telegram 配置在后台“系统配置”中维护。发布频道、多渠道目标和草稿在“发布中心”维护；实体、叙事、关注列表、提醒规则和行情映射在“情报中心”维护；AI 指标和评测在“AI 质量”维护；来源分级与异常在“来源运营”维护。

自动任务总开关默认关闭，启动 Worker 本身不会开启自动采集。明确开启并保存后，只有已启用且配置了自动采集频率的来源会在运行时段采集；未采集过的来源会开始首次任务，之后至少等待设定间隔。选择“仅手动”会持久保存，重启不会恢复默认频率。关闭总开关、停用来源或改为“仅手动”后，Worker 会在下一次检查（通常 2 秒内）停止对应的自动采集，并清理网络资源；已入库内容保留，尚未入库的缓冲内容不会继续写入。手动采集不受自动任务总开关和运行时段限制，停用来源则不接受新采集。采集日志记录自动或手动触发，方便核对。

普通 HTTP/RSS 与浏览器采集共用按站点保存的请求间隔（5～8 秒，浏览器包括页面及其接口请求）。收到 403、429 或识别人机验证页面时立即停止，至少冷却 30 分钟；24 小时内再次受限会延长等待，网站 `Retry-After` 要求更久时完整遵守。冷却存入数据库，重启、手动采集和定时任务均不能跳过，后台会显示原因和恢复时间。普通 HTTP 网络错误与页面服务异常最多等待 30～35 秒后重试一次，连续失败冷却至少 10 分钟；浏览器路由请求失败则直接暂停。浏览器复用同一会话并阻止图片、视频和字体下载，跳转目标也经过请求检查。这些措施减少请求压力，但不能保证网站永不限制访问。公众号仍使用其独立的限流处理。

AI 资讯的八个固定来源（Hacker News、量子位、InfoQ、Hugging Face Blog、Lobsters、掘金本周最热、WaytoAGI、V2EX 技术）独立于上述定时采集：打开 `/?channel=ai` 时先显示数据库内容，再自动检查来源；页面可见时每 30 秒检查一次，正在更新时每 3 秒读取进度和新内容。默认 5 分钟内复用结果，V2EX 为 10 分钟、WaytoAGI 为 30 分钟，多页面共享任务和更新时间；隐藏页面停止检查，返回时恢复。刷新按钮执行同一更新流程，不能绕过缓存或网站冷却。采集与批量翻译仍由 Worker 完成，不调用旧审核、日报或推送流程；Worker 未运行会明确提示，旧内容仍可阅读。这些来源不会再由旧定时调度重复触发。停用的公众号从 AI 资讯来源栏和内容列表隐藏，订阅及历史记录保留。

Hacker News 读取官网首页的 30 条投稿；选择该来源时保留官网首页排序。列表以最近一次成功获取的首页为准，已离开首页的内容和早期“最新投稿”记录保留在数据库，但不混入公开列表；获取失败时继续显示上次成功的首页。

### 启动

Windows 下双击根目录的 [`start.bat`](start.bat)，会依次启动后端、Worker 和前端，确认服务就绪后自动打开浏览器。三个服务分别显示在独立窗口中；停止时，在每个服务窗口按 `Ctrl+C`，再关闭窗口。缺少依赖、端口被占用或已有 Worker 时会显示原因；启动中途失败时，可查看已打开服务窗口的报错，并按 `Ctrl+C` 停止已经启动的服务。

也可以从命令行启动或只检查启动条件：

```powershell
.\start.bat
.\start.bat -NoBrowser  # 启动服务，不自动打开浏览器
.\start.bat -CheckOnly  # 检查依赖、端口和重复 Worker，不启动服务
```

如需单独启动某个服务：

```powershell
# 分别打开三个 PowerShell 窗口
.\run_backend.ps1
.\run_worker.ps1
.\run_frontend.ps1
```

访问地址：

- 公开前台: [http://localhost:5173/](http://localhost:5173/)
- 登录页: [http://localhost:5173/login](http://localhost:5173/login)
- 后台: [http://localhost:5173/admin](http://localhost:5173/admin)
- 后端: [http://localhost:8000/](http://localhost:8000/)
- 存活检查: [http://localhost:8000/health/live](http://localhost:8000/health/live)
- API 就绪检查: [http://localhost:8000/health/ready](http://localhost:8000/health/ready)
- 完整流水线就绪检查（含 worker）: [http://localhost:8000/health/pipeline](http://localhost:8000/health/pipeline)

API 与 worker 不能合并成一个进程。worker 使用数据库租约阻止重复实例；启动脚本遇到端口或 worker 已占用时会直接报错，不会结束其他进程。

## Agent CLI

项目提供不依赖 FastAPI 进程的本机管理 CLI，供 Codex、Claude Code 等外部 Agent 和 PowerShell 操作者使用。CLI 直接复用后端 service、事务、流水线租约和 worker 命令队列，不包含内置 Agent 或模型运行时。

```powershell
# 不访问数据库
.\glean.ps1 version
.\glean.ps1 capabilities

# 首次使用时显式创建或迁移数据库
.\glean.ps1 system init

# 查询内容与流水线状态
.\glean.ps1 system status --pipeline
.\glean.ps1 content overview --kind news
.\glean.ps1 content list --scope selected --kind news --limit 20

# 复杂配置从 UTF-8 JSON 文件或 stdin 传入
'{"timezone":"UTC"}' | .\glean.ps1 config timezone set --input -
```

默认 stdout 是单个 JSON 文档，业务日志只写入 stderr；调用方应同时检查 `success` 和进程退出码。删除、数据库维护、完整流水线和 Telegram 发送等高影响操作必须显式传入 `--yes`。完整命令、输入 Schema、退出码和 Agent 调用规则见 [`CLI_DOCUMENTATION.md`](CLI_DOCUMENTATION.md)，也可运行 `.\glean.ps1 capabilities <command-id>` 获取机器可读描述。

## 改名兼容

项目现名为 Glean，新命令入口为 `glean.ps1`，原 `ainews.ps1` 继续转发到同一入口。环境选择优先读取 `GLEAN_ENV`，仍支持 `AINEWS_ENV` 和 `ENV`。

数据库文件仍使用 `ainews.db`；浏览器草稿和发送恢复记录沿用原存储键；Webhook 事件类型保留 `ainews.publication` 和 `ainews.analyst.changes`。这些是已有数据与接入协议的兼容标识，改名不要求搬迁数据库或重配订阅。已有部署目录和服务名可继续使用，部署文档中的 Glean 路径用于新部署。

## 后台数据流

系统由两个 Python 进程协作：

- `backend/main.py`: API 入口，只负责接口和数据库初始化
- `backend/worker.py`: 后台 worker，负责调度和自动流水线

- `scheduler_loop`: 按爬虫配置定时拉起抓取任务
- `auto_pipeline_loop`: 在工作时段内等待当前采集结束，然后依次处理快讯和文章；每种内容先聚合事件，再执行黑名单，随后连续处理审核与补充批次，最后执行发布频道、提醒、来源健康和行情窗口任务

审核批次是资源边界，不是业务完成边界。一次自动周期会连续处理 `max_review_batches_per_cycle` 批；如果仍有积压、剩余量无法确认或某阶段失败，worker 会按 `backlog_retry_seconds` 短间隔继续追尾。黑名单阶段失败时只跳过同类内容的后续审核，另一类内容和交付仍会继续。内容写入按批提交；SQLite 短暂写锁不会被误判为租约丢失，提交前仍会按租约持有者身份做栅栏检查。

运行时处理链路如下：

1. 爬虫把内容写入 `news.stage = incoming`
2. 事件聚合服务写入 `content_events` 和 `event_sources`，并将规范事件写入 `archive_entries`
3. 黑名单服务把命中项标记为 `archive_status = blocked`
4. AI 审核服务把归档内容送入 `review_entries`
5. 审核结果落为 `pending / selected / discarded`；入选事件再根据全部来源生成带引用的补充内容
6. 规则按实体名称、符号、别名和叙事关键词自动识别事件；人工关联优先且不会被自动结果覆盖
7. 人工可修订入选稿、对照 AI 原稿、维护证据关系、关键事实、关联事件和事前影响判断；每次修改生成可恢复版本
8. 发布草稿控制顺序、栏目、逐条覆盖和排期，可先生成最终成稿预览；所有目标都通过持久化交付状态机投递，全部成功后才写入日报并开放公开流
9. 自动周期继续评估提醒、生成到期日报、投递分析师变更订阅、检查来源健康，并补齐已到观察时间的市场窗口

## 主要接口

### 公开接口

- `GET /api/public/content`
- `GET /api/public/reports` 支持服务端搜索和 `limit` / `offset` 分页
- `GET /api/public/search`
- `GET /api/public/events/{id}`
- `GET /api/public/entities/{slug}`
- `GET /api/public/narratives/{slug}`
- `GET /api/public/rss.xml`

公开内容、日报、搜索和 RSS 都支持 `publication` 参数；只有启用且标记为公开的频道可读取，RSS 还必须单独启用。

### 后台内容接口

- `GET /api/content/overview`
- `GET /api/content/incoming`
- `GET /api/content/events`
- `GET /api/content/archive`
- `GET /api/content/blocked`
- `GET /api/content/review`
- `GET /api/content/decisions`
- `GET /api/content/export`
- `GET/PUT /api/editorial/entries/{id}` 与修订恢复、反馈接口
- `GET/PATCH /api/editorial/events/{id}` 与来源证据、事件进展、关键事实和关联事件接口
- `GET/POST/PATCH /api/editorial/drafts`
- `GET /api/editorial/drafts/{id}/preview`
- `GET/POST /api/editorial/corrections`

### 后台控制接口

- `POST /api/spiders/run/{name}`
- `POST /api/content/events/cluster`
- `POST /api/content/blocked/apply`
- `POST /api/content/review/run`
- `POST /api/delivery/daily/news`
- `POST /api/delivery/daily/article`
- `POST /api/delivery/send`
- `POST /api/delivery/retry`
- `GET/PATCH /api/publications`
- `GET/POST/PUT /api/publication-channels`
- `/api/intelligence/entities`、`narratives`、`watchlists`、`alerts` 下的读取与维护接口
- `/api/market/instruments` 与 `/api/market/events/{id}` 下的行情映射、刷新、快照和预期接口
- `/api/source-operations` 下的来源目录、健康快照和异常接口
- `/api/ai-quality` 下的指标、调用明细、评测样例和评测运行接口

### 分析师接口

以下接口使用后台创建的 API Key，并通过 `X-API-Key` 请求头调用：

- `GET /api/analyst/news`
- `GET /api/analyst/events` 与 `GET /api/analyst/events/{id}`
- `GET /api/analyst/entities`
- `GET /api/analyst/narratives`
- `GET /api/analyst/tags`
- `GET /api/analyst/delta?since=<ISO-8601>`

`delta` 返回自游标以来变化的事件、市场窗口、实体、叙事和更正；调用方应保存响应中的 `next_cursor` 作为下一次同步起点。

后台还可在“发布中心 → 分析师变更订阅”配置结构化 Webhook。订阅使用整数游标跟踪事件、更正、实体、叙事和标签变更，可按内容类型与内容档案过滤；只有 Webhook 明确返回 2xx 后才推进游标，失败或远端结果不确定时保留原游标等待重试。

### 配置接口

- `GET/POST /api/system/timezone`
- `GET/POST /api/delivery/schedule`
- `GET/POST /api/config/automation`
- `GET/POST /api/integration/telegram`
- `GET/POST /api/integration/ai`
- `GET/PUT /api/editorial/profiles`
- `GET/POST/PUT/DELETE /api/rss/sources`
- `GET/POST /api/review/settings`

## 说明

- 如需了解当前数据库表结构，请以 [`sqlite_schema.py`](backend/app/infrastructure/sqlite/sqlite_schema.py) 为准。
- 如需了解迁移顺序，请以 [`sqlite_migration_plan.py`](backend/app/infrastructure/sqlite/sqlite_migration_plan.py) 为准；[`sqlite_migrations.py`](backend/app/infrastructure/sqlite/sqlite_migrations.py) 仅保留历史兼容转换。
- 旧数据库首次升级会在同级 `archive/database-backups` 中生成迁移前快照，每个已执行步骤按顺序记录在 `schema_migrations`，未登记的中间版本会被拒绝。
- JSON 接口的成功响应使用具体 `APIEnvelope[T]` DTO；前端实际消费的 method/path 由 [`operations.json`](frontend/src/api/operations.json) 登记，后端测试会与 OpenAPI 逐项核对。
- 发布渠道配置、模板字段、提醒条件、行情窗口和日常操作说明见 [`INTELLIGENCE_WORKFLOWS.md`](INTELLIGENCE_WORKFLOWS.md)。

## 验证

```powershell
python -m compileall -q backend
python -m ruff check backend shared --select F --exclude backend/archive
python -m pytest backend/tests -q
Set-Location frontend
npm run lint
npm test
npm run verify:architecture
node --input-type=module -e "import { build } from 'vite'; await build({ build: { write: false } });"
```

日常快速检查可以使用上面的内存构建。正式发布和 CI 使用下面两条命令真实生成并核对静态文件：

```powershell
npm run build:release
npm run verify:release
```

`build:release` 会重新生成 `frontend/dist`，嵌入 `VERSION` 并写出逐文件 SHA-256 清单；`verify:release` 会拒绝版本不一致、文件缺失、哈希变化和未列入清单的额外文件，并用无头 Chromium 实际打开公开页、登录页和后台页，任何浏览器运行时异常都会使发布失败。Nginx 必须按 `DEPLOYMENT.md` 开启文本资源 gzip 压缩。CI 使用 Windows、Python 3.10 和 Node.js 22 执行完整测试和这组真实构建检查。

## 许可

项目原创代码采用 `AGPL-3.0-or-later`。采集内容、模型输出和第三方依赖仍受各自来源条款约束，详见 [LICENSING.md](LICENSING.md) 与 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
