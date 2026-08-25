# AINews 情报与发布工作流

本文说明后台新增能力怎样组合成完整工作流，以及 JSON 配置中实际支持的字段。接口的请求与响应结构仍以运行中的 OpenAPI 和 `ainews.ps1 capabilities` 为准。

## 1. 从事件证据到可发布内容

事件详情页把同一事件的来源集中展示。编辑可为每个来源设置以下证据字段：

- `source_role`：`primary`、`independent`、`reporting`、`repost` 或 `commentary`。
- `evidence_group`：同源转载应使用同一组名，独立来源数按组去重。
- `origin_news_id`：转载或二次报道所依据的同事件来源。
- `independence_score`：0 到 1；大于 0 的证据组计入独立来源。
- `verification_status`：`unverified`、`verified` 或 `disputed`。
- `evidence_notes`：人工核验说明。

事件进展用于记录后续发展、更正、撤回、背景和市场变化。结构化关键事实单独保存事实文字、依据来源、核验状态、置信度和公开性；关联事件明确记录原因、结果、后续、矛盾、同一故事或普通相关。公开事件页只显示 `is_public=true` 的进展、事实和关系，而且事件至少有一条已经发布的入选稿后才可公开读取。

审核稿的人工修改会生成不可变修订记录。编辑可直接对照 AI 原稿与当前人工版本，查看修改者、修改说明、字段变化和质量评分，也可把任一历史版本恢复为新版本；恢复不会覆盖或删除旧记录。对 AI 结果的接受、修改、拒绝和错误反馈会进入 AI 质量统计。

## 2. 发布频道与投递渠道

每个内容档案自动对应一个发布频道。发布频道负责内容选择和公开呈现，投递渠道负责实际发送，两者通过投递目标关联。

发布频道可设置：

- `digest_frequency`：`realtime`、`daily`、`weekly` 或 `manual`。
- `digest_time` 与 `timezone`：日报或周报到期时间。
- `is_public`：是否出现在公开前台并允许通过 `publication` 参数读取。
- `rss_enabled`：是否允许该频道生成 RSS；只有公开频道可使用。
- `targets`：渠道与 `realtime`、`digest`、`alert` 模式的组合。
- `template`：支持 `title_prefix`、`title_suffix`、`intro`、`footer`；周报还支持 `weekday`，0 表示周一，6 表示周日。模板文字按纯文本转义，不会被当作 HTML 执行。

渠道配置示例：

```json
{
  "telegram": {"bot_token": "...", "chat_id": "..."},
  "webhook": {"url": "https://example.com/hook", "headers": {"Authorization": "Bearer ..."}},
  "discord": {"url": "https://discord.com/api/webhooks/..."},
  "slack": {"url": "https://hooks.slack.com/services/..."},
  "email": {
    "host": "smtp.example.com",
    "port": 587,
    "from_address": "news@example.com",
    "to_addresses": ["reader@example.com"],
    "username": "news@example.com",
    "password": "...",
    "use_tls": true,
    "use_ssl": false,
    "subject": "AINews 内容更新"
  }
}
```

后台保存后会隐藏常见密钥字段；再次提交掩码值会保留原密钥。Discord 内容会在 2000 字符边界内分段，不会静默截断。

发布草稿可以调整标题、栏目、顺序、是否包含和逐条覆盖字段，也可立即发布或设置 `scheduled_at`。成稿预览与实际发布使用同一排版器，会展示最终标题、正文、条目数、分片数和目标数，但不会创建交付记录。每个目标都有独立且稳定的操作键，重试会继续未完成的分段，不会重复发送已经确认成功的分段。只有所有目标成功后，草稿才会变为 `published`，对应审核稿才会标记为已投递，公开日报才会落库。

更正、澄清和撤回必须关联日报、审核稿或事件。系统据此找到发布频道，并使用同一持久化交付流程发送；部分渠道失败时保持待重试状态。

## 3. 实体、叙事、关注列表和提醒

实体支持资产、协议、公司、人物、监管机构、交易所、组织和司法辖区。别名用于统一检索，事件可记录实体角色和关联置信度。叙事用于把多个事件组织为持续主题，并可维护自动识别关键词。自动周期先按实体名称、符号、别名和叙事名称、关键词识别近期事件，再评估提醒；人工关联优先，规则不会覆盖人工来源或置信度。公开实体与叙事页只列出已经发布的事件，叙事页另展示 90 天公开事件趋势。

关注列表可以组合实体和叙事。提醒规则也可不使用关注列表，直接在 `conditions` 中配置：

