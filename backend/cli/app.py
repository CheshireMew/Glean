from __future__ import annotations

import argparse
import asyncio
from contextlib import redirect_stdout
from datetime import date, datetime
import inspect
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
import traceback
from typing import Any, Sequence

from pydantic import BaseModel, ValidationError as PydanticValidationError

from . import CLI_CONTRACT_VERSION
from .errors import CLIError, CLIUsageError, CLIUnavailableError
from .models import CLIEnvelope, CLIErrorBody, CLIMeta, CommandContext, CommandResult, CommandSpec
from .registry import build_parser, load_command_specs


def _source_version() -> str:
    path = Path(__file__).resolve().parents[2] / "VERSION"
    try:
        return path.read_text(encoding="utf-8").strip() or "unreleased"
    except OSError:
        return "unreleased"


def _environment() -> str:
    return (os.getenv("AINEWS_ENV") or os.getenv("ENV") or "development").strip().lower()


def _json_default(value: Any):
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, set):
        return sorted(value)
    return str(value)


def _load_input(spec: CommandSpec, args: argparse.Namespace) -> dict[str, Any] | None:
    if spec.input_model is None:
        return None
    input_path = getattr(args, "input", None)
    if not input_path:
        if spec.input_required:
            raise CLIUsageError("必须通过 --input 提供 JSON")
        return None
    try:
        if input_path == "-":
            if sys.stdin.isatty():
                raise CLIUsageError("--input - 需要从 stdin 传入 JSON，拒绝等待交互输入")
            payload = json.load(sys.stdin)
        else:
            payload = json.loads(Path(input_path).read_text(encoding="utf-8-sig"))
    except CLIError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CLIUsageError(f"无法读取 JSON 输入: {exc}") from exc
    if not isinstance(payload, dict):
        raise CLIUsageError("JSON 输入必须是对象")
    validated = spec.input_model.model_validate(payload)
    return validated.model_dump()


def _preflight_database(ctx: CommandContext) -> None:
    ctx.settings.validate()
    database = ctx.database
    path = Path(database.db_path)
    if not path.exists():
        raise CLIUnavailableError(
            "数据库尚未初始化，请先运行 .\\ainews.ps1 system init",
            details={"database_path": str(path.resolve())},
        )
    try:
        database.assert_schema_current()
    except Exception as exc:
        raise CLIUnavailableError(
            "数据库结构尚未就绪，请先运行 .\\ainews.ps1 system init",
            details={"database_path": str(path.resolve()), "reason": str(exc)},
        ) from exc


def _preflight_worker(ctx: CommandContext) -> None:
    ready, details = ctx.services.runtime_health.pipeline_readiness()
    if ready:
        return
    worker = details.get("checks", {}).get("worker", {})
    raise CLIUnavailableError(
        "后台 Worker 未就绪，暂时不能执行该命令",
        details={"worker": worker},
        data={"readiness": details},
    )


def _invoke(spec: CommandSpec, ctx: CommandContext, args: argparse.Namespace, payload):
    if spec.requires_yes and not getattr(args, "yes", False):
        raise CLIUsageError("该命令属于高影响操作，必须显式传入 --yes")
    if spec.database_mode == "ready":
        _preflight_database(ctx)
        if spec.requires_worker:
            _preflight_worker(ctx)
        from backend.app.infrastructure.repositories import repository_session

        with repository_session():
            result = spec.handler(ctx, args, payload)
            return asyncio.run(result) if inspect.isawaitable(result) else result
    result = spec.handler(ctx, args, payload)
    return asyncio.run(result) if inspect.isawaitable(result) else result


def _normalize_result(value: Any) -> CommandResult:
    if isinstance(value, CommandResult):
        return value
    return CommandResult(data=value)


