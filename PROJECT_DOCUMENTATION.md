# Glean 项目技术文档

> 当前版本文档，只描述现行架构，不再保留旧阶段模型说明。

## 项目概述

Glean 是一个信息筛选、事件追踪与发布系统，当前内置来源以加密行业为主，负责：

- 多来源抓取新闻和文章
- 将原始内容写入采集池
- 将多来源报道聚合为可追溯事件并执行黑名单拦截
- 按内容档案审核，入选后根据全部来源做引用受限的补充
- 对精选内容做公开展示、人工导出和 Telegram 分发

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
- `app/core`: 配置、异常、响应、运行时装配、爬虫注册
- `app/routers`: HTTP 路由
- `app/services`: 应用服务和跨池编排

### `backend/app/infrastructure/`

- `scraper_impl`: 各站点解析器与 HTTP/RSS/Browser 传输实现
- `event_clustering.py`: 跨来源事件匹配
- `repository_impl`: 表级仓储
- `sqlite/sqlite_schema.py`: schema 唯一来源
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

## 运行流程

### 自动流程

应用启动后会有两个后台循环：

1. `scheduler_loop`
   负责按配置调度爬虫。

2. `auto_pipeline_loop`
   负责按顺序执行：
   - 等待当前抓取结束
   - 来源事件聚合
   - 归档池黑名单拦截
   - 分档案 AI 审核和二次补充
   - 定时日报与 Telegram 实时发送

API 与 worker 分进程运行。worker 必须持有持续刷新的唯一数据库租约；重启时会回收已过期命令并结束被中断的运行。`/health/ready` 检查 API 数据库依赖，`/health/pipeline` 再检查 worker 心跳。

### 处理链路

1. Scraper 抓取内容，写入 `news`
2. Event Clustering 将来源写入 `content_events` 和 `event_sources`，规范事件进入 `archive_entries`
3. Blocklist 将命中项标记为 `blocked`
4. AI 审核更新 `review_entries.review_status`，入选事件生成带来源引用的补充内容
5. 到达设定时间后发送平衡日报，并写入 `daily_reports` 和 `daily_report_items`
6. 默认内容档案中尚未发送的 `selected` 内容再走 Telegram 实时发送

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
- 快讯流
- 文章日报
- 快讯日报
- 公开搜索

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

## 维护约束

- 新代码不得再引入并行旧模型或额外的兼容层
- 数据库结构变更必须以 `sqlite_schema.py` 和 `sqlite_migration_plan.py` 的追加式迁移链为准
- JSON 接口的成功响应必须使用具体 `APIEnvelope[T]` DTO；前端请求的 method/path 以 `frontend/src/api/operations.json` 为机器可检查的消费者契约
- 前后端内容状态只能使用 `shared/content_contract.py` 中的规范名
- 数据库升级必须保留迁移前快照并在失败时回滚
- Telegram 只有在全部持久化分片明确成功后才能更新内容和日报发送状态
