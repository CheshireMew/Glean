from __future__ import annotations

import hashlib
import json
from pathlib import Path

from shared.content_contract import (
    CONTENT_KINDS,
    EXPORT_SCOPE_ARCHIVE,
    EXPORT_SCOPE_BLOCKED,
    EXPORT_SCOPE_DISCARDED,
    EXPORT_SCOPE_INCOMING,
    EXPORT_SCOPE_REVIEW,
    EXPORT_SCOPE_SELECTED,
    PUBLIC_STREAM_MAP,
)

from ..errors import CLIConflictError, CLINotFoundError, CLIUsageError
from ..models import CommandResult, CommandSpec
from ..registry import arg


CONTENT_SCOPES = (
    "incoming",
    "events",
    "archive",
    "blocked",
    "review",
    "selected",
    "discarded",
)
EXPORT_SCOPES = (
    EXPORT_SCOPE_INCOMING,
    EXPORT_SCOPE_ARCHIVE,
    EXPORT_SCOPE_BLOCKED,
    EXPORT_SCOPE_REVIEW,
    EXPORT_SCOPE_SELECTED,
    EXPORT_SCOPE_DISCARDED,
)


def _bounded(value: int, label: str, minimum: int, maximum: int) -> int:
    if value < minimum or value > maximum:
        raise CLIUsageError(f"{label}必须在 {minimum} 到 {maximum} 之间")
    return value


def _page_payload(result: dict) -> dict:
    return {
        "items": result.get("results", []),
        "pagination": {
            "total": result.get("total", 0),
            "page": result.get("page", 1),
            "limit": result.get("limit", 0),
        },
        **({"summary": result["summary"]} if "summary" in result else {}),
    }


def overview_handler(ctx, args, payload):
    return ctx.services.content.get_dashboard_overview(args.kind)


def stats_handler(ctx, args, payload):
    return ctx.services.content.get_source_stats(args.kind)


def list_handler(ctx, args, payload):
    page = _bounded(args.page, "page", 1, 2_147_483_647)
    limit = _bounded(args.limit, "limit", 1, 200)
    service = ctx.services.content
    if args.scope == "incoming":
        result = service.list_incoming(page, limit, args.source, args.keyword, args.kind)
    elif args.scope == "events":
        result = service.list_source_groups(page, limit, args.source, args.keyword, args.kind)
    elif args.scope == "archive":
        result = service.list_archive(page, limit, args.source, args.keyword, args.kind)
    elif args.scope == "blocked":
        result = service.list_blocked(page, limit, args.keyword, args.kind)
    elif args.scope == "review":
        result = service.list_review_queue(page, limit, args.source, args.keyword, args.kind)
    else:
        result = service.list_review_decisions(
            args.scope, page, limit, args.source, args.keyword, args.kind
        )
    return _page_payload(result)


def export_handler(ctx, args, payload):
    target = Path(args.output).expanduser().resolve()
    if not target.parent.exists():
        raise CLIUsageError(f"输出目录不存在: {target.parent}")
    if target.exists() and not args.overwrite:
        raise CLIConflictError("输出文件已存在；如需替换请显式传入 --overwrite")

    rows = ctx.services.content.stream_export_content(
        args.scope,
        args.start_date,
        args.end_date,
        args.keyword,
        args.source,
        args.kind,
        args.fields,
    )
    digest = hashlib.sha256()
    count = 0
    mode = "w" if args.overwrite else "x"
    with target.open(mode, encoding="utf-8", newline="") as handle:
        opening = "["
        handle.write(opening)
        digest.update(opening.encode("utf-8"))
        for item in rows:
            serialized = json.dumps(item, default=str, ensure_ascii=False, separators=(",", ":"))
            chunk = ("," if count else "") + serialized
            handle.write(chunk)
            digest.update(chunk.encode("utf-8"))
            count += 1
        handle.write("]")
        digest.update(b"]")
    return CommandResult(
        data={
            "path": str(target),
            "count": count,
            "bytes": target.stat().st_size,
            "sha256": digest.hexdigest(),
        },
        message=f"已导出 {count} 条内容",
    )


def delete_handler(ctx, args, payload):
    lifecycle = ctx.services.content_lifecycle
    if args.scope == "incoming":
        deleted = lifecycle.delete_incoming_entry(args.id)
    elif args.scope == "archive":
        deleted = lifecycle.delete_archive_entry(args.id)
    else:
        deleted = lifecycle.delete_review_entry(args.id)
    if not deleted:
        raise CLINotFoundError("内容不存在")
    return CommandResult(message="内容已删除")


def restore_handler(ctx, args, payload):
    lifecycle = ctx.services.content_lifecycle
    restored = (
        lifecycle.restore_archive_entry(args.id)
        if args.scope == "archive"
        else lifecycle.restore_blocked_entry(args.id)
    )
    if not restored:
        raise CLINotFoundError("内容不存在或当前状态不能恢复")
    destination = "采集池" if args.scope == "archive" else "审核池"
    return CommandResult(message=f"内容已恢复到{destination}")


def requeue_handler(ctx, args, payload):
    result = ctx.services.content_lifecycle.reset_review_item(args.id)
    return CommandResult(message=result["message"])


def requeue_all_handler(ctx, args, payload):
    result = ctx.services.content_lifecycle.reset_review_queue(args.kind)
    return CommandResult(data=result, message="已重新入队审核结果")


def clear_decisions_handler(ctx, args, payload):
    result = ctx.services.content_lifecycle.clear_review_results(args.kind)
    return CommandResult(data=result, message="审核结果已清空")


def restore_blocked_all_handler(ctx, args, payload):
    result = ctx.services.content_lifecycle.restore_blocked_queue(args.kind)
    return CommandResult(data=result, message="已恢复黑名单拦截队列")


