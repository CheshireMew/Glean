# Windows 启动脚本

常用入口保留在项目根目录：双击 `start.bat` 或执行 `.\start.ps1`。完整启动实现在 [windows/start-services.ps1](windows/start-services.ps1)，依次检查依赖、启动 API、worker 和前端并等待服务就绪。

| 脚本 | 用途 | 是否需要 |
| --- | --- | --- |
| [start.ps1](../start.ps1) | 根目录的一键启动入口，转交给下面的启动实现 | 保留；平时双击 `start.bat` 也会调用它 |
| [start-services.ps1](windows/start-services.ps1) | 检查依赖和端口，依次启动三个服务并等待就绪 | 保留；由 `start.ps1` 自动调用 |
| [run_backend.ps1](windows/run_backend.ps1) | 启动提供数据与管理接口的 API，端口 8000 | 保留；由完整启动流程调用，也可单独启动 |
| [run_worker.ps1](windows/run_worker.ps1) | 启动采集和自动处理任务 | 保留；自动更新信息流需要它 |
| [run_frontend.ps1](windows/run_frontend.ps1) | 启动网页开发服务，端口 5173 | 保留；当前本机启动方式需要它 |
| [glean.ps1](../glean.ps1) | 调用项目 CLI，查看状态或管理来源、内容和配置 | 保留；手动操作及外部 Agent 使用 |

这些脚本本身只负责选择 Python、切换目录、检查启动条件和调用程序，实际业务在后端与前端代码中。启动关系为 `start.bat → start.ps1 → start-services.ps1 → 三个 run_*.ps1`；CLI 独立使用 `glean.ps1`。

旧 `ainews.ps1` 已归档到本机 `archive/scripts/ainews.ps1`，只保留历史文件，不再作为运行入口。后续命令统一使用 `glean.ps1`。

这些脚本根据自身位置计算项目根目录，因此从其他工作目录调用也能找到项目。单独启动时，从项目根目录运行：

```powershell
.\scripts\windows\run_backend.ps1
.\scripts\windows\run_worker.ps1
.\scripts\windows\run_frontend.ps1
```

`.\start.ps1 -CheckOnly` 只检查启动条件，不启动服务。CLI 仍使用根目录 `glean.ps1`；前端构建和发布核对脚本继续放在 `frontend/scripts/`，便于 npm 配置直接引用。
