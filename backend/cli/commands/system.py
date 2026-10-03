from __future__ import annotations

from pathlib import Path

from backend.app.models.operations import CredentialsUpdateRequest

from ..errors import CLIUnavailableError
from ..models import CommandResult, CommandSpec
from ..registry import arg, capability_contract


def version_handler(ctx, args, payload):
    version_file = ctx.project_root() / "VERSION"
    return {"version": version_file.read_text(encoding="utf-8").strip()}


def capabilities_handler(ctx, args, payload):
    return capability_contract(ctx.registry, args.command)


def status_handler(ctx, args, payload):
    from backend.app.infrastructure.sqlite.sqlite_migration_plan import SCHEMA_VERSION

    database = ctx.database
    db_path = Path(database.db_path).resolve()
    if not db_path.exists():
        data = {
            "database": {
                "ready": False,
                "exists": False,
                "path": str(db_path),
                "required_schema_version": SCHEMA_VERSION,
            },
            "pipeline": {"ready": False, "reason": "数据库尚未初始化"},
        }
        raise CLIUnavailableError("数据库尚未初始化", data=data)

    api_ready, api_payload = ctx.services.runtime_health.api_readiness()
    pipeline_ready, pipeline_payload = ctx.services.runtime_health.pipeline_readiness()
    data = {
        "database": {
            "ready": api_ready,
            "exists": True,
            "path": str(db_path),
            "required_schema_version": SCHEMA_VERSION,
            **api_payload,
        },
        "pipeline": {"ready": pipeline_ready, **pipeline_payload},
    }
    if not api_ready or (args.pipeline and not pipeline_ready):
        raise CLIUnavailableError("Glean 尚未就绪", data=data)
    return CommandResult(data=data, message="Glean 状态查询成功")


def init_handler(ctx, args, payload):
    from backend.app.infrastructure.database import init_database
    from backend.app.infrastructure.sqlite.sqlite_migration_plan import SCHEMA_VERSION

    database_path = Path(ctx.database.db_path).resolve()
    existed = database_path.exists()
    ctx.settings.validate()
    init_database()
    ctx.services.credentials.initialize()
    ctx.services.scraper_runtime_state.ensure_runtime_initialized()
    ctx.database.assert_schema_current()
    return CommandResult(
        data={
            "database_path": str(database_path),
            "created": not existed,
            "schema_version": SCHEMA_VERSION,
        },
        message="数据库已初始化并升级到当前结构",
    )


async def maintenance_handler(ctx, args, payload):
    result = await ctx.services.data_maintenance.run_if_due(force=args.force)
    return CommandResult(data=result, message="数据库维护检查已完成")


def credentials_handler(ctx, args, payload):
    current_username = ctx.services.auth().get_admin_credentials().username
    result = ctx.services.credentials.update_credentials(
        current_username,
        payload["current_password"],
        payload.get("new_username"),
        payload.get("new_password"),
    )
    return CommandResult(data=None, message=result["message"])


def command_specs():
    return [
        CommandSpec("version", ("version",), "显示源码版本", version_handler, database_mode="none"),
        CommandSpec(
            "capabilities",
            ("capabilities",),
            "输出机器可读的 CLI 命令与 Schema",
            capabilities_handler,
            arguments=(arg("command", nargs="?", help="可选的命令 ID"),),
            database_mode="none",
        ),
        CommandSpec(
            "system.status",
            ("system", "status"),
            "检查数据库、worker 和流水线状态",
            status_handler,
            arguments=(arg("--pipeline", action="store_true", help="worker 未就绪时返回非零退出码"),),
            database_mode="none",
        ),
        CommandSpec(
            "system.init",
            ("system", "init"),
            "显式创建或迁移数据库并初始化运行状态",
            init_handler,
            database_mode="init",
        ),
        CommandSpec(
            "system.maintenance",
            ("system", "maintenance"),
            "按保留策略清理并优化数据库",
            maintenance_handler,
            arguments=(arg("--force", action="store_true", help="忽略维护周期立即执行"),),
            requires_yes=True,
        ),
        CommandSpec(
            "system.credentials",
            ("system", "credentials"),
            "修改数据库管理的管理员凭据",
            credentials_handler,
            input_model=CredentialsUpdateRequest,
            input_required=True,
            requires_yes=True,
        ),
    ]