def public_content_handler(ctx, args, payload):
    limit = _bounded(args.limit, "limit", 1, 1000)
    offset = _bounded(args.offset, "offset", 0, 2_147_483_647)
    kind = PUBLIC_STREAM_MAP[args.stream]
    return ctx.services.public_content.get_public_content(
        kind, limit, offset, args.cursor, args.known_revision, args.publication
    )


def public_reports_handler(ctx, args, payload):
    limit = _bounded(args.limit, "limit", 1, 100)
    offset = _bounded(args.offset, "offset", 0, 2_147_483_647)
    return ctx.services.public_content.get_public_reports(
        args.kind, limit, offset, args.query, args.publication
    )


def public_search_handler(ctx, args, payload):
    query = args.query.strip()
    if not query:
        raise CLIUsageError("搜索关键词不能为空")
    limit = _bounded(args.limit, "limit", 1, 100)
    offset = _bounded(args.offset, "offset", 0, 2_147_483_647)
    return ctx.services.public_content.search_public_content(
        query, args.kind, limit, offset, args.publication
    )


def public_rss_handler(ctx, args, payload):
    limit = _bounded(args.limit, "limit", 1, 100)
    return {
        "content_type": "application/rss+xml",
        "xml": ctx.services.public_content.build_public_rss(args.kind, limit, args.publication),
    }


def _kind_argument(default="news"):
    return arg("--kind", choices=CONTENT_KINDS, default=default, help="内容类型")


def _page_arguments():
    return (
        arg("--page", type=int, default=1),
        arg("--limit", type=int, default=50),
        arg("--source"),
        arg("--keyword"),
        _kind_argument(),
    )


def command_specs():
    return [
        CommandSpec(
            "content.overview",
            ("content", "overview"),
            "查询各内容池数量",
            overview_handler,
            arguments=(_kind_argument(),),
        ),
        CommandSpec(
            "content.stats",
            ("content", "stats"),
            "查询来源统计",
            stats_handler,
            arguments=(_kind_argument(),),
        ),
        CommandSpec(
            "content.list",
            ("content", "list"),
            "分页查询内容池或事件",
            list_handler,
            arguments=(arg("--scope", choices=CONTENT_SCOPES, required=True), *_page_arguments()),
        ),
        CommandSpec(
            "content.export",
            ("content", "export"),
            "流式导出内容到 JSON 文件",
            export_handler,
            arguments=(
                arg("--scope", choices=EXPORT_SCOPES, required=True),
                arg("--output", required=True),
                arg("--overwrite", action="store_true"),
                arg("--start-date"),
                arg("--end-date"),
                arg("--keyword"),
                arg("--source"),
                arg("--kind", choices=CONTENT_KINDS),
                arg("--fields", help="逗号分隔的字段名"),
            ),
        ),
        CommandSpec(
            "content.delete",
            ("content", "delete"),
            "删除采集、归档或审核内容",
            delete_handler,
            arguments=(
                arg("--scope", choices=("incoming", "archive", "review"), required=True),
                arg("--id", type=int, required=True),
            ),
            requires_yes=True,
        ),
        CommandSpec(
            "content.restore",
            ("content", "restore"),
            "恢复归档事件或黑名单内容",
            restore_handler,
            arguments=(
                arg("--scope", choices=("archive", "blocked"), required=True),
                arg("--id", type=int, required=True),
            ),
            requires_yes=True,
        ),
        CommandSpec(
            "content.requeue",
            ("content", "requeue"),
            "把单条审核结果重新入队",
            requeue_handler,
            arguments=(arg("--id", type=int, required=True),),
        ),
        CommandSpec(
            "content.requeue-all",
            ("content", "requeue-all"),
            "按内容类型重新入队全部审核结果",
            requeue_all_handler,
            arguments=(_kind_argument(),),
        ),
        CommandSpec(
            "content.clear-decisions",
            ("content", "clear-decisions"),
            "清空指定类型的审核结果",
            clear_decisions_handler,
            arguments=(_kind_argument(),),
            requires_yes=True,
        ),
        CommandSpec(
            "content.restore-blocked-all",
            ("content", "restore-blocked-all"),
            "恢复指定类型的全部黑名单拦截内容",
            restore_blocked_all_handler,
            arguments=(_kind_argument(),),
        ),
        CommandSpec(
            "public.content",
            ("public", "content"),
            "查询公开内容流",
            public_content_handler,
            arguments=(
                arg("--stream", choices=tuple(PUBLIC_STREAM_MAP), required=True),
                arg("--limit", type=int, default=20),
                arg("--offset", type=int, default=0),
                arg("--cursor"),
                arg("--known-revision"),
                arg("--publication", help="公开频道标识"),
            ),
        ),
        CommandSpec(
            "public.reports",
            ("public", "reports"),
            "查询已发布日报",
            public_reports_handler,
            arguments=(
                arg("--kind", choices=CONTENT_KINDS),
                arg("--limit", type=int, default=20),
                arg("--offset", type=int, default=0),
                arg("--query"),
                arg("--publication", help="公开频道标识"),
            ),
        ),
        CommandSpec(
            "public.search",
            ("public", "search"),
            "搜索公开内容",
            public_search_handler,
            arguments=(
                arg("--query", required=True),
                arg("--kind", choices=(*CONTENT_KINDS, "all"), default="all"),
                arg("--limit", type=int, default=20),
                arg("--offset", type=int, default=0),
                arg("--publication", help="公开频道标识"),
            ),
        ),
        CommandSpec(
            "public.rss",
            ("public", "rss"),
            "生成公开 RSS XML",
            public_rss_handler,
            arguments=(
                _kind_argument(),
                arg("--limit", type=int, default=20),
                arg("--publication", help="公开频道标识"),
            ),
        ),
    ]
