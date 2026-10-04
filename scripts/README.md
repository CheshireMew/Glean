# Windows 启动脚本

常用入口保留在项目根目录：双击 `start.bat` 或执行 `.\start.ps1`。[windows/start-services.ps1](windows/start-services.ps1) 调用 [统一启动器](windows/launcher.py)，在一个窗口中检查依赖、启动 API、worker 和网页并等待就绪。服务输出保存在本机 `data/logs/launcher/`，失败时直接显示错误和日志位置。

| 脚本 | 用途 | 是否需要 |
| --- | --- | --- |
| [start.ps1](../start.ps1) | 根目录的一键启动入口，转交给下面的启动实现 | 保留；平时双击 `start.bat` 也会调用它 |
| [start-services.ps1](windows/start-services.ps1) | 将参数交给统一启动器 | 保留；由 `start.ps1` 自动调用 |
| [run_backend.ps1](windows/run_backend.ps1) | 单独启动提供数据与管理接口的 API，端口 8000 | 保留；用于单独调试后端 |
| [run_worker.ps1](windows/run_worker.ps1) | 启动采集和自动处理任务 | 保留；自动更新信息流需要它 |
| [run_frontend.ps1](windows/run_frontend.ps1) | 单独启动网页服务，优先 5173，自动跳过不可用端口 | 保留；用于单独调试网页 |
| [glean.ps1](../glean.ps1) | 调用项目 CLI，查看状态或管理来源、内容和配置 | 保留；手动操作及外部 Agent 使用 |

启动关系为 `start.bat → start.ps1 → start-services.ps1 → launcher.py`，三个 `run_*.ps1` 是独立调试入口；CLI 独立使用 `glean.ps1`。统一启动器为本次子进程设置 Windows 进程作业，关闭窗口时一并收回；正常停止还会先通知后端和 worker 完成退出清理。

统一启动后按 `Ctrl+C` 停止全部服务。启动器会检查子进程是否提前退出，避免某个服务失败后仍等待完整超时。网页端口通过实际 Node.js 监听检查选择，并同步传给本次后端的允许来源和本机站点地址。后端端口占用或已有 worker 时只报告错误，不会停止原进程。

旧 `ainews.ps1` 已归档到本机 `archive/scripts/ainews.ps1`，只保留历史文件，不再作为运行入口。后续命令统一使用 `glean.ps1`。

这些脚本根据自身位置计算项目根目录，因此从其他工作目录调用也能找到项目。单独启动时，从项目根目录运行：

```powershell
.\scripts\windows\run_backend.ps1
.\scripts\windows\run_worker.ps1
.\scripts\windows\run_frontend.ps1
```

`.\start.ps1 -CheckOnly` 只检查启动条件，不启动服务。CLI 仍使用根目录 `glean.ps1`；前端构建和发布核对脚本继续放在 `frontend/scripts/`，便于 npm 配置直接引用。
