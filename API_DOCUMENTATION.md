# Glean API 概览

API 默认运行在 `http://localhost:8000`，业务路由统一使用 `/api` 前缀。后台接口使用登录获得的 Bearer Token；公开接口不需要登录。

## 公开接口

- `GET /api/public/content?stream=briefs|longform&limit=20&cursor=...`
- `GET /api/public/reports?kind=news|article&limit=20&offset=0`
- `GET /api/public/search?query=关键词&kind=news|article|all`
- `GET /api/public/rss.xml?kind=news|article&limit=20`
- `GET /api/public/events/{id}`：返回公开时间线、关键事实、来源证据、关联事件、更正、实体、叙事和市场窗口
- `GET /api/public/entities/{slug}`
- `GET /api/public/narratives/{slug}`：包含 90 天公开事件趋势

公开内容只读取每种内容类型的默认内容档案。返回项包含规范来源、事件来源数、全部来源链接、审核结果、补充摘要和实际引用。

公开内容流使用 `(published_at, id)` 游标分页。首次请求不传 `cursor`，后续使用响应中的 `next_cursor`；游标无效时返回 400。日报与搜索目前使用 `limit + offset`，所有公开接口的 `limit` 上限为 100。

## 后台内容接口

- `GET /api/content/overview`
- `GET /api/content/incoming`
- `GET /api/content/events`
- `GET /api/content/archive`
- `GET /api/content/blocked`
- `GET /api/content/review`
- `GET /api/content/decisions?decision=selected|discarded`
- `GET /api/content/export`

后台列表分页上限为每页 200。`/api/content/export` 不套用列表页固定条数上限，而是用独立数据库连接每 500 行读取一批并持续输出 JSON 数组；可用 `scope`、日期、关键词、来源、内容类型和 `fields` 过滤。日期必须是 ISO 格式，开始日期不能晚于结束日期。

## 流水线接口

- `POST /api/content/events/cluster`
- `POST /api/content/events/check-similarity`
- `POST /api/content/blocked/apply`
- `POST /api/content/review/run`
- `POST /api/delivery/daily/news`
- `POST /api/delivery/daily/article`
- `POST /api/delivery/send`
- `POST /api/delivery/retry`

手动审核请求只接受扫描范围和内容类型，审核标准始终来自内容档案：

```json
{
  "hours": 24,
  "kind": "news"
}
```

所有发送请求都必须携带 8 到 128 字符的 `operation_key`，可用字符为字母、数字、冒号、点、下划线和连字符。相同操作键与相同内容可安全重试；相同键配不同内容会被拒绝。Telegram 消息按 4096 字符上限持久化分片，只有明确未发送或明确失败的分片能重试；网络结果不确定时接口返回 `needs_attention`，前台必须先让用户确认。

```json
{
  "entries": [
    {"scope": "selected", "id": 12},
    {"scope": "archive", "id": 18}
  ],
  "operation_key": "manual:news:20260812:7f2a"
}
```

`scope` 必须是 `incoming / archive / blocked / review / selected / discarded` 之一。操作及其内容引用会被持久化；可通过 `GET /api/delivery/operations` 和 `GET /api/delivery/operations/{operation_key}` 查询刷新前后仍未完成的交付。

重试请求为：

```json
{
  "operation_key": "manual:news:20260812:7f2a"
}
```

## 运行状态接口

- `GET /health/live`：进程存活，不检查依赖
- `GET /health/ready`：只检查 API 所需的数据库、结构版本、关键表和外键开关；未就绪返回 503
- `GET /health/pipeline`：在 API 就绪基础上检查 worker 租约；流水线不可用时返回 503
- `GET /`：兼容入口，返回 API 就绪状态和版本

每个 HTTP 响应包含 `X-Request-ID`，服务日志记录相同 ID、方法、路径、状态码和耗时。

## 配置接口

- `GET/POST /api/system/timezone`
- `POST /api/system/settings`：原子保存时区、自动化运行窗口、批大小和日报时间
- `GET/POST /api/config/automation`
- `GET/POST /api/delivery/schedule`
- `GET/POST /api/integration/ai`
- `GET/POST /api/integration/telegram`
- `GET/PUT /api/editorial/profiles`
- `GET/POST/PUT/DELETE /api/rss/sources`
- `POST/GET/PATCH/DELETE /api/integration/analyst/keys`
- `GET /api/analyst/news`：使用 `X-API-Key` 读取分页后的已选入内容

## 情报编辑与发布接口

- `POST /api/editorial/events/{id}/facts` 与 `PATCH /api/editorial/event-facts/{fact_id}`
- `POST /api/editorial/events/{id}/relations`
- `POST /api/intelligence/events/{id}/classify` 与 `POST /api/intelligence/classify`
- `GET /api/editorial/drafts/{id}/preview`：生成与实际发布相同的标题、正文和分片，但不创建交付操作
- `GET/POST/PUT /api/integration/analyst/subscriptions`
- `POST /api/integration/analyst/subscriptions/deliver`

分析师读取还包括 `GET /api/analyst/events`、`events/{id}`、`entities`、`narratives`、`tags` 和 `delta`。变更订阅只接受已经配置的 Webhook 渠道，发送体的 `event` 固定为 `ainews.analyst.changes`（Glean 保留的兼容协议标识），包含订阅信息、`from/to/has_more` 游标和变更数组。服务端通过持久化交付状态机发送；只有确认 2xx 后才推进订阅游标。

除流式导出和 RSS 外，`/api` 响应统一包含 `success / data / message / code / timestamp`，分页信息位于 `pagination`，失败详情位于 `error`。完整请求模型和响应结构以 FastAPI 生成的 `/docs` 为准。
