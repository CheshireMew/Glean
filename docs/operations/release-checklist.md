# 发布检查清单

这份清单用于正式发布或服务器切换，不会自动生成安装包。

## 代码与依赖

- 确认 `requirements.txt` 的直接依赖范围与 `requirements.lock` 一致
- 使用 `npm ci` 验证 `frontend/package-lock.json`
- 确认根目录 `VERSION`、`frontend/package.json`、`frontend/package-lock.json` 和 `CHANGELOG.md` 使用同一版本
- 检查根目录 `LICENSE`、[许可说明](../legal/licensing.md) 和[第三方声明](../legal/third-party-notices.md)

## 自动验证

```powershell
python -m compileall -q backend
python -m ruff check backend shared --select F
python -m unittest discover -s backend/tests -v
Set-Location frontend
npm run lint
npm test
npm run build:release
npm run verify:release
```

Windows CI 必须通过。当前项目只验收 Windows；Linux 部署流程需要在预发布主机另行验证。

## 数据与运行时

- 备份现有数据库并验证备份可打开
- 确认升级启动后 `schema_migrations` 为预期版本，迁移前自动快照已生成
- 确认 `PRAGMA foreign_keys` 返回 `1`
- 确认只有一个 worker 持有租约，旧的 `processing` 命令没有永久滞留
- 确认同版本数据库重复启动不会进入迁移、规范化、种子写入或 FTS 重建路径
- 确认内容管线租约丢失会取消任务，过期任务的数据库提交被拒绝
- 确认审核积压在单周期批次上限后按短间隔继续追尾；剩余量读取失败必须显示为未知，不能记录为 0
- 确认 `/health/live` 和 `/health/ready` 均返回 200；启用自动流水线时，`/health/pipeline` 也必须返回 200

## 功能抽查

- 各运行一次 RSS 与浏览器来源，确认失败时后台显示真实错误
- 验证事件聚合、黑名单、AI 审核与默认内容档案
- 用超长正文验证 Telegram 分片；模拟失败后只续发未完成分片
- 验证稿件、更正、实时内容、预警和订阅重试回到原业务收尾；多渠道部分成功不得提前完成
- 首次发送后修改内容、模板或目标，验证恢复使用原计划，报告保持原始快照；订阅发送成功但游标收尾中断后不得重发或跳过变更
- 验证超过两批的混合预警积压及尾批；不满足资格的策略不能遮住可发送匹配
- 验证草稿引用下的过期清理、删除、恢复和黑名单转换；未完成稿件有明确保护，历史快照可读取
- 验证无内容日报不会占用当天发送日期
- 验证公开文章/AI 资讯翻页、搜索失败重试和移动端搜索；日报接口和结构化数据单独验证，当前公开页面隐藏快讯和日报入口
- 验证公开流刷新会更新同 ID、移除已撤下内容，并保留当前已加载深度
- 验证系统、Telegram、AI 和审核配置读取失败时表单不可保存；仪表盘统计失败时显示不可用而不是 0
- 仅使用键盘完成公开页标签切换、链接菜单导航、Escape 关闭和焦点返回
- 验证旧登录令牌在管理员账号或密码修改后失效
- Windows 启动日志验证单文件、总量、运行数量和保留天数预算；超限时不启动新服务，先查看只读清理候选，取得删除授权后再处置

## 上线与回退

- 先启动 API，再启动 worker，最后检查 readiness
- 只部署刚刚通过 `verify:release` 的全新 `dist`；上线后核对后端健康接口、页面元数据和发布清单的版本一致
- 观察请求 ID、worker 心跳、爬虫日志和交付操作状态
- 若迁移或启动失败，停止新进程，保留失败现场日志，使用已验证的迁移前备份恢复
