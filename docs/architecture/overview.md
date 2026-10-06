# Glean 项目技术文档

> 当前版本文档，只描述现行架构，不再保留旧阶段模型说明。

## 项目概述

Glean 是一个信息筛选、事件追踪与发布系统，内置 RSS、浏览器与公众号采集能力，负责：

- 多来源抓取新闻和文章
- 将原始内容写入采集池
- 将多来源报道聚合为可追溯事件并执行黑名单拦截
- 按内容档案审核，入选后根据全部来源做引用受限的补充
- 对精选内容做公开展示、人工导出和多渠道分发，管理更正、预警和分析师变更订阅

## 技术栈

### 后端

- Python 3.10+
- FastAPI
- SQLite
- HTTP/RSS 与 Playwright 分层传输
- OpenAI 兼容 AI 端点链

### 前端

- React
- Ant Design
- Vite
- Axios

## 目录与职责

### `backend/`

- `main.py`: API 启动、数据库初始化和请求生命周期
- `worker.py`: 爬虫命令、定时采集和自动内容流水线
- `app/composition.py`: 应用服务与依赖装配
- `app/core`: 配置、异常、响应、日志和通用运行工具
- `app/domain`: 领域规则与来源定义
- `app/models`: 请求和响应模型
- `app/routers`: HTTP 路由
- `app/services`: 应用服务和跨池编排

### `backend/app/infrastructure/`

- `scraper_impl`: 各站点解析器与 HTTP/RSS/Browser 传输实现
- `event_clustering.py`: 跨来源事件匹配
- `repository_impl`: 表级仓储
- `sqlite/sqlite_schema.py` 及注册的专属 schema 模块: 由迁移注册表统一调用的数据库结构定义
- `sqlite/sqlite_migration_plan.py`: 有序、追加式迁移注册表
- `sqlite/sqlite_migrations.py`: 历史兼容转换，只由迁移计划的基线步骤调用

### `frontend/src/`

- `api`: 接口封装
- `hooks/dashboard`: 后台领域 hook
- `hooks/newsfeed`: 前台领域 hook
- `components/dashboard`: 后台 tab 和配置卡片
- `components/newsfeed`: 前台内容组件
- `pages`: 登录、后台、公开前台

### `shared/`

- `content_contract.py`: 内容状态、配置 key、公开流映射

## 当前内容模型

### 采集池

表: `news`

- 用途: 保存每家媒体的原始抓取结果
- 核心状态: `stage = incoming`
- 每个来源通过 `event_id` 加入 `content_events`，来源关系保存在 `event_sources`
- `source_identity` 和 `news_source_identities` 共用采集器的媒体身份规则；入库通过持久身份约束去重，保留原始 `source_url`。历史别名记录和关联不会被迁移删除。
- 事件聚合先检查主体、对象、方向、计划／完成状态、否定和关键数值是否冲突，再计算标题相似度。小数与数量单位精确归一化，同义词按最长匹配和英文单词边界替换；批内、历史匹配与相似度检测共用这些规则，并纳入非主来源的事实约束。

### 归档池

表: `archive_entries`

- 用途: 保存事件的规范内容
- 状态:
  - `ready`
  - `blocked`
  - `reviewed`

### 审核池

表: `review_entries`

- 用途: 保存进入 AI 审核后的内容和结果
- 状态:
  - `pending`
  - `selected`
  - `discarded`

### 其他表

- `content_events` / `event_sources`: 事件和全部来源
- `editorial_profiles`: 审核、补充和日报规则
- `daily_reports` / `daily_report_items`: 日报及选入明细
- `system_config`: 系统配置
- `keyword_blacklist`: 黑名单
- `push_logs`: 发送记录
- `api_keys`: 分析师 API Key
- `delivery_operations` / `delivery_parts` / `delivery_operation_entries`: 幂等发送操作、消息分片和覆盖内容
- `scraper_runtime_state` / `scraper_runtime_commands` / `runtime_leases`: 采集状态、持久命令和 worker 独占租约
- `schema_migrations`: 数据库结构版本
- `delivery_plans`: 首次接受时固化的业务发送计划与完成结果
- `publication_drafts` / `publication_draft_items`: 草稿及保留快照
- `profile_publications` / `publication_channels` / `publication_targets`: 频道与渠道
- `publication_corrections` / `analyst_subscriptions` / `analyst_change_log`: 更正与订阅变更

### 服务所有权

`ContentService` 负责查询与导出；`ContentLifecycleService` 负责删除与恢复，`ContentTransitionService` 负责聚合落库和黑名单转换。黑名单与外部调用密钥分别由 `BlacklistService`、`AnalystAccessService` 管理，项目没有 `ContentAdminService`。

`EditorialWorkbenchService` 管理编辑版本和草稿规则；`EventIntelligenceService` 管理事件进展及来源归属。`PublicationWorkflowService` 接受完整发送计划，全部原始渠道送达后才发布报告、更正或标记内容已送达。`DeliveryOperationService` 只执行已保存消息并记录渠道结果；`DeliveryRetryService` 把完成结果交回对应业务所有者。`AnalystSubscriptionService` 从保存的批次恢复并原子推进游标，不能按后来修改的对象或筛选条件重建旧批次。

