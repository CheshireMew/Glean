# Glean 自动化流程说明

本文档只描述当前运行中的自动化链路。

## 总览

系统启动后会同时运行两个后台循环：

1. `scheduler_loop`
   负责按爬虫配置定时启动抓取任务。

2. `auto_pipeline_loop`
   负责在工作时间内串行推进内容处理。

工作时间判断来自系统时区配置，默认窗口为北京时间 08:00 到 23:59。运行开关、起止时间、循环间隔、审核批大小和内容补充批大小都可以在系统设置中调整；窗口跨午夜时也能正确运行。非工作时间不会继续跑自动处理链路。

API 与 worker 是两个独立进程。worker 启动时必须取得唯一运行租约，并持续刷新心跳；第二个 worker 无法取得租约时会直接退出。`/health/ready` 只判断 API 能否接流量，`/health/pipeline` 额外检查 worker 心跳。

## 自动处理链路

`auto_pipeline_loop` 的实际执行顺序如下：

1. 等待当前抓取任务结束
2. 对 `news` 中的 `news` 类型来源做自动事件聚合
3. 对 `news` 中的 `article` 类型来源做自动事件聚合
4. 对 `archive_entries` 做黑名单拦截
5. 对 `review_entries` 的待审核事件执行 AI 审核，并对入选事件做带引用的二次补充
6. 到达日报时间时先生成并发送平衡日报，再实时发送默认内容档案中尚未发送的入选内容

API 进程入口是 [backend/main.py](backend/main.py)，自动链路由 [backend/worker.py](backend/worker.py) 启动，并由 [automation_runtime_service.py](backend/app/services/automation_runtime_service.py) 调度。

## 步骤 1：抓取与入池

爬虫抓到的新内容先写入 `news` 表。

- `news.stage = incoming`
- `news.type` 标识内容类型，当前使用 `news` 和 `article`
- 这一步只负责采集，不做归档、审核或推送

## 步骤 2：自动事件聚合

自动聚合会读取 `news` 中最近时间窗口内、仍可处理的来源报道：

1. 相似报道组成一个 `content_events` 事件。
2. 所有报道写入 `event_sources`，不会因相似而删除。
3. 信息最完整的报道成为规范来源，其余报道保留自己的标题、正文和链接。
4. 来源统一更新为 `news.stage = archived`，规范事件进入 `archive_entries`。
5. 后续新报道可以加入已有事件。

## 步骤 3：黑名单拦截

黑名单处理只操作 `archive_entries` 中 `archive_status = ready` 的内容。

处理结果只有两种：

1. 命中黑名单
   - `archive_status = blocked`
   - 记录 `block_reason`

2. 未命中黑名单
   - 写入 `review_entries`
   - `review_status = pending`
   - 同时把归档记录改为 `archive_status = reviewed`

这一步的职责是把“可继续审核的内容”从归档池推进到审核池，而不是在多个临时表之间来回复制。

## 步骤 4：AI 审核

AI 审核分批认领 `review_entries` 中 `review_status = pending` 的事件，认领期间状态为 `processing`。每个事件会按所有已启用的内容档案分别生成审核任务；各档案独立定义审核标准、最低分、补充要求和日报配额，默认档案的结果用于日报和公开内容。失败条目最多自动尝试三次，错误留在原条目中，之后可人工重新入队。

审核结果写回同一张表；单条调用失败只记录 `review_error`，不会中断同批其他事件。入选事件会根据 `event_sources` 中的全部来源生成 `enriched_summary / enriched_impact / enriched_background`，引用只能指向实际来源。

- 通过：`review_status = selected`
- 不通过：`review_status = discarded`

同时补充以下字段：

- `review_reason`
- `review_score`
- `review_category`
- `review_summary`
- `review_tags`

也就是说，审核前后的内容都留在同一个审核池中，只通过 `review_status` 区分阶段。

## 步骤 5：Telegram 实时发送

自动发送只读取默认内容档案中满足以下条件的内容：

- `review_status = selected`
- `delivery_status = pending`
- 在最近时间窗口内

发送成功后：

- `delivery_status = sent`
- `delivered_at` 写入时间
- `push_logs` 记录发送日志

每次交付先写入 `delivery_operations` 和 `delivery_parts`。明确成功的分片保存 Telegram 消息 ID，明确失败的分片标记为 `failed`，网络中断等无法判断是否已送达的分片标记为 `unknown`，整体状态变为 `needs_attention`。内容只有在全部分片明确成功后才会变成 `delivery_status = sent`；重复提交相同操作键不会重复发送已成功分片。

## 每日日报

`auto_pipeline_loop` 按系统设置中的循环间隔检查日报时间；快讯和文章各自每天最多自动发送一次。后台也可以通过以下接口强制触发：

- `POST /api/delivery/daily/news`
- `POST /api/delivery/daily/article`

手动触发必须传稳定的 `operation_key`。日报正文与每条内容都会在发送前按 Telegram 的 4096 字符限制拆分，完整正文不会因单条过长而被静默截断。当天没有可发送内容时不会写入“已发送日期”，因此稍后有内容进入时仍可正常生成日报。

日报生成逻辑会：

1. 从 `review_entries` 读取最近 24 小时内已选入的内容
2. 按分数、多来源印证、栏目上限和来源上限编排
3. 发送到 Telegram
4. 发送成功后写入 `daily_reports` 与 `daily_report_items`，并将对应内容标记为公开可见

每次成功发布使用唯一 `publication_key`，日报条目同时冻结标题、链接、来源、摘要、补充内容与引用；后来删除或修改审核条目不会改变历史日报。因此，`daily_reports` 是不可变的发布历史，不是实时发送队列。

## 运行中会看到的核心状态

### `news.stage`

- `incoming`
- `archived`

### `archive_entries.archive_status`

- `ready`
- `blocked`
- `reviewed`

### `review_entries.review_status`

- `pending`
- `processing`
- `selected`
- `discarded`

### `review_entries.delivery_status`

- `pending`
- `sent`
- `expired`

### `delivery_operations.status`

- `pending`：还有待发送分片
- `sending`：有分片正在发送
- `failed`：至少一个分片明确失败，可重试未完成分片
- `needs_attention`：至少一个分片结果不确定，必须人工确认后重试
- `sent`：全部分片明确成功

### 抓取运行状态

抓取命令带 worker 所有者、过期时间和尝试次数。worker 重启时会把租约已过期的 `processing` 命令恢复为 `pending`，把被中断的运行状态标记为错误。爬虫异常会保留原始错误和运行日志，不会再以空结果冒充成功；等待抓取完成超时也会让自动流水线失败并记录原因。

## 数据流简图

```text
news (incoming)
    ↓ 事件聚合
content_events + event_sources
    ↓ 规范事件归档
news (archived)
    ↓
archive_entries (ready)
    ↓ 黑名单拦截
archive_entries (blocked | reviewed)
    ↓
review_entries (pending)
    ↓ AI 审核
review_entries (selected + enriched | discarded)
    ↓ 到点生成日报，再发送尚未覆盖的实时内容
review_entries (delivery_status = sent)
    ↓
daily_reports + daily_report_items
```

## 判断自动流程是否正常的最小检查点

1. `news` 是否持续写入新内容
2. `archive_entries` 是否出现新的 `ready` 或 `reviewed` 记录
3. `review_entries` 是否出现新的 `pending / selected / discarded`
4. `delivery_operations` 是否最终进入 `sent`，是否存在需要人工确认的 `needs_attention`
5. `daily_reports` 是否在设定时间后产生当天记录
6. `/health/ready` 是否返回 200；需要自动流水线时，再确认 `/health/pipeline` 返回 200
