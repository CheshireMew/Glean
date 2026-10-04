# 本机运行数据

现用数据库是 `data/ainews.db`，迁移锁是 `data/ainews.db.migration.lock`，数据库升级前的快照放在 `data/backups/`。数据库采用 WAL 时生成的 `-wal`、`-shm` 文件也位于数据库旁边。这个目录中的运行数据不提交到 Git。

本次整理将根目录的原数据库和 6 份历史快照搬到了这里，搬移前后核对内容哈希，数据库内容未被重建。统一启动时，三个服务的日志分别保存在 `data/logs/launcher/` 的本次启动子目录，`data/launcher.json` 记录状态、实际网页地址和日志位置。此前检查产生的日志、截图与来源样本保存在 `archive/local/verification/2026-10-04/`。

## 其他旧部署的兼容行为

默认位置是 `data/ainews.db`。如果其他旧部署只有根目录 `ainews.db`，程序会继续读取该文件，不会自动创建另一份空数据库替代它；数据库同级的 `backups/` 用于保存后续升级快照。若根目录和 `data/` 同时存在数据库，程序会明确报错，要求先确认使用哪一份。显式传给 `Database` 的路径保持不变。

整理其他旧部署时，先停止 API 和 worker，确认 SQLite 已关闭，再把数据库、已有 WAL/SHM 文件和迁移锁一起搬入 `data/`；旧 `archive/database-backups/` 中的快照可归入 `data/backups/`。本机当前已完成搬移。恢复备份时也应先停止服务，并保留当前数据库作为回退副本。