```json
{
  "min_score": 8,
  "categories": ["监管", "市场"],
  "content_types": ["news"],
  "min_independent_sources": 2,
  "verified_only": true,
  "source_sites": ["SEC", "Federal Reserve"],
  "keywords": ["ETF", "执法"],
  "entity_ids": [1, 2],
  "narrative_ids": [3]
}
```

同类数组内部采用“任一命中”，不同条件之间采用“全部满足”。关注列表中的实体和叙事会与条件中的 ID 合并；实体和叙事各自至少命中一个即可。

提醒的 `schedule_type` 支持 `instant`、`daily` 和 `weekly`。`quiet_hours` 示例：

```json
{
  "timezone": "Asia/Shanghai",
  "start": "23:00",
  "end": "08:00",
  "digest_time": "09:00",
  "weekday": 0
}
```

跨午夜静默时段会按本地时间计算。每日和每周提醒在 `digest_time` 后成组发送，周报的 `weekday` 同样以周一为 0。

## 4. 来源运营

来源目录由当前爬虫注册表自动同步，不另建一套采集配置。运营字段包括权威级别、是否官方、主页、元数据和是否参与自动采集。停用后，定时调度不会再启动该来源；人工命令仍可用于明确的诊断或补采。

默认来源包含 SEC、CFTC、Kraken、Ethereum Foundation 和 ENS Governance 的官方 RSS，分别覆盖监管、交易所、项目与治理信息。24 小时健康快照记录最新运行结果、抓取条数、平均延迟、标题与正文完整率、事件入簇率和内容入选率。系统每天自动生成一次快照，也可在后台或 CLI 手动生成。以下情况会创建去重异常：采集失败、零结果、正文完整率低于 60%，超过三个默认采集间隔且至少 6 小时没有运行记录，或相邻窗口内容量/正文完整率大幅下降而疑似解析结构漂移。异常可确认为已知问题或标记解决，不会自动删除。

## 5. 市场影响

行情品种通过实体与事件关联。`binance` 提供方会自动读取公开 K 线，`manual` 用于没有自动数据源的资产或人工校准。系统使用事件发布时间作为 T0，并在可用后补齐：`t-1h`、`t0`、`t+15m`、`t+1h`、`t+24h` 和 `t+7d`。

编辑可在价格出现前保存 `expected_direction`、`expected_impact` 和 `confidence`。系统以 T0 价格计算 15 分钟、1 小时和 24 小时收益率，并给出实际方向。如果品种元数据包含 `benchmark_instrument_id`，还会用相同事件窗口计算 24 小时基准调整收益。公开事件页和分析师事件接口都会返回已经形成的市场窗口；尚未到达的窗口不会伪造数据。

## 6. AI 质量

AI 审核、补充和固定样例评测都记录端点、模型、提示词版本、尝试次数、成功状态、耗时、输入/输出 Token 和估算费用。费用按照 AI 端点配置中的输入、输出单价计算；未配置价格时费用为空，不以 0 冒充免费。人工反馈按直接采纳、修改后采纳、拒绝和事实错误汇总，质量页展示采纳率、修改率、拒绝率、错误率和有评分反馈的平均质量分。

固定评测样例分为 `review` 和 `enrichment`。期望值支持字段相等、`score_min`、`score_max` 和 `required_nonempty`。评测运行不会进入正常审核队列，但调用本身仍进入质量统计，方便比较端点或模型变化。

## 7. 分析师增量同步

先用 CLI 创建 API Key：

```powershell
.\ainews.ps1 analyst-key create --name research-client
```

明文 Key 只在创建结果中返回一次。HTTP 调用通过 `X-API-Key` 传入。第一次同步可使用较早的 ISO-8601 时间调用 `/api/analyst/delta`，保存响应的 `next_cursor`，下一次把它原样作为 `since`。游标在查询开始前保留一秒重叠窗口，因此并发发生的修改可能在下一轮重复返回，但不会落在两个游标之间；调用方应按事件或对象 ID 幂等更新。事件关系、证据和市场窗口的更新都会推进事件修改时间。

本机外部 Agent 不需要启动 HTTP 服务，也可通过 [`CLI_DOCUMENTATION.md`](CLI_DOCUMENTATION.md) 中的 `event`、`editorial`、`publication`、`draft`、`entity`、`narrative`、`watchlist`、`alert`、`source`、`market` 和 `ai-quality` 命令完成同样的管理任务。

需要主动推送时，可创建分析师 Webhook 变更订阅。订阅对象包括事件、更正、实体、叙事和标签，可按快讯/文章及内容档案过滤。发送体为稳定的 JSON 结构，含 `schema_version`、订阅信息、`from/to/has_more` 游标和变更数组。每批通过现有持久化交付状态机发送；只有 Webhook 明确返回 2xx 才推进整数游标，失败或网络结果不确定时保留游标，避免漏数。
