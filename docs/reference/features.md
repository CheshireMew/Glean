# Glean 功能清单

> 基于当前模块化架构整理，供重构和回归检查使用。

## 前台

### 页面

- `frontend/src/pages/NewsFeed.jsx`
- `frontend/src/layouts/PublicLayout.jsx`

### 内容流

- 文章流: `stream=longform`
- AI 资讯频道
- 后端仍提供快讯流 `stream=briefs`、文章日报和快讯日报；公开页面目前通过 `SHOW_SECONDARY_FEEDS = false` 隐藏这些入口，相关数据和组件保留。
- 公开搜索

### 主要行为

- 顶部搜索
- 深浅色切换
- 无限滚动加载
- 内容流和搜索失败时显示原因与重试入口
- 自动刷新保留已加载深度，并与加载更多协调；刷新失败保留上次成功列表
- 移动端搜索入口、键盘可操作频道切换

## 后台

### 入口

- `frontend/src/pages/Dashboard.jsx`
- `frontend/src/hooks/useDashboardData.js`

### Tab 清单

1. 采集池
   文件: `frontend/src/components/dashboard/NewsManagementTab.jsx`
   能力: 列表、搜索、按来源筛选、删除、导出入口

2. 事件聚合
   文件: `frontend/src/components/dashboard/EventGroupsTab.jsx`
   能力: 多来源事件视图、事件相似度检测、来源移除和规范来源自动提升

3. 归档池
   文件: `frontend/src/components/dashboard/ArchiveTab.jsx`
   能力: 列表、搜索、按来源筛选、恢复到采集池、删除、加入输出

4. 已拦截
   文件: `frontend/src/components/dashboard/BlocklistTab.jsx`
   能力: 黑名单管理、执行拦截、批量恢复、单条恢复、删除、加入输出

5. 待审核
   文件: `frontend/src/components/dashboard/ReviewQueueTab.jsx`
   能力: 列表、搜索、按来源筛选、加入输出

6. 系统配置
   文件: `frontend/src/components/dashboard/SystemSettingsTab.jsx`
   能力: 时区、自动化窗口、AI 端点链、内容档案、RSS 源、Telegram、账户安全、外部调用密钥

7. 结果输出
   文件: `frontend/src/components/dashboard/ExportTab.jsx`
   能力: 手动精选、格式化复制、发送到 Telegram、手动触发每日日报

8. 已舍弃
   文件: `frontend/src/components/dashboard/DiscardedContentTab.jsx`
   能力: 审核配置、执行审核、恢复单条、批量恢复、清空审核结果、删除

9. 已选入
   文件: `frontend/src/components/dashboard/SelectedContentTab.jsx`
   能力: 列表、搜索、按来源筛选、删除、加入输出

10. 爬虫控制
    文件: `frontend/src/components/dashboard/SpiderControlTab.jsx`
    能力: 运行与取消采集、调度配置、RSS 来源管理和真实错误查看

11. 公众号采集
    文件: `frontend/src/components/dashboard/WechatSourceManager.jsx`
    能力: 微信登录状态、公众号订阅、文章采集及来源配置

12. AI 质量
    文件: `frontend/src/components/dashboard/AiQualityTab.jsx`
    能力: AI 调用记录、质量指标、费用与预算、失败查看

13. 发布中心
    文件: `frontend/src/components/dashboard/PublicationCenterTab.jsx`
    能力: 频道与多渠道目标、草稿编排和预览、网站发布、外部投递、更正及分析师变更订阅；未送达渠道显示状态并提供针对原操作的恢复入口

14. 情报目录
    文件: `frontend/src/components/dashboard/IntelligenceCenterTab.jsx`
    能力: 实体、叙事、关注列表、预警策略和匹配、市场标的；事件详情可编辑进展并查看来源

15. 来源运营
    文件: `frontend/src/components/dashboard/SourceOperationsTab.jsx`
    能力: 来源档案、健康快照、完整性与入选质量、异常处理

### 共享前端基础

- API 封装: `frontend/src/api/*.js`
- 通用分页列表控制器: `frontend/src/hooks/dashboard/usePaginatedContentList.js`
- 爬虫运行态: `frontend/src/hooks/dashboard/useDashboardScraperRuntimeData.js`
- 概览统计: `frontend/src/hooks/dashboard/useDashboardOverviewData.js`

## 后端

### 应用入口

- `backend/main.py`: 只负责 ASGI 启动、数据库初始化和生命周期
- `backend/worker.py`: 爬虫命令、采集调度和自动流水线入口
- `backend/app/infrastructure/repositories.py`: repository 的统一装配入口

