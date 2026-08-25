# AINews Agent CLI

AINews CLI 是供 Codex、Claude Code 等外部 Agent 使用的本机管理入口。它直接调用项目现有的 application service 和 SQLite 数据库，不要求 FastAPI 监听端口，也不会在产品中启动 Agent、聊天界面或模型编排层。

## 调用方式

推荐从项目根目录运行：

```powershell
.\ainews.ps1 version
```

包装脚本优先使用 `D:\Tools\Python310\python.exe`，不存在时回退到 `python`。也可以直接调用：

```powershell
python -m backend.cli version
```

全局选项必须放在命令之前：

```powershell
.\ainews.ps1 --env development --format json --pretty content overview --kind news
```

- `--env development|production|test`：选择环境文件，默认 `development`。
- `--format json|text`：默认 `json`；只有 JSON 格式属于稳定的 Agent 接口。
- `--pretty`：缩进 JSON。
- `--debug`：把未预期错误的堆栈写入 stderr，不污染 stdout。

## 输出契约

正常命令的 stdout 始终只有一个 JSON 文档：

```json
{
  "contract_version": 1,
  "success": true,
  "command": "content.overview",
  "data": {},
  "message": "操作成功",
  "error": null,
  "meta": {
    "app_version": "0.1.0",
    "environment": "development",
    "duration_ms": 12.5
  }
}
```

业务日志和长任务进度写入 stderr。Agent 不应通过中文 `message` 判断结果，应检查进程退出码、`success`、`error.type` 和 `data`。

| 退出码 | 含义 |
|---:|---|
| `0` | 命令成功；异步爬虫命令已被接受也属于成功 |
| `1` | 未预期的内部错误 |
| `2` | 命令参数、JSON 或 Pydantic 模型校验失败 |
| `3` | 指定资源不存在 |
| `4` | 业务冲突或当前状态拒绝操作 |
| `5` | 数据库、worker、配置或外部依赖未就绪 |
| `6` | 任务已执行但未完整完成，例如交付失败或需要人工确认 |
| `124` | 等待爬虫终态超时 |
| `130` | 操作者中断 |

## 首次初始化和状态

`version`、`capabilities` 和缺库状态检查不会创建 SQLite 文件。其他命令只接受当前结构版本的数据库；缺失或过期时会提示显式初始化：

```powershell
.\ainews.ps1 system status
.\ainews.ps1 system init
```

`system init` 会执行生产配置校验、创建或追加式迁移数据库、为旧数据库生成迁移前备份、迁移管理员密码并初始化爬虫运行状态。普通查询不会自动迁移。

`system status` 默认以数据库/API 就绪度决定退出码，同时返回 worker 信息；加 `--pipeline` 后，worker 未就绪也返回退出码 `5`。

## 机器发现

Agent 应先读取能力清单，而不是从帮助文本猜参数：

```powershell
.\ainews.ps1 capabilities
.\ainews.ps1 capabilities delivery.send
```

返回内容包含命令 ID、实际调用路径、参数、是否需要数据库/worker/`--yes`，以及结构化输入和输出 Schema。

## 结构化 JSON 输入

配置、内容档案、RSS、管理员凭据和手动交付通过 `--input` 读取 UTF-8 JSON 对象：

```powershell
.\ainews.ps1 config ai set --input D:\Config\ainews-ai.json
Get-Content -Raw D:\Config\ainews-telegram.json | .\ainews.ps1 config telegram set --input -
```

使用 `--input -` 时 stdin 必须已经连接到管道；CLI 不会停下来等待交互输入。AI 和 Telegram 查询会继续隐藏密钥，掩码 `••••••••` 在保存时表示保留当前密钥。新建分析 API Key 的明文只在创建结果中返回一次。

## 命令目录

### 系统与配置

