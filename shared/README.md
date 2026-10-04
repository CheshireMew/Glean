# 共享目录

`content_contract.json` 是内容阶段、处理状态、配置键和导出范围的共同定义。Python 通过 `content_contract.py` 读取，前端通过 `frontend/src/contracts/content.js` 使用同一契约。修改状态时更新这份定义及相关使用处，避免在各端重复定义。

`db_base.py` 提供数据库基础接口。业务流程属于后端服务，页面展示属于前端；这个目录只放双方需要共用的定义和基础接口。

状态与数据流说明见 [数据库文档](../docs/reference/database.md)。
