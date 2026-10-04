# 数据库结构与状态说明

本文档只描述当前 SQLite 运行时结构。数据库唯一来源仍然是 [sqlite_schema.py](../../backend/app/infrastructure/sqlite/sqlite_schema.py)，这里提供的是便于理解的数据视图。

## 数据流转概览

当前运行模型由来源、事件和内容生命周期组成：

1. `news`
   各媒体原始报道的唯一落点

2. `content_events` / `event_sources`
   跨来源事件及其全部来源关系

3. `archive_entries`
   事件归档池，也是黑名单处理入口

4. `review_entries`
   分档案 AI 审核池，同时承载补充内容和发送状态

日报单独存放在 `daily_reports`，不会再作为内容池参与流转。

SQLite 每个连接都启用 `PRAGMA foreign_keys=ON` 与 30 秒忙等待。结构版本记录在 `schema_migrations`；发现旧版本或无版本的既有业务库时，初始化会先通过 SQLite 在线备份接口写入数据库同级的 `backups/`（默认 `data/backups/`），迁移失败则回滚本次结构变更。迁移会先归一化旧的自由状态值，再重建领域校验触发器，因此绕过 API 直接写库也不能写入非法的内容、审核、配置、采集命令或交付状态。

## 核心表

### `news`

用途：保存抓取结果，是内容最早进入系统的地方。

关键字段：

- `id`: 主键
- `title`: 标题
- `content`: 内容
- `source_site`: 来源站点
- `source_url`: 原始链接，唯一约束
- `published_at`: 原发布时间
- `scraped_at`: 抓取时间
- `stage`: 当前采集阶段
- `type`: 内容类型，当前为 `news` 或 `article`
- `event_id`: 所属事件
- `event_similarity`: 与事件规范来源的匹配度
- `is_event_primary`: 是否是当前规范来源

### `archive_entries`

用途：保存已经形成事件的规范内容，作为黑名单处理和归档浏览的入口。

关键字段：

- `id`: 规范来源对应的归档记录 ID
- `title`
- `content`
- `source_site`
- `source_url`
- `published_at`
- `scraped_at`
- `archived_at`: 进入归档池的时间
- `archive_status`: 归档状态
- `content_type`: 内容类型
- `source_item_id`: 对应 `news.id`
- `restored_from_blocklist`: 是否从拦截状态人工恢复
- `block_reason`: 拦截原因

### `review_entries`

用途：保存进入审核流程的内容，以及审核和发送结果。

关键字段：

- `id`: 每个“事件 × 内容档案”审核决定的独立 ID
- `event_id`: 对应的事件
- `profile_slug`: 对应的内容档案
- `title`
- `content`
- `source_site`
- `source_url`
- `published_at`
- `archived_at`
- `queued_at`: 进入审核池的时间
- `review_status`: 审核状态
- `review_summary`: 审核摘要
- `review_reason`: 审核理由
- `review_score`: 审核分数
- `review_category`: 审核分类
- `review_tags`: 审核标签
- `delivery_status`: Telegram 发送状态
- `delivered_at`: 实际发送时间
- `content_type`
- `source_item_id`

### `daily_reports`

用途：存储已生成并已发送的每日日报。

关键字段：

- `publication_key`: 一次成功发布的不可变幂等键
- `date`: 日报日期
- `type`: 内容类型
- `title`: 日报标题
- `content`: 完整正文
- `news_count`: 条目数
- `created_at`: 写入时间

### `daily_report_items`

用途：保存日报最终选入的事件、顺序、栏目、排序分、来源数量，以及发布时的标题、链接、摘要、补充内容和引用快照，使日报在源审核记录变化后仍可审计和复现。

### `delivery_operations` / `delivery_parts` / `delivery_operation_entries`

用途：提供 Telegram 交付的幂等性和逐分片恢复能力。

