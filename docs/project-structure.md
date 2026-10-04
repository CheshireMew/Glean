# 项目目录职责

目录整理于 2026-10-04。根目录保留安装依赖、环境配置、常用入口和仓库约定文件；业务代码、现行文档、运行数据和历史资料分别集中管理。

| 目录 | 放什么 | 入口或说明 |
| --- | --- | --- |
| `backend/` | API、worker、CLI、Python 业务实现和后端测试 | [后端目录](../backend/README.md) |
| `frontend/` | React 页面、组件、前端测试、Vite 配置和前端构建脚本 | [前端目录](../frontend/README.md) |
| `shared/` | 内容状态契约和数据库基础接口 | [共享目录](../shared/README.md) |
| `docs/` | 现行使用、架构、接口、来源和运维文档 | [文档索引](README.md) |
| `scripts/windows/` | Windows 服务启动实现 | [脚本说明](../scripts/README.md) |
| `data/` | 现用 SQLite 数据库、迁移锁、数据库备份 | [数据说明](../data/README.md) |
| `archive/` | 历史代码、替换素材、旧文档和来源筛选记录 | 本机 `archive/README.md`；整个目录由 Git 忽略 |
| `archive/local/` | 本机旧构建、缓存、验证日志、截图和抓取样本 | 本机保留，Git 忽略 |
| `.github/workflows/` | Windows 持续集成 | [CI 配置](../.github/workflows/ci.yml) |

## 根目录入口

双击 [start.bat](../start.bat) 或运行 [start.ps1](../start.ps1) 启动项目；它们调用 `scripts/windows/` 中的服务脚本。CLI 入口是 [glean.ps1](../glean.ps1)，旧 `ainews.ps1` 已放入本机 `archive/scripts/`。管理员本机恢复仍通过 `python -m backend.reset_admin` 调用。

`requirements.txt` 表示直接依赖范围，`requirements.lock` 和 `requirements-dev.lock` 分别记录运行与开发依赖快照。前端依赖使用 `frontend/package.json` 与 `frontend/package-lock.json`。`VERSION`、`LICENSE`、`README.md`、`CONTRIBUTING.md` 和 `CHANGELOG.md` 保留在根目录，便于仓库工具和开发者查找。

根目录 `.env.example` 是可提交的配置示例，`.env.development` 和 `.env.production` 是本机配置；前端的环境文件继续放在 `frontend/`，保持 Vite 的读取约定。

## 文件放置规则

后端新增业务实现按已有 `domain / services / infrastructure / routers / models` 分层放置，CLI 命令放入 `backend/cli/commands/`。前端功能放在 `frontend/src/` 的对应页面、组件、hook 和 API 目录，组件测试继续与组件放在一起。

新使用说明放在 `docs/guides/`，架构与处理流程放在 `docs/architecture/`，接口和结构参考放在 `docs/reference/`，运行与发布说明放在 `docs/operations/`，现用来源说明放在 `docs/sources/`。旧记录转入 `archive/`，并在归档索引说明原位置和用途。

依赖目录 `frontend/node_modules/` 保持 npm 的标准位置。Python 缓存、测试缓存和检查缓存由工具生成并由 Git 忽略；本次检查禁用了项目内 Python 字节码写入，Ruff 缓存放在 `D:\Tools\Temp`。正式前端发布产物仍使用 `frontend/dist/`，现有无发布清单的旧产物已归档，本次没有重新构建发布文件。