清理会跳过未完成草稿或交付引用的内容；已发布和已取消草稿保存条目快照，源内容清理后仍可读取。预警先按启用、时间和渠道资格选候选，再按稳定顺序限制每批数量，避免不合格前批阻塞尾批；准备操作与匹配排队共用事务。

## 运行流程

### 自动流程

worker 启动后持有独占租约，并运行以下任务：

1. `scheduler_loop`
   负责按配置调度爬虫。

2. `auto_pipeline_loop`
   负责按顺序执行：
   - 等待当前抓取结束
   - 来源事件聚合
   - 归档池黑名单拦截
   - 分档案 AI 审核和二次补充
   - 按发布频道和目标运行实时内容、定时稿件与预警，并交付分析师变更订阅

此外，`scraper_command_loop` 消费持久采集命令，`worker_heartbeat_loop` 刷新实例租约，`maintenance_loop` 按保留策略维护数据库。

API 与 worker 分进程运行。worker 必须持有持续刷新的唯一数据库租约；重启时会回收已过期命令并结束被中断的运行。`/health/ready` 检查 API 数据库依赖，`/health/pipeline` 再检查 worker 心跳。

### 处理链路

1. Scraper 抓取内容，写入 `news`
2. Event Clustering 将来源写入 `content_events` 和 `event_sources`，规范事件进入 `archive_entries`
3. Blocklist 将命中项标记为 `blocked`
4. AI 审核更新 `review_entries.review_status`，入选事件生成带来源引用的补充内容
5. 到达设定时间后发送平衡日报，并写入 `daily_reports` 和 `daily_report_items`
6. 配置实时投递目标的发布频道将尚未送达的 `selected` 内容发送到原目标集合；各目标全部完成后才收尾

## 后端接口概览

### 认证

- `POST /api/login`
- `POST /api/system/credentials`

### 内容

- `GET /api/content/overview`
- `GET /api/content/stats`
- `GET /api/content/incoming`
- `GET /api/content/events`
- `GET /api/content/archive`
- `GET /api/content/blocked`
- `GET /api/content/review`
- `GET /api/content/decisions`
- `GET /api/content/export`
- `DELETE /api/content/source/{id}`
- `DELETE /api/content/archive/{id}`
- `DELETE /api/content/review/{id}`
- `POST /api/content/archive/{id}/restore`
- `POST /api/content/blocked/{id}/restore`

### 公开前台

- `GET /api/public/content`
- `GET /api/public/reports`（支持 `kind` / `query` / `limit` / `offset`）
- `GET /api/public/search`

### 配置

- `GET/POST /api/system/timezone`
- `GET/POST /api/delivery/schedule`
- `GET/POST /api/config/automation`
- `GET/POST /api/integration/telegram`
- `GET/POST /api/integration/ai`
- `GET/PUT /api/editorial/profiles`
- `GET/POST/PUT/DELETE /api/rss/sources`
- `GET/POST /api/review/settings`

### 管理与流水线

- `GET /api/spiders`
- `GET /api/spiders/status`
- `POST /api/spiders/run/{name}`
- `POST /api/spiders/stop/{name}`
- `POST /api/spiders/config/{name}`
- `POST /api/content/events/cluster`
- `POST /api/content/events/check-similarity`
- `GET/POST/DELETE /api/content/blocklist`
- `POST /api/content/blocked/apply`
- `POST /api/content/blocked/restore`
- `POST /api/content/review/run`
- `POST /api/content/review/{id}/requeue`
- `POST /api/content/review/requeue`
- `POST /api/content/review/clear`
- `POST /api/delivery/daily/news`
- `POST /api/delivery/daily/article`
- `POST /api/delivery/send`
- `POST /api/delivery/retry`

## 前端界面概览

### 公开前台

- 文章流
- AI 资讯频道
- 公开搜索

当前页面的 `SHOW_SECONDARY_FEEDS = false` 暂时隐藏快讯流和两类日报入口。后端快讯、日报接口和对应组件保留；不能把接口存在视为这些入口当前可见。

### 后台标签页

- 采集池
- 事件聚合
- 归档池
- 已拦截
- 待审核
- 已舍弃
- 已选入
- 爬虫控制
- 系统配置
- 结果输出
- 公众号采集
- AI 质量
- 发布中心
- 情报目录
- 来源运营

## 维护约束

- 新代码不得再引入并行旧模型或额外的兼容层
- 数据库结构变更必须通过 `sqlite_migration_plan.py` 注册追加式迁移，结构模块只由正式创建或升级入口调用
- JSON 接口的成功响应必须使用具体 `APIEnvelope[T]` DTO；前端请求的 method/path 以 `frontend/src/api/operations.json` 为机器可检查的消费者契约
- 前后端内容状态只能使用 `shared/content_contract.py` 中的规范名
- 数据库升级必须保留迁移前快照并在失败时回滚
- Telegram 只有在全部持久化分片明确成功后才能更新内容和日报发送状态
- 多渠道业务只能在冻结计划内全部原始目标送达后完成；失败和结果不确定的渠道需明确恢复，已送达分片不重放