```powershell
.\ainews.ps1 system status [--pipeline]
.\ainews.ps1 system init
.\ainews.ps1 system maintenance [--force] --yes
.\ainews.ps1 system credentials --input credentials.json --yes

.\ainews.ps1 config system get|set
.\ainews.ps1 config timezone get|set
.\ainews.ps1 config schedule get|set
.\ainews.ps1 config automation get|set
.\ainews.ps1 config telegram get|set|test
.\ainews.ps1 config ai get|set|test
.\ainews.ps1 config review get|set --kind news|article
```

`system credentials` 的 JSON 使用 `current_password`、可选的 `new_username` 和 `new_password`。管理员账号由环境变量管理时，现有 service 会拒绝数据库修改。

### 内容和公开读取

```powershell
.\ainews.ps1 content overview --kind news
.\ainews.ps1 content stats --kind article
.\ainews.ps1 content list --scope incoming|events|archive|blocked|review|selected|discarded
.\ainews.ps1 content export --scope selected --output D:\Exports\selected.json
.\ainews.ps1 content delete --scope incoming|archive|review --id 12 --yes
.\ainews.ps1 content restore --scope archive|blocked --id 12 --yes
.\ainews.ps1 content requeue --id 12
.\ainews.ps1 content requeue-all --kind news
.\ainews.ps1 content clear-decisions --kind news --yes
.\ainews.ps1 content restore-blocked-all --kind news

.\ainews.ps1 public content --stream briefs|longform [--publication daily-briefs]
.\ainews.ps1 public reports [--kind news|article] [--publication daily-briefs]
.\ainews.ps1 public search --query "稳定币" --kind all [--publication daily-briefs]
.\ainews.ps1 public rss --kind news [--publication daily-briefs]
```

列表命令支持 `--page`、`--limit`、`--source`、`--keyword` 和 `--kind`。导出支持日期、关键词、来源、内容类型和字段过滤；默认拒绝覆盖已有文件，只有 `--overwrite` 才会替换。成功结果返回绝对路径、条数、字节数和 SHA-256。

### 爬虫和流水线

```powershell
.\ainews.ps1 scraper list
.\ainews.ps1 scraper status [name]
.\ainews.ps1 scraper configure <name> --interval 60 --limit 20
.\ainews.ps1 scraper run <name> --items 10
.\ainews.ps1 scraper run <name> --items 10 --wait --timeout 600
.\ainews.ps1 scraper stop <name> [--wait]
.\ainews.ps1 scraper command <command-id>
.\ainews.ps1 scraper wait <command-id> --timeout 600

.\ainews.ps1 pipeline cluster --hours 24 --threshold 0.5 --kind news
.\ainews.ps1 pipeline similarity <first-id> <second-id>
.\ainews.ps1 pipeline blocklist-apply --hours 24 --kind news
.\ainews.ps1 pipeline review --hours 8 --kind news
.\ainews.ps1 pipeline cycle --yes
```

`scraper run`、`scraper stop` 和 `scraper wait` 执行前都会统一检查 worker 租约、版本和就绪状态；worker 未就绪时返回退出码 `5`，不会继续入队或无效等待。普通 `scraper run` 在命令入队后返回；`--wait` 会继续等待实际抓取进入 `idle` 或 `error`，而不是只等待命令被领取。流水线命令沿用 `content-pipeline` 租约，已有任务执行时不会并行运行。

### 黑名单、档案和资源

```powershell
.\ainews.ps1 blocklist list --kind news
.\ainews.ps1 blocklist add "空投骗局" --match-type contains --kind news
.\ainews.ps1 blocklist remove 12 --yes

.\ainews.ps1 profile list [--kind news|article]
.\ainews.ps1 profile save default-news --input profile.json
.\ainews.ps1 rss list
.\ainews.ps1 rss create --input source.json
.\ainews.ps1 rss update 12 --input source.json
.\ainews.ps1 rss delete 12 --yes

.\ainews.ps1 analyst-key list
.\ainews.ps1 analyst-key create --name research-agent --notes "本机研究任务"
.\ainews.ps1 analyst-key enable|disable 12
.\ainews.ps1 analyst-key delete 12 --yes
```

