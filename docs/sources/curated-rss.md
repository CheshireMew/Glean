# 当前 RSS 阅读来源

更新：2026-10-04。以下是从 2,141 个订阅地址中按用户逐轮筛选后保留并接入项目的 **4 个来源**。序号沿用原清单。Acquired 的 YouTube 订阅接口返回 404/500，已按用户要求移除。

| 原序号 | 来源 | 提供的内容 | RSS / Feed 链接 | 项目运行名称 |
| ---: | --- | --- | --- | --- |
| 366 | Hacker News 中文每日摘要 | Hacker News 热门讨论与技术新闻的中文摘要。 | <https://www.supertechfans.com/cn/index.xml> | `rss__hn-chinese-digest` |
| 468 | V2EX 首页 | 中文社区的新主题，涉及编程、产品、职业与数码生活。 | <https://v2ex.com/index.xml> | `rss__v2ex-main` |
| 470 | V2EX 技术板块 | 编程、架构与开发工具讨论。 | <https://www.v2ex.com/feed/tab/tech.xml> | `rss__v2ex-tech` |
| 591 | 保持偏见播客 | 通过人物和商业故事解释科技与社会运行规则。 | <https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/663e3c95af1e22bb157dcee3> | `rss__baochipianjian` |

这 4 个来源通过现有“AI 资讯”信息流展示，可在后台 RSS 来源管理中编辑或停用。更新需要项目 worker 运行。保持偏见读取节目介绍，不下载音视频，也不生成转写。V2EX 技术板块复用原配置，其余三个为本轮新增入口。量子位的项目订阅已停用并在前台隐藏，钛媒体没有加入项目。

## 完整清单与筛选记录

| 所在位置 | 数量 | 用途 |
| --- | ---: | --- |
| 本文件 | 4 | 当前保留的阅读来源 |
| 已移除的 Acquired | 1 | 原地址保留在本机历史清单中 |
| 本机归档 `excluded.md` | 1,655 | 按阅读偏好、质量和可读性移出的地址及说明 |
| 本机归档 `slow-updates.md` | 481 | 长期未更新和低频来源及检查附录 |
| 合计 | **2,141** | 原始不重复地址仍全部保留 |

历史文件仅存放在本机 `archive/research/rss/2026-10-03/`，整个归档目录由 Git 忽略，不随仓库克隆。`final-selection.md` 保留筛选规则、历次数量变化和例外恢复说明；`quality-review.md` 保留质量评估报告，近期内容采样及后续削减记录也保留在同一目录。项目全部采集器的现行说明见 [采集来源](collectors.md)。
