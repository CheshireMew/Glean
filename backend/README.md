# 后端目录

从项目根目录运行后端模块。API 入口为 `python -m uvicorn backend.main:app`，worker 为 `python -m backend.worker`，CLI 为 `python -m backend.cli`。

| 路径 | 职责 |
| --- | --- |
| `main.py` | FastAPI 入口、请求生命周期与健康接口 |
| `worker.py` | 定时采集、命令处理和自动内容流水线 |
| `reset_admin.py` | 管理员账户的本机恢复入口 |
| `cli/` | 命令注册、参数、结构化输出与各类管理命令 |
| `app/composition.py` | 应用服务及依赖装配 |
| `app/core/` | 配置、异常、日志、时间与通用运行工具 |
| `app/domain/` | 领域规则、状态和来源定义 |
| `app/models/` | API 请求与响应模型 |
| `app/routers/` | HTTP 接口路由 |
| `app/services/` | 应用服务与业务流程 |
| `app/infrastructure/` | SQLite、仓储、采集传输、站点解析和微信网关 |
| `tests/` | 后端行为和契约测试 |

旧实现已统一放到本机根目录 `archive/code/`，整个归档目录由 Git 忽略，后端不再单独维护归档目录。详细说明见 [技术架构](../docs/architecture/overview.md)、[API](../docs/reference/api.md) 与 [CLI](../docs/reference/cli.md)。
