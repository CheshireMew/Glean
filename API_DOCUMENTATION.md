# Glean API 概览

API 默认运行在 `http://localhost:8000`，业务路由统一使用 `/api` 前缀。后台接口使用登录获得的 Bearer Token；公开接口不需要登录。

账户接口：`POST /api/login` 接收表单 `username` / `password`；`GET /api/session` 验证当前登录并返回用户名；`POST /api/logout` 撤销当前登录；`POST /api/system/credentials` 验证当前密码并修改账户，成功后全部旧登录失效。除登录外都要求 Bearer Token。登录凭证有效期为 12 小时，且必须存在对应的服务器会话；退出后的凭证不能重放。登录和修改账户都有持久化尝试限制，超过限制返回 `429` 和 `Retry-After` 秒数。密码重置仅有本机命令，不提供匿名网络重置接口。

## 公开接口

- `GET /api/public/ai/content?source=lobsters&limit=20&offset=0`：读取已入库的 AI 资讯与译文，不直接请求外站。
- `POST /api/public/ai/refresh`：页面打开或停留时检查八个固定来源是否需要更新，返回 `updating`、来源状态及失败原因。无需传来源 URL 或模型参数；同一来源默认 5 分钟内复用结果（V2EX 10 分钟、WaytoAGI 30 分钟），多页面共用任务，尊重网站冷却和来源停用状态。Worker 负责实际采集和翻译，不依赖旧定时采集总开关；服务未运行时返回明确提示，旧内容仍可读取。
- `GET /api/public/content?stream=briefs|longform&limit=20&cursor=...`
- `GET /api/public/reports?kind=news|article&limit=20&offset=0`
- `GET /api/public/search?query=关键词&kind=news|article|all`
- `GET /api/public/rss.xml?kind=news|article&limit=20`
- `GET /api/public/events/{id}`：返回公开时间线、关键事实、来源证据、关联事件、更正、实体、叙事和市场窗口
- `GET /api/public/entities/{slug}`
- `GET /api/public/narratives/{slug}`：包含 90 天公开事件趋势

原有公开内容读取内容档案，返回项包含规范来源、事件来源数、全部来源链接、审核结果、补充摘要和实际引用。

`GET /api/public/ai/content` 独立读取四个 AI/技术信息源的采集记录，支持 `source`、`query`、`limit`（1–100）、`offset`。有已保存译文时 `title`、`source_excerpt` 优先返回中文，`original_title` 保留原始标题，`translated` 表示是否使用译文；搜索同时匹配中文译文与原始内容。无译文时返回来源文字，无内容时返回空字符串，不读取审核摘要、不生成导读。此 GET 只读数据库，不调用模型。四个来源不进入原有公开流、搜索、RSS 和日报。已取消发布的草稿不再出现在公开日报中，历史快照保留。

采集任务保存上述来源后自动批量翻译英文标题和已有正文/摘要前 600 字符，每个请求最多 10 条；中文字段跳过。使用运行环境的 `DEEPSEEK_API_KEY`，模型 `deepseek-flash`，`thinking.type=disabled`，不额外抓取原文。译文保存在 `news_translations`，原始 `news` 内容不覆盖；来源标题或正文开头变化时旧译文失效。接口失败保留原文，下一次采集或补译命令可继续处理；不在同次请求中重复重试。`news_translation_batches` 保存每批实际 token 用量和结果。

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
- `POST /api/editorial/drafts/{id}/publish?website_only=true`：将已审核入选的草稿发布到公开网站，不要求外部投递渠道。保存日报和条目快照后，内容可通过公开列表、搜索、RSS 和事件详情读取；不会把外部投递状态改成已送达。省略该参数则沿用原有外部投递流程。
- `PUT /api/editorial/entries/{id}`：人工编辑支持 `review_status`（`pending`、`selected`、`discarded`）；入选需同时具备 `review_summary` 和 `review_reason`，修改保留修订记录。
- `GET/POST/PUT /api/integration/analyst/subscriptions`
- `POST /api/integration/analyst/subscriptions/deliver`

分析师读取还包括 `GET /api/analyst/events`、`events/{id}`、`entities`、`narratives`、`tags` 和 `delta`。变更订阅只接受已经配置的 Webhook 渠道，发送体的 `event` 固定为 `ainews.analyst.changes`（Glean 保留的兼容协议标识），包含订阅信息、`from/to/has_more` 游标和变更数组。服务端通过持久化交付状态机发送；只有确认 2xx 后才推进订阅游标。

除流式导出和 RSS 外，`/api` 响应统一包含 `success / data / message / code / timestamp`，分页信息位于 `pagination`，失败详情位于 `error`。完整请求模型和响应结构以 FastAPI 生成的 `/docs` 为准。

### RSS 预览

`POST /api/rss/preview`（需登录），请求示例：`{"feed_url":"https://example.substack.com/feed","parser_type":"generic","limit":3}`。`limit` 为 1–5；解析方式为 `generic` 或 `summary_source_link`。

返回标准 API envelope，`data` 为 `{feed_url, notice, items}`。每项包含标题、作者、时间、原文 URL、订阅源提供的正文及 `content_origin=feed`、`completeness=unknown`。预览不保存来源、不写内容池、不触发审核或投递。RSS 正式采集现在保留源提供的正文，不再截到 500 字符；历史内容不自动回填。

## 微信公众号采集 API

以下 `/api/wechat/*` 接口均要求现有管理员 Bearer 登录凭据，返回标准 APIEnvelope，不返回微信 Cookie 或 token。

| 方法 | 路径 | 功能 |
| --- | --- | --- |
| GET | `/api/wechat/status` | 已保存的登录状态、二维码进度、系统自动化状态 |
| POST | `/api/wechat/login` | 开始扫码登录；后台浏览器有效期 5 分钟，重复调用复用本次登录 |
| POST | `/api/wechat/login/cancel` | 取消本次二维码登录并关闭浏览器 |
| POST | `/api/wechat/disconnect` | 清除本机微信登录凭据，保留来源和文章 |
| GET | `/api/wechat/search?query=名称&begin=0` | 搜索公众号，每页 5 个 |
| GET | `/api/wechat/sources` | 已订阅公众号，含 runtime_name |
| POST | `/api/wechat/sources` | 添加搜索返回的 fake_id、name、alias、introduction；重复账号不会重复添加 |
| PUT | `/api/wechat/sources/{source_id}` | 设置 enabled、default_limit（1～100）、default_interval（30～10080 分钟） |

手动采集复用 `POST /api/spiders/run/wechat__{source_id}`，请求 `{"items":10}`，由 worker 执行；状态复用 `GET /api/spiders/status`。公开阅读仍为 `GET /api/public/ai/content?source=wechat__{source_id}`。来源接口有摘要才展示摘要，不额外抓取正文。尚未登录、会话失效、限流及接口格式变化会明确报错。
