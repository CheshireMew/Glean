# 文档索引

这里存放项目现行说明。项目入口与安装方法见 [根目录 README](../README.md)，目录分类与文件放置规则见 [项目目录职责](project-structure.md)。历史资料仅在本机 `archive/` 保存，索引是 `archive/README.md`；整个归档目录由 Git 忽略，不随仓库克隆。

| 分类 | 文档 | 内容 |
| --- | --- | --- |
| 使用 | [情报工作流](guides/intelligence-workflows.md) | 内容档案、发布频道、提醒、行情与日常操作 |
| 架构 | [技术架构](architecture/overview.md) | 后端、前端、数据模型与业务分层 |
| 架构 | [自动处理流程](architecture/automation.md) | 采集、聚合、拦截、审核与发送顺序 |
| 架构 | [事件聚合](architecture/event-clustering.md) | 多来源如何组成同一事件 |
| 接口 | [CLI](reference/cli.md) | 本机命令、JSON 输入、输出和退出码 |
| 接口 | [HTTP API](reference/api.md) | 公开读取、后台管理、来源与微信接口 |
| 参考 | [数据库](reference/database.md) | 表结构、状态流转与迁移规则 |
| 参考 | [功能清单](reference/features.md) | 前后台已有功能和模块 |
| 来源 | [当前 RSS 阅读来源](sources/curated-rss.md) | 本轮筛选后保留并接入的 5 个来源 |
| 来源 | [全部采集器说明](sources/collectors.md) | 固定站点、RSS 与公众号采集机制 |
| 运维 | [部署](operations/deployment.md) | 服务器部署步骤；当前本机验收平台为 Windows |
| 运维 | [发布检查](operations/release-checklist.md) | 正式发布时的数据、版本和回退检查 |
| 许可 | [许可说明](legal/licensing.md) | 当前授权与历史许可 |
| 许可 | [第三方说明](legal/third-party-notices.md) | 依赖、协议参考与采集内容的来源条款 |

开发提交说明保留在根目录 [CONTRIBUTING.md](../CONTRIBUTING.md)，版本变化保留在 [CHANGELOG.md](../CHANGELOG.md)。
