from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import replace
from typing import Any, Iterable, Sequence

from .errors import CLIUsageError
from .models import ArgumentSpec, CommandSpec


GROUP_HELP = {
    "system": "数据库、运行状态、维护和管理员凭据",
    "content": "后台内容查询、导出和生命周期操作",
    "public": "公开内容、日报、搜索和 RSS",
    "scraper": "爬虫目录、状态、配置和 worker 命令",
    "pipeline": "事件聚合、黑名单、审核和整周期处理",
    "blocklist": "黑名单词条管理",
    "delivery": "Telegram 交付及持久化操作状态",
    "config": "系统和集成配置",
    "profile": "内容档案管理",
    "rss": "RSS 来源管理",
    "analyst-key": "分析接口密钥管理",
    "event": "事件证据和进展",
    "editorial": "人工编辑和修订",
    "publication": "内容档案发布频道",
    "channel": "多渠道投递配置",
    "draft": "发布草稿和排期",
    "correction": "发布更正",
    "entity": "实体目录",
    "narrative": "叙事目录",
    "watchlist": "关注列表",
    "alert": "提醒规则",
    "source": "来源运营和健康度",
    "market": "事件行情反应",
    "ai-quality": "AI 调用质量、费用和固定评测",
}


class CLIArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CLIUsageError(message)


def arg(*names: str, **kwargs: Any) -> ArgumentSpec:
    return ArgumentSpec(tuple(names), kwargs)


def load_command_specs() -> list[CommandSpec]:
    from .commands.configuration import command_specs as configuration_specs
    from .commands.content import command_specs as content_specs
    from .commands.delivery import command_specs as delivery_specs
    from .commands.operations import command_specs as operation_specs
    from .commands.system import command_specs as system_specs
    from .commands.intelligence import command_specs as intelligence_specs

    specs = [
        *system_specs(),
        *content_specs(),
        *operation_specs(),
        *delivery_specs(),
        *configuration_specs(),
        *intelligence_specs(),
    ]
    from .output_schemas import command_output_schemas

    schemas = command_output_schemas()
    command_ids = [spec.command_id for spec in specs]
    paths = [spec.path for spec in specs]
    if len(command_ids) != len(set(command_ids)):
        raise RuntimeError("CLI command_id 必须唯一")
    if len(paths) != len(set(paths)):
        raise RuntimeError("CLI 命令路径必须唯一")
    missing_schemas = sorted(set(command_ids) - set(schemas))
    unknown_schemas = sorted(set(schemas) - set(command_ids))
    if missing_schemas or unknown_schemas:
        raise RuntimeError(
            "CLI 输出 Schema 必须与命令注册表完全一致："
            f"missing={missing_schemas} unknown={unknown_schemas}"
        )
    return [replace(spec, output_schema=schemas[spec.command_id]) for spec in specs]


def build_parser(specs: Sequence[CommandSpec]) -> CLIArgumentParser:
    parser = CLIArgumentParser(
        prog="ainews",
        description="AINews 本机管理 CLI；默认输出适合 Agent 解析的 JSON。",
    )
    parser.add_argument("--env", choices=("development", "production", "test"), help="运行环境")
    parser.add_argument("--format", choices=("json", "text"), default="json", help="输出格式")
    parser.add_argument("--pretty", action="store_true", help="缩进 JSON 输出")
    parser.add_argument("--debug", action="store_true", help="把调试堆栈写入 stderr")

    children: dict[tuple[str, ...], set[str]] = defaultdict(set)
    for spec in specs:
        for index, segment in enumerate(spec.path):
            children[spec.path[:index]].add(segment)

    parser_by_path: dict[tuple[str, ...], argparse.ArgumentParser] = {(): parser}
    subparsers_by_path: dict[tuple[str, ...], argparse._SubParsersAction] = {}

    def ensure_subparsers(path: tuple[str, ...]):
        existing = subparsers_by_path.get(path)
        if existing is not None:
            return existing
        parent = parser_by_path[path]
        action = parent.add_subparsers(dest=f"_segment_{len(path)}")
        subparsers_by_path[path] = action
        return action

    spec_by_path = {spec.path: spec for spec in specs}
    all_paths = sorted(
        {spec.path[:index] for spec in specs for index in range(1, len(spec.path) + 1)},
        key=lambda value: (len(value), value),
    )
    for path in all_paths:
        parent_path = path[:-1]
        leaf = path[-1]
        action = ensure_subparsers(parent_path)
        spec = spec_by_path.get(path)
        help_text = spec.help if spec else GROUP_HELP.get(leaf, leaf)
        child = action.add_parser(leaf, help=help_text, description=help_text)
        parser_by_path[path] = child
        if spec is None:
            continue
        for argument in spec.arguments:
            child.add_argument(*argument.names, **argument.kwargs)
        if spec.input_model is not None:
            child.add_argument(
                "--input",
                required=spec.input_required,
                metavar="PATH|-",
                help="UTF-8 JSON 文件；使用 - 从 stdin 读取",
            )
        if spec.requires_yes:
            child.add_argument("--yes", action="store_true", help="确认执行高影响操作")
        child.set_defaults(_command_spec=spec)
    return parser


def _json_type(action: argparse.Action) -> str:
    if action.type is int:
        return "integer"
    if action.type is float:
        return "number"
    if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
        return "boolean"
    return "string"


def argument_contract(spec: CommandSpec) -> list[dict[str, Any]]:
    parser = CLIArgumentParser(add_help=False)
    for argument in spec.arguments:
        parser.add_argument(*argument.names, **argument.kwargs)
    if spec.input_model is not None:
        parser.add_argument("--input", required=spec.input_required)
    if spec.requires_yes:
        parser.add_argument("--yes", action="store_true")
    result = []
    for action in parser._actions:
        if action.dest == "help":
            continue
        item = {
            "name": action.dest,
            "flags": action.option_strings,
            "required": bool(getattr(action, "required", False)) or not action.option_strings,
            "type": _json_type(action),
        }
        if action.choices is not None:
            item["choices"] = list(action.choices)
        if action.default is not None and action.default is not argparse.SUPPRESS:
            item["default"] = action.default
        result.append(item)
    return result


def capability_contract(specs: Iterable[CommandSpec], command_id: str | None = None) -> dict[str, Any]:
    selected = [spec for spec in specs if command_id is None or spec.command_id == command_id]
    if command_id is not None and not selected:
        raise CLIUsageError(f"未知命令 ID: {command_id}")
    commands = []
    for spec in selected:
        commands.append(
            {
                "id": spec.command_id,
                "invocation": " ".join(spec.path),
                "description": spec.help,
                "arguments": argument_contract(spec),
                "requires_database": spec.database_mode == "ready",
                "requires_worker": spec.requires_worker,
                "requires_yes": spec.requires_yes,
                "input_schema": spec.input_model.model_json_schema() if spec.input_model else None,
                "output_schema": spec.output_schema,
            }
        )
    return {"contract_version": 1, "commands": commands}
