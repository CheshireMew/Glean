# AINews 功能清单

> 基于当前模块化架构整理，供重构和回归检查使用。

## 前台

### 页面

- `frontend/src/pages/NewsFeed.jsx`
- `frontend/src/layouts/PublicLayout.jsx`

### 内容流

- 文章流: `stream=longform`
- 快讯流: `stream=briefs`
- 文章日报
- 快讯日报
- 公开搜索

### 主要行为

- 顶部搜索
- 深浅色切换
- 无限滚动加载
- 日报弹窗查看
- 侧栏快讯同步展示
- 内容流、日报和搜索失败时显示原因与重试入口
- 移动端搜索入口、键盘可操作标签页和带焦点约束的日报对话框

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

### 服务模块

- `content_service`: 内容查询、后台列表和导出
- `public_content_service`: 默认内容档案的公开流、日报、搜索和 RSS
- `content_admin_service`: 黑名单和外部调用密钥
- `event_clustering_service`: 事件聚合、事件相似度检测和自动聚合
- `ai_pipeline_service`: 多端点容错审核、失败隔离和入选后二次补充
- `scraper_run_service` / `scraper_schedule_service`: 爬虫执行与调度
- `scraper_runtime_state_service`: 爬虫状态
- `daily_report_service`: 日报平衡编排、选入明细和成功发布落库
- `telegram_delivery_service`: 实时发送与日报投递
- `delivery_operation_service`: Telegram 分片、幂等键、未知结果确认与断点续发
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
- `scraper_runtime_commands` / `runtime_leases`: 持久命令与 worker 独占租约

### 单一来源

- 内容状态常量: `shared/content_contract.py`
- SQLite schema: `backend/app/infrastructure/sqlite/sqlite_schema.py`
- 旧表迁移: `backend/app/infrastructure/sqlite/sqlite_migrations.py`

## 回归重点

- 前后台都只能使用 `incoming/archive/blocked/review/selected/discarded`
- 公开搜索必须走后端 `/api/public/search`
- 日报读写只能走 `daily_reports`
- Telegram 交付必须携带稳定 `operation_key`，不得绕过持久化操作直接标记已发送
- worker 任务必须保留租约、心跳和重启恢复语义
- 不应再引入额外的并行内容状态模型