`profile save` 的命令行 slug 与 JSON 中的 `slug` 必须一致。RSS 更新使用命令行 ID 定位记录；运行中的 RSS 抓取任务仍由现有 service 阻止修改或删除。

### 事件证据与人工编辑

```powershell
.\ainews.ps1 event get 42
.\ainews.ps1 event evidence 42 108 --input evidence.json
.\ainews.ps1 event update add 42 --input event-update.json
.\ainews.ps1 event fact add 42 --input event-fact.json
.\ainews.ps1 event fact update 7 --input event-fact-update.json
.\ainews.ps1 event relation add 42 --input event-relation.json
.\ainews.ps1 event classify 42
.\ainews.ps1 intelligence classify [--hours 168] [--limit 500]
.\ainews.ps1 editorial get 77
.\ainews.ps1 editorial update 77 --input editorial-edit.json
.\ainews.ps1 editorial restore 77 3
```

`event evidence` 维护来源角色、证据组、引用源、独立性、核验状态和说明。关键事实可引用同事件来源并分别控制核验状态、置信度与公开性；事件关系支持相关、原因、结果、后续、矛盾与同一故事。自动识别使用实体名称、符号、别名和叙事关键词，人工关系不会被规则覆盖。`editorial update` 每次都会生成新修订；`editorial restore` 把历史修订恢复为一个新的当前版本，不覆盖修订历史。

### 发布频道、渠道、草稿与更正

```powershell
.\ainews.ps1 publication list
.\ainews.ps1 publication update 1 --input publication.json
.\ainews.ps1 channel list
.\ainews.ps1 channel save [--id 2] --input channel.json
.\ainews.ps1 channel test 2 --yes
.\ainews.ps1 draft list [--status draft|scheduled|publishing|published|cancelled]
.\ainews.ps1 draft create --input draft.json
.\ainews.ps1 draft update 12 --input draft-update.json
.\ainews.ps1 draft preview 12
.\ainews.ps1 draft publish 12 --yes
.\ainews.ps1 draft publish-due --limit 100 --yes
.\ainews.ps1 correction list
.\ainews.ps1 correction create --input correction.json
.\ainews.ps1 correction publish 9 --yes
```

发布频道可设置公开路径、RSS、摘要频率、时间、时区、模板和投递目标。模板支持 `title_prefix`、`title_suffix`、`intro`、`footer` 和周报 `weekday`。渠道类型支持 `telegram`、`email`、`discord`、`slack` 和 `webhook`，具体配置见 [`INTELLIGENCE_WORKFLOWS.md`](INTELLIGENCE_WORKFLOWS.md)。`draft preview` 使用实际发布排版器但不发送或创建交付记录。草稿和更正都使用持久化交付状态机；重试不会重新发送已经确认成功的分段。

### 实体、叙事、关注列表和提醒

```powershell
.\ainews.ps1 entity list [--type asset] [--query BTC]
.\ainews.ps1 entity save [--id 1] --input entity.json
.\ainews.ps1 entity attach 42 --input event-entity.json
.\ainews.ps1 narrative list [--enabled-only]
.\ainews.ps1 narrative save [--id 3] --input narrative.json
.\ainews.ps1 narrative attach 42 --input event-narrative.json
.\ainews.ps1 watchlist list
.\ainews.ps1 watchlist save [--id 5] --input watchlist.json
.\ainews.ps1 alert list
.\ainews.ps1 alert save [--id 8] --input alert.json
.\ainews.ps1 alert evaluate [--id 8] [--hours 24]
.\ainews.ps1 alert matches [--status pending] [--limit 200]
.\ainews.ps1 alert deliver --limit 200 --yes
.\ainews.ps1 analyst-subscription list
.\ainews.ps1 analyst-subscription create --input subscription.json
.\ainews.ps1 analyst-subscription update 3 --input subscription-update.json
.\ainews.ps1 analyst-subscription deliver [--id 3] --yes
```