def _map_exception(exc: Exception) -> CLIError:
    if isinstance(exc, CLIError):
        return exc
    if isinstance(exc, PydanticValidationError):
        return CLIUsageError("JSON 输入不符合命令模型", details=exc.errors(include_url=False))
    try:
        from backend.app.core.exceptions import APIException
    except Exception:
        APIException = ()
    if APIException and isinstance(exc, APIException):
        error_type = getattr(exc, "error_type", type(exc).__name__)
        code = int(getattr(exc, "code", 400))
        if code == 404:
            exit_code = 3
        elif error_type in {"ValidationError", "RequestValidationError"}:
            exit_code = 2
        elif code in {400, 409}:
            exit_code = 4
        elif code in {500, 503}:
            exit_code = 5 if error_type in {"DatabaseError", "ConfigurationError", "ServiceUnavailableError"} else 1
        else:
            exit_code = 1
        return CLIError(
            str(exc),
            exit_code=exit_code,
            error_type=error_type,
            details=getattr(exc, "details", None),
        )
    if isinstance(exc, (sqlite3.Error, OSError)):
        return CLIUnavailableError(str(exc))
    return CLIError(str(exc) or type(exc).__name__, error_type=type(exc).__name__)


def _text_output(envelope: dict[str, Any]) -> str:
    prefix = "成功" if envelope["success"] else "失败"
    lines = [f"{prefix}: {envelope['message']}"]
    if envelope.get("data") is not None:
        lines.append(json.dumps(envelope["data"], ensure_ascii=False, indent=2, default=_json_default))
    if envelope.get("error"):
        lines.append(json.dumps(envelope["error"], ensure_ascii=False, indent=2, default=_json_default))
    return "\n".join(lines)


def _emit(stream, envelope: CLIEnvelope, output_format: str, pretty: bool) -> None:
    payload = envelope.model_dump(mode="python")
    if output_format == "text":
        stream.write(_text_output(payload) + "\n")
        stream.flush()
        return
    stream.write(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
            default=_json_default,
        )
        + "\n"
    )
    stream.flush()


def main(argv: Sequence[str] | None = None) -> int:
    started_at = time.perf_counter()
    real_stdout = sys.stdout
    specs = load_command_specs()
    parser = build_parser(specs)
    args = argparse.Namespace(format="json", pretty=False, debug=False, _command_spec=None)
    command_id = None
    result = CommandResult()
    cli_error = None
    exit_code = 0
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
        if getattr(args, "env", None):
            os.environ["AINEWS_ENV"] = args.env
        spec = getattr(args, "_command_spec", None)
        if spec is None:
            raise CLIUsageError("缺少命令；使用 --help 查看可用命令")
        command_id = spec.command_id
        payload = _load_input(spec, args)
        ctx = CommandContext(specs)
        with redirect_stdout(sys.stderr):
            result = _normalize_result(_invoke(spec, ctx, args, payload))
    except KeyboardInterrupt:
        cli_error = CLIError("操作已中断", exit_code=130, error_type="InterruptedError")
        exit_code = 130
    except SystemExit as exc:
        return int(exc.code or 0)
    except Exception as exc:
        cli_error = _map_exception(exc)
        exit_code = cli_error.exit_code
        if getattr(args, "debug", False):
            traceback.print_exc(file=sys.stderr)

    duration_ms = round((time.perf_counter() - started_at) * 1000, 3)
    meta = CLIMeta(app_version=_source_version(), environment=_environment(), duration_ms=duration_ms)
    if cli_error is None:
        envelope = CLIEnvelope(
            contract_version=CLI_CONTRACT_VERSION,
            success=True,
            command=command_id,
            data=result.data,
            message=result.message,
            meta=meta,
        )
    else:
        envelope = CLIEnvelope(
            contract_version=CLI_CONTRACT_VERSION,
            success=False,
            command=command_id,
            data=cli_error.data,
            message=cli_error.message,
            error=CLIErrorBody(type=cli_error.error_type, details=cli_error.details),
            meta=meta,
        )
    _emit(real_stdout, envelope, getattr(args, "format", "json"), getattr(args, "pretty", False))
    return exit_code
