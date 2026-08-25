from __future__ import annotations

from shared.content_contract import (
    CONTENT_KINDS,
    DELIVERY_OPERATION_STATUSES,
    DELIVERY_OPERATION_STATUS_SENT,
)
from backend.app.models.config import TelegramConfigRequest
from backend.app.models.operations import TelegramSendRequest

from ..errors import CLIIncompleteError, CLIUsageError
from ..models import CommandResult, CommandSpec
from ..registry import arg


def _operation_outcome(result: dict, success_message: str) -> CommandResult:
    status = result.get("status")
    if status in {DELIVERY_OPERATION_STATUS_SENT, "success", "skipped"}:
        return CommandResult(data=result, message=result.get("message") or success_message)
    raise CLIIncompleteError(
        result.get("message") or "交付尚未完整完成",
        details={"status": status},
        data=result,
    )


async def daily_handler(ctx, args, payload):
    if args.kind == "news":
        result = await ctx.services.daily_delivery.send_news(
            force=True, operation_key=args.operation_key
        )
    else:
        result = await ctx.services.daily_delivery.send_articles(
            force=True, operation_key=args.operation_key
        )
    return _operation_outcome(result, "日报交付已完成")


async def send_handler(ctx, args, payload):
    request = TelegramSendRequest.model_validate(payload)
    result = await ctx.services.manual_entry_delivery.send(
        [entry.model_dump() for entry in request.entries], request.operation_key
    )
    return _operation_outcome(result, "内容交付已完成")


async def retry_handler(ctx, args, payload):
    result = await ctx.services.delivery_retry.retry(args.operation_key)
    return _operation_outcome(result, "交付重试已完成")


def operations_handler(ctx, args, payload):
    if args.limit < 1 or args.limit > 200:
        raise CLIUsageError("limit 必须在 1 到 200 之间")
    return {
        "items": ctx.services.delivery_operations.list_operations(args.limit, args.status),
        "limit": args.limit,
        "status": args.status,
    }


def operation_handler(ctx, args, payload):
    return ctx.services.delivery_operations.get_operation(args.operation_key)


async def test_handler(ctx, args, payload):
    result = await ctx.services.telegram_gateway.send_test_message(payload)
    return CommandResult(data=result, message=result["message"])


def command_specs():
    return [
        CommandSpec(
            "delivery.daily",
            ("delivery", "daily"),
            "强制生成并发送指定类型的日报",
            daily_handler,
            arguments=(
                arg("--kind", choices=CONTENT_KINDS, required=True),
                arg("--operation-key", required=True),
            ),
            requires_yes=True,
        ),
        CommandSpec(
            "delivery.send",
            ("delivery", "send"),
            "发送明确引用的内容条目",
            send_handler,
            input_model=TelegramSendRequest,
            input_required=True,
            requires_yes=True,
        ),
        CommandSpec(
            "delivery.retry",
            ("delivery", "retry"),
            "确认后重试明确未发送或失败的分段",
            retry_handler,
            arguments=(arg("--operation-key", required=True),),
            requires_yes=True,
        ),
        CommandSpec(
            "delivery.operations",
            ("delivery", "operations"),
            "列出持久化交付操作",
            operations_handler,
            arguments=(
                arg("--limit", type=int, default=50),
                arg("--status", choices=DELIVERY_OPERATION_STATUSES),
            ),
        ),
        CommandSpec(
            "delivery.operation",
            ("delivery", "operation"),
            "按操作键查询交付状态",
            operation_handler,
            arguments=(arg("--operation-key", required=True),),
        ),
        CommandSpec(
            "delivery.test",
            ("delivery", "test"),
            "使用保存或临时配置发送 Telegram 测试消息",
            test_handler,
            input_model=TelegramConfigRequest,
            input_required=False,
            requires_yes=True,
        ),
    ]