- `delivery_operations.operation_key`：客户端或自动任务提供的稳定操作键，唯一约束
- `payload_hash`：冻结消息、内容 ID 与日报元数据，阻止同一键被复用于不同内容
- `status`：`pending / sending / failed / needs_attention / sent`
- `delivery_parts`：保存每个不超过 4096 字符的消息分片、尝试次数、远端消息 ID 与最后错误
- `delivery_operation_entries`：用 `scope + id` 记录来自任一内容池的操作引用；审核外键可置空，历史引用和已冻结消息仍会保留

### `scraper_runtime_state` / `scraper_runtime_commands` / `runtime_leases`

用途：持久化采集 UI 状态、待处理命令和 worker 独占租约。运行状态保存 `run_id / worker_id / heartbeat_at`，命令保存 `claimed_by / lease_expires_at / attempt_count`。worker 重启会恢复过期命令并如实结束被中断的运行。

## 配置与辅助表

- `system_config`: 系统配置
- `keyword_blacklist`: 黑名单关键词
- `push_logs`: 已完成交付的审核内容日志，外键指向 `review_entries`
- `api_keys`: 分析师 API Key
- `tags` / `news_tags`: 标签体系
- `processing_logs`: 带 `operation_id` 的处理阶段日志
- `schema_migrations`: 已应用结构版本
- `filter_stats`: 过滤统计

## 状态定义

### `news.stage`

| 值 | 含义 |
| :--- | :--- |
| `incoming` | 新抓取内容，尚未进入归档池 |
| `archived` | 已加入事件并写入归档流程 |

### `archive_entries.archive_status`

| 值 | 含义 |
| :--- | :--- |
| `ready` | 已归档，等待黑名单处理或人工查看 |
| `blocked` | 命中黑名单，被拦截 |
| `reviewed` | 已推进到审核池 |

### `review_entries.review_status`

| 值 | 含义 |
| :--- | :--- |
| `pending` | 待审核 |
| `processing` | 已被一个审核批次认领 |
| `selected` | 审核通过 |
| `discarded` | 审核未通过 |

### `review_entries.delivery_status`

| 值 | 含义 |
| :--- | :--- |
| `pending` | 待发送 |
| `sent` | 已发送到 Telegram |
| `expired` | 已明确结束且不再进入自动交付 |

## 处理链路

1. 爬虫写入 `news`
2. 事件聚合写入 `content_events`、`event_sources` 和 `archive_entries`
3. 黑名单把归档内容分成 `blocked` 或推进到 `review_entries`
4. AI 审核在 `review_entries` 内更新决定，入选事件随后根据全部来源生成带引用的补充内容
5. 到达设定时间时，默认内容档案的入选事件经过栏目、来源配额编排；发送成功后写入 `daily_reports` 和 `daily_report_items`
6. 默认内容档案中尚未发送的 `selected + pending delivery` 内容再走 Telegram 实时发送

两个交付步骤都会先冻结到 `delivery_operations`，只有全部分片明确成功后才更新 `review_entries.delivery_status` 和日报记录。

## 常见恢复操作

### 恢复已拦截内容

为所有已启用内容档案重新建立待审核条目，将 `archive_entries.archive_status` 改为 `reviewed`，并标记 `restored_from_blocklist = 1`。这样恢复后的内容不会滞留在归档池。

### 恢复审核结果

将 `review_entries.review_status` 改回 `pending`，同时清空审核结果字段。

### 删除内容

后台删除来源时只移除该来源；删除归档记录表示删除整个归档事件链；删除单条审核记录只删除该档案下的审核结果，不再误删事件、来源、其他档案结果或历史日报快照。

## 维护原则

- 运行时状态名称以 [content_contract.py](../../shared/content_contract.py) 为准
- 表结构以 [sqlite_schema.py](../../backend/app/infrastructure/sqlite/sqlite_schema.py) 为准
- 历史数据迁移以 [sqlite_migrations.py](../../backend/app/infrastructure/sqlite/sqlite_migrations.py) 为准
