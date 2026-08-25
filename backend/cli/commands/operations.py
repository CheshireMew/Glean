from __future__ import annotations

import asyncio
import time

from shared.content_contract import (
    CONTENT_KINDS,
    SCRAPER_COMMAND_STATUS_CANCELLED,
    SCRAPER_COMMAND_STATUS_COMPLETED,
    SCRAPER_COMMAND_STATUS_FAILED,
    SCRAPER_RUNTIME_STATUS_ERROR,
    SCRAPER_RUNTIME_STATUS_IDLE,
)
from backend.app.models.operations import (
    AddBlacklistRequest,
    BlocklistRunRequest,
    CheckSimilarityRequest,
    EventClusterRequest,
    ReviewRunRequest,
    RunScraperRequest,
    ScraperConfigRequest,
)

from ..errors import CLIIncompleteError, CLITimeoutError, CLIUsageError
from ..models import CommandResult, CommandSpec
from ..registry import arg


def _positive_timeout(value: int) -> int:
    if value < 1:
        raise CLIUsageError("timeout 必须大于 0")
    return value


def scraper_list_handler(ctx, args, payload):
    return ctx.services.scraper_runtime_state.get_spiders()


def scraper_status_handler(ctx, args, payload):
    runtime = ctx.services.scraper_runtime_state
    if args.name:
        definition = runtime.require_scraper(args.name)
        return {
            **runtime.get_scraper_state(args.name),
            **runtime.get_scraper_config(args.name, definition),
        }
    return runtime.get_spider_status()


def scraper_configure_handler(ctx, args, payload):
    request = ScraperConfigRequest(interval=args.interval, limit=args.limit)
    return ctx.services.scraper_runtime_state.update_scraper_config(
        args.name, request.interval, request.limit
    )


async def _wait_for_scraper(ctx, command_id: int, timeout: int):
    timeout = _positive_timeout(timeout)
    deadline = time.monotonic() + timeout
    command = None
    state = None
    while time.monotonic() < deadline:
        command = ctx.services.scraper_commands.get_command(command_id)
        if command["status"] in {SCRAPER_COMMAND_STATUS_FAILED, SCRAPER_COMMAND_STATUS_CANCELLED}:
            raise CLIIncompleteError(
                "爬虫命令未成功执行",
                data={"command": command, "state": state},
            )
        if command["status"] == SCRAPER_COMMAND_STATUS_COMPLETED:
            state = ctx.services.scraper_runtime_state.get_scraper_state(command["scraper_name"])
            if state.get("status") == SCRAPER_RUNTIME_STATUS_ERROR:
                raise CLIIncompleteError(
                    "爬虫运行失败",
                    data={"command": command, "state": state},
                )
            if state.get("status") == SCRAPER_RUNTIME_STATUS_IDLE:
                return {"command": command, "state": state}
        await asyncio.sleep(1)
    raise CLITimeoutError(
        f"等待爬虫命令超时（{timeout} 秒）",
        data={"command": command, "state": state},
    )


async def scraper_run_handler(ctx, args, payload):
    request = RunScraperRequest(items=args.items)
    accepted = await ctx.services.scraper_commands.request_run(args.name, request.items)
    if not args.wait:
        return CommandResult(data=accepted, message=accepted["message"])
    completed = await _wait_for_scraper(ctx, accepted["command_id"], args.timeout)
    return CommandResult(data=completed, message="爬虫运行已完成")


async def scraper_stop_handler(ctx, args, payload):
    accepted = await ctx.services.scraper_commands.request_stop(args.name)
    if not args.wait:
        return CommandResult(data=accepted, message=accepted["message"])
    completed = await _wait_for_scraper(ctx, accepted["command_id"], args.timeout)
    return CommandResult(data=completed, message="爬虫停止命令已完成")


def scraper_command_handler(ctx, args, payload):
    return ctx.services.scraper_commands.get_command(args.command_id)


async def scraper_wait_handler(ctx, args, payload):
    result = await _wait_for_scraper(ctx, args.command_id, args.timeout)
    return CommandResult(data=result, message="爬虫运行已完成")


async def cluster_handler(ctx, args, payload):
    request = EventClusterRequest(
        time_window_hours=args.hours,
        threshold=args.threshold,
        kind=args.kind,
    )
    return await ctx.services.pipeline.cluster_content(
        request.time_window_hours, request.threshold, request.kind
    )


async def similarity_handler(ctx, args, payload):
    request = CheckSimilarityRequest(news_id_1=args.first_id, news_id_2=args.second_id)
    return await ctx.services.event_clustering.check_event_similarity(
        request.news_id_1, request.news_id_2
    )


async def blocklist_apply_handler(ctx, args, payload):
    request = BlocklistRunRequest(time_range_hours=args.hours, kind=args.kind)
    return await ctx.services.pipeline.apply_blocklist(request.time_range_hours, request.kind)


async def review_handler(ctx, args, payload):
    request = ReviewRunRequest(hours=args.hours, kind=args.kind)
    return await ctx.services.pipeline.run_review(request.hours, request.kind)