### 路由模块

- `backend/app/routers/auth.py`
- `backend/app/routers/news.py`
- `backend/app/routers/config.py`
- `backend/app/routers/pipeline.py`
- `backend/app/routers/editorial.py`
- `backend/app/routers/publications.py`
- `backend/app/routers/delivery.py`
- `backend/app/routers/intelligence.py`
- `backend/app/routers/market_intelligence.py`
- `backend/app/routers/source_operations.py`
- `backend/app/routers/ai_quality.py`
- `backend/app/routers/wechat.py`
- `backend/app/routers/public_content.py`
- `backend/app/routers/spiders.py`
- `backend/app/routers/integrations.py`

### 服务模块

- `content_service`: 内容查询、后台列表和导出
- `public_content_service`: 默认内容档案的公开流、日报、搜索和 RSS
- `content_lifecycle_service` / `content_transition_service`: 内容删除、恢复和状态转换；未完成稿件或交付引用的内容返回业务冲突
- `blacklist_service` / `analyst_access_service`: 黑名单和外部调用密钥
- `event_clustering_service`: 事件聚合、事件相似度检测和自动聚合
- `ai_pipeline_service`: 多端点容错审核、失败隔离和入选后二次补充
- `scraper_run_service` / `scraper_schedule_service`: 爬虫执行与调度
- `scraper_runtime_state_service`: 爬虫状态
- `daily_report_service`: 日报平衡编排、选入明细和成功发布落库
- `telegram_delivery_service`: 实时发送与日报投递
- `delivery_operation_service`: 多渠道消息快照、分片、幂等键、执行租约和原计划续发
- `delivery_retry_service`: 按原操作类型交回业务所有者收尾，未知结果须核对后明确重试
- `publication_workflow_service`: 草稿、实时发布、更正和预警的冻结计划与成组收尾
- `editorial_workbench_service` / `event_intelligence_service`: 编辑版本、草稿校验、事件进展与来源归属
- `analyst_subscription_service`: 冻结 Webhook 变更批次、先恢复原批次再继续扫描、单调推进游标
- `ai_quality_service` / `source_operations_service`: AI 质量记录和来源健康运营
- `wechat_source_service`: 公众号采集管理
- `runtime_health_service`: 分离 API 就绪检查与流水线 worker 就绪检查
- `automation_settings_service` 等配置服务: 分领域读写系统配置
- `auth_service`: 登录和令牌验证

## 数据模型

### 运行时 contract

- `news`: 采集源池，核心状态 `incoming`
- `content_events` / `event_sources`: 事件及其来源关系
- `archive_entries`: 归档池，核心状态 `ready / blocked / reviewed`
- `review_entries`: 审核池，核心状态 `pending / selected / discarded`
- `daily_reports`: 以 `publication_key` 标识的不可变日报发布记录
- `daily_report_items`: 日报选入顺序和编排依据
- `system_config`: 系统配置
- `keyword_blacklist`: 黑名单
- `push_logs`: 发送日志
- `delivery_operations` / `delivery_parts` / `delivery_operation_entries`: 带租约、类型化内容引用和消息快照的可恢复发送操作
- `delivery_plans`: 原始内容、版本、渠道集合与业务收尾结果；仅所有原始目标送达后原子完成
- `publication_drafts` / `publication_draft_items`: 草稿及条目；未完成草稿保护引用，已发布/取消条目保留快照并允许脱离被清理内容
- `profile_publications` / `publication_channels` / `publication_targets`: 频道及多渠道投递目标
- `publication_corrections` / `analyst_subscriptions` / `analyst_change_log`: 更正和游标订阅
- `alert_policies` / `alert_matches`: 预警策略和逐条投递状态
- `scraper_runtime_commands` / `runtime_leases`: 持久命令与 worker 独占租约

### 单一来源

- 内容状态常量: `shared/content_contract.py`
- SQLite 创建与升级入口: `backend/app/infrastructure/sqlite/sqlite_migration_plan.py`；基础表由 `sqlite_schema.py` 定义，各领域结构由注册的专属 schema 模块定义
- 历史基线转换: `backend/app/infrastructure/sqlite/sqlite_migrations.py`

## 回归重点

- 前后台都只能使用 `incoming/archive/blocked/review/selected/discarded`
- 公开搜索必须走后端 `/api/public/search`
- 日报读写只能走 `daily_reports`
- Telegram 交付必须携带稳定 `operation_key`，不得绕过持久化操作直接标记已发送
- worker 任务必须保留租约、心跳和重启恢复语义
- 不应再引入额外的并行内容状态模型