提醒条件、静默时段和每日/每周汇总字段见 [`INTELLIGENCE_WORKFLOWS.md`](INTELLIGENCE_WORKFLOWS.md)。提醒规则引用的关注列表、实体、叙事和投递渠道必须已经存在。分析师订阅只使用 Webhook，只有远端确认送达后才推进变更游标；投递命令需要 `--yes`。

### 来源运营与市场影响

```powershell
.\ainews.ps1 source list
.\ainews.ps1 source update blockbeats-news --input source.json
.\ainews.ps1 source snapshot [--key blockbeats-news] [--hours 24]
.\ainews.ps1 source incidents [--status open] [--limit 200]
.\ainews.ps1 source incident update 6 --input incident-status.json
.\ainews.ps1 market instrument list
.\ainews.ps1 market instrument save [--id 2] --input instrument.json
.\ainews.ps1 market event 42
.\ainews.ps1 market refresh 42
.\ainews.ps1 market snapshot 42 2 --input snapshot.json
.\ainews.ps1 market expectation 42 2 --input expectation.json
```

来源 `enabled=false` 会从定时采集调度中排除，但不阻止操作者显式执行补采命令。行情提供方支持 `binance` 和 `manual`；自动刷新只请求已经到达观察时间且尚未保存的窗口。

### AI 质量与固定评测

```powershell
.\ainews.ps1 ai-quality summary [--days 30]
.\ainews.ps1 ai-quality invocations [--stage review] [--provider primary] [--profile daily-briefs]
.\ainews.ps1 ai-quality case list [--enabled]
.\ainews.ps1 ai-quality case save [--id 4] --input evaluation-case.json
.\ainews.ps1 ai-quality evaluate [--input evaluation-run.json] --yes
```

`ai-quality evaluate` 会实际调用已配置的 AI 端点，因此需要 `--yes`。评测样例不会进入正常审核队列，但调用耗时、Token 和费用仍会记录。

### 旧版 Telegram 交付

```powershell
.\ainews.ps1 delivery daily --kind news --operation-key daily:news:20260824:agent --yes
.\ainews.ps1 delivery send --input delivery.json --yes
.\ainews.ps1 delivery retry --operation-key manual:news:20260824:agent --yes
.\ainews.ps1 delivery operations --limit 50 [--status failed]
.\ainews.ps1 delivery operation --operation-key manual:news:20260824:agent
.\ainews.ps1 delivery test --yes
```

手动发送 JSON 与 HTTP API 使用同一模型：

```json
{
  "entries": [
    {"scope": "selected", "id": 12},
    {"scope": "archive", "id": 18}
  ],
  "operation_key": "manual:news:20260824:agent"
}
```

CLI 不自动生成操作键。调用方必须在逻辑任务级保存稳定的 `operation_key`，相同任务重试时继续使用同一值。`failed`、`needs_attention`、`pending` 或 `in_progress` 会返回退出码 `6`，并在 `data` 中保留持久化操作状态。

## 高影响操作

CLI 从不进行交互式 y/N 询问。以下操作缺少 `--yes` 时会在调用 service 前以退出码 `2` 拒绝：

- 删除内容、黑名单、RSS 源或分析 API Key；
- 清空审核结果或恢复归档事件；
- 修改管理员凭据和执行数据库维护；
- 运行包含 Telegram 交付的完整流水线；
- Telegram 测试、日报、手动发送和重试；
- 渠道测试、草稿发布、到期草稿发布、更正发布和提醒投递；
- 固定 AI 评测。
- 分析师 Webhook 变更投递。

`--yes` 只确认这一次命令，不改变项目配置，也不会绕过 service 自身的状态、事务、租约或幂等检查。