async def cycle_handler(ctx, args, payload):
    result = await ctx.services.pipeline.run_automation_cycle()
    if result.get("failures") or result.get("backlog_pending") or result.get("backlog_unknown"):
        raise CLIIncompleteError("流水线周期未完整完成", data=result)
    return CommandResult(data=result, message="流水线周期已完整完成")


def blocklist_list_handler(ctx, args, payload):
    return ctx.services.blacklist.get_blacklist(args.kind)


def blocklist_add_handler(ctx, args, payload):
    request = AddBlacklistRequest(
        keyword=args.keyword,
        match_type=args.match_type,
        kind=args.kind,
    )
    result = ctx.services.blacklist.add_blacklist(
        request.keyword, request.match_type, request.kind
    )
    return CommandResult(message=result["message"])


def blocklist_remove_handler(ctx, args, payload):
    result = ctx.services.blacklist.delete_blacklist(args.id)
    return CommandResult(message=result["message"])


def _kind_arg():
    return arg("--kind", choices=CONTENT_KINDS, default="news")


def _wait_args():
    return (
        arg("--wait", action="store_true", help="等待实际抓取进入终态"),
        arg("--timeout", type=int, default=600, help="等待秒数"),
    )


def command_specs():
    return [
        CommandSpec(
            "scraper.list",
            ("scraper", "list"),
            "列出所有可用爬虫",
            scraper_list_handler,
        ),
        CommandSpec(
            "scraper.status",
            ("scraper", "status"),
            "查询全部或单个爬虫状态",
            scraper_status_handler,
            arguments=(arg("name", nargs="?"),),
        ),
        CommandSpec(
            "scraper.configure",
            ("scraper", "configure"),
            "更新爬虫频率或抓取上限",
            scraper_configure_handler,
            arguments=(
                arg("name"),
                arg("--interval", help="分钟数或 manual"),
                arg("--limit", type=int),
            ),
        ),
        CommandSpec(
            "scraper.run",
            ("scraper", "run"),
            "把抓取命令提交给已运行的 worker",
            scraper_run_handler,
            arguments=(arg("name"), arg("--items", type=int, default=10), *_wait_args()),
            requires_worker=True,
        ),
        CommandSpec(
            "scraper.stop",
            ("scraper", "stop"),
            "停止排队或运行中的爬虫",
            scraper_stop_handler,
            arguments=(arg("name"), *_wait_args()),
            requires_worker=True,
        ),
        CommandSpec(
            "scraper.command",
            ("scraper", "command"),
            "查询爬虫命令状态",
            scraper_command_handler,
            arguments=(arg("command_id", type=int),),
        ),
        CommandSpec(
            "scraper.wait",
            ("scraper", "wait"),
            "等待现有爬虫命令和实际抓取进入终态",
            scraper_wait_handler,
            arguments=(arg("command_id", type=int), arg("--timeout", type=int, default=600)),
            requires_worker=True,
        ),
        CommandSpec(
            "pipeline.cluster",
            ("pipeline", "cluster"),
            "聚合指定时间范围的内容事件",
            cluster_handler,
            arguments=(
                arg("--hours", type=int, default=24),
                arg("--threshold", type=float, default=0.5),
                _kind_arg(),
            ),
        ),
        CommandSpec(
            "pipeline.similarity",
            ("pipeline", "similarity"),
            "检查两条来源内容的相似度",
            similarity_handler,
            arguments=(arg("first_id", type=int), arg("second_id", type=int)),
        ),
        CommandSpec(
            "pipeline.blocklist-apply",
            ("pipeline", "blocklist-apply"),
            "应用黑名单并推进未命中内容",
            blocklist_apply_handler,
            arguments=(arg("--hours", type=int, default=24), _kind_arg()),
        ),
        CommandSpec(
            "pipeline.review",
            ("pipeline", "review"),
            "运行一批 AI 审核和内容补充",
            review_handler,
            arguments=(arg("--hours", type=int, default=8), _kind_arg()),
        ),
        CommandSpec(
            "pipeline.cycle",
            ("pipeline", "cycle"),
            "运行包含交付的完整自动流水线周期",
            cycle_handler,
            requires_yes=True,
        ),
        CommandSpec(
            "blocklist.list",
            ("blocklist", "list"),
            "列出黑名单词条",
            blocklist_list_handler,
            arguments=(_kind_arg(),),
        ),
        CommandSpec(
            "blocklist.add",
            ("blocklist", "add"),
            "添加黑名单词条",
            blocklist_add_handler,
            arguments=(
                arg("keyword"),
                arg("--match-type", choices=("contains", "regex"), default="contains"),
                _kind_arg(),
            ),
        ),
        CommandSpec(
            "blocklist.remove",
            ("blocklist", "remove"),
            "删除黑名单词条",
            blocklist_remove_handler,
            arguments=(arg("id", type=int),),
            requires_yes=True,
        ),
    ]
