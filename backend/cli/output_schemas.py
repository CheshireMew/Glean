from __future__ import annotations

from typing import Any


STRING = {"type": "string"}
INTEGER = {"type": "integer"}
NUMBER = {"type": "number"}
BOOLEAN = {"type": "boolean"}
NULL = {"type": "null"}
STRING_OR_NULL = {"type": ["string", "null"]}


def _array(items: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"type": "array", "items": items or {"type": "object"}}


def _object(
    properties: dict[str, Any] | None = None,
    *,
    required: tuple[str, ...] = (),
    additional: bool | dict[str, Any] = True,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties or {},
        "additionalProperties": additional,
    }
    if required:
        schema["required"] = list(required)
    return schema


ITEM = _object()
ITEMS = _array(ITEM)
EXTENSIBLE_RESULT = _object(
    {"id": INTEGER, "status": STRING, "message": STRING, "items": ITEMS}
)
MESSAGE_RESULT = NULL
COUNT_RESULT = _object(
    {
        "restored_count": INTEGER,
        "cleared_count": INTEGER,
        "count": INTEGER,
    }
)
PAGE = _object(
    {
        "items": ITEMS,
        "pagination": _object(
            {"total": INTEGER, "page": INTEGER, "limit": INTEGER},
            required=("total", "page", "limit"),
        ),
        "summary": ITEM,
    },
    required=("items", "pagination"),
)
PUBLIC_PAGE = _object(
    {
        "items": ITEMS,
        "total": INTEGER,
        "limit": INTEGER,
        "offset": INTEGER,
        "next_cursor": STRING_OR_NULL,
        "revision": STRING,
        "not_modified": BOOLEAN,
        "query": STRING,
    },
    required=("items", "total", "limit", "offset"),
)
SCRAPER_COMMAND = _object(
    {
        "id": INTEGER,
        "command_id": INTEGER,
        "scraper_name": STRING,
        "command_type": STRING,
        "status": STRING,
        "result_message": STRING_OR_NULL,
        "message": STRING,
        "attempt_count": INTEGER,
    }
)
SCRAPER_STATE = _object(
    {
        "scraper_name": STRING,
        "status": STRING,
        "items_scraped": INTEGER,
        "last_result": STRING_OR_NULL,
        "logs": _array(STRING),
        "interval": {"type": ["string", "integer", "null"]},
        "limit": INTEGER,
    },
    required=("status",),
)
SCRAPER_WAIT = _object(
    {"command": SCRAPER_COMMAND, "state": SCRAPER_STATE},
    required=("command", "state"),
)
DELIVERY_OPERATION = _object(
    {
        "operation_key": STRING,
        "status": STRING,
        "parts": INTEGER,
        "sent_parts": INTEGER,
        "last_error": STRING_OR_NULL,
        "needs_attention": BOOLEAN,
        "message": STRING,
    },
    required=("operation_key", "status"),
)
DELIVERY_SKIPPED = _object(
    {"status": {"const": "skipped"}, "message": STRING},
    required=("status", "message"),
)
PROFILE = _object(
    {
        "slug": STRING,
        "name": STRING,
        "content_type": STRING,
        "review_prompt": STRING,
        "enrichment_prompt": STRING,
        "min_score": INTEGER,
        "max_items": INTEGER,
        "max_per_category": INTEGER,
        "max_per_source": INTEGER,
        "enabled": {"type": ["boolean", "integer"]},
        "is_default": {"type": ["boolean", "integer"]},
        "created_at": STRING,
        "updated_at": STRING,
    },
    required=("slug", "name", "content_type", "enabled", "is_default"),
)
RSS_SOURCE = _object(
    {
        "id": INTEGER,
        "slug": STRING,
        "display_name": STRING,
        "feed_url": STRING,
        "site_url": STRING,
        "content_kind": STRING,
        "parser_type": STRING,
        "default_limit": INTEGER,
        "default_interval": INTEGER,
        "enabled": {"type": ["boolean", "integer"]},
        "created_at": STRING,
        "updated_at": STRING,
    },
    required=(
        "id",
        "slug",
        "display_name",
        "feed_url",
        "site_url",
        "content_kind",
        "parser_type",
        "default_limit",
        "default_interval",
        "enabled",
    ),
)


def command_output_schemas() -> dict[str, dict[str, Any]]:
    schemas: dict[str, dict[str, Any]] = {
        "version": _object({"version": STRING}, required=("version",)),
        "capabilities": _object(
            {
                "contract_version": INTEGER,
                "commands": _array(
                    _object(
                        {
                            "id": STRING,
                            "invocation": STRING,
                            "description": STRING,
                            "arguments": ITEMS,
                            "requires_database": BOOLEAN,
                            "requires_worker": BOOLEAN,
                            "requires_yes": BOOLEAN,
                            "input_schema": {"type": ["object", "null"]},
                            "output_schema": _object(),
                        },
                        required=(
                            "id",
                            "invocation",
                            "description",
                            "arguments",
                            "requires_database",
                            "requires_worker",
                            "requires_yes",
                            "input_schema",
                            "output_schema",
                        ),
                    )
                ),
            },
            required=("contract_version", "commands"),
        ),
        "system.status": _object(
            {
                "database": _object(
                    {
                        "ready": BOOLEAN,
                        "exists": BOOLEAN,
                        "path": STRING,
                        "required_schema_version": STRING,
                    },
                    required=("ready", "exists", "path", "required_schema_version"),
                ),
                "pipeline": _object({"ready": BOOLEAN}, required=("ready",)),
            },
            required=("database", "pipeline"),
        ),
        "system.init": _object(
            {"database_path": STRING, "created": BOOLEAN, "schema_version": STRING},
            required=("database_path", "created", "schema_version"),
        ),
        "system.maintenance": _object({"status": STRING}, required=("status",)),
        "system.credentials": MESSAGE_RESULT,
        "content.overview": _object(
            {
                "incoming": INTEGER,
                "archive": INTEGER,
                "blocked": INTEGER,
                "review": INTEGER,
                "selected": INTEGER,
                "discarded": INTEGER,
            },
            required=("incoming", "archive", "blocked", "review", "selected", "discarded"),
        ),
        "content.stats": _object(
            {
                "stats": _array(
                    _object(
                        {"source": {"type": ["string", "null"]}, "count": INTEGER},
                        required=("source", "count"),
                    )
                )
            },
            required=("stats",),
        ),
        "content.list": PAGE,
        "content.export": _object(
            {"path": STRING, "count": INTEGER, "bytes": INTEGER, "sha256": STRING},
            required=("path", "count", "bytes", "sha256"),
        ),
        "content.delete": MESSAGE_RESULT,
        "content.restore": MESSAGE_RESULT,
        "content.requeue": MESSAGE_RESULT,
        "content.requeue-all": COUNT_RESULT,
        "content.clear-decisions": COUNT_RESULT,
        "content.restore-blocked-all": COUNT_RESULT,
        "public.content": PUBLIC_PAGE,
        "public.reports": PUBLIC_PAGE,
        "public.search": PUBLIC_PAGE,
        "public.rss": _object(
            {"content_type": STRING, "xml": STRING}, required=("content_type", "xml")
        ),
        "scraper.list": _object({"spiders": ITEMS}, required=("spiders",)),
        "scraper.status": {
            "anyOf": [
                SCRAPER_STATE,
                _object(additional=SCRAPER_STATE),
            ]
        },
        "scraper.configure": _object(
            {"status": STRING, "config": ITEM}, required=("status", "config")
        ),
        "scraper.run": {"anyOf": [SCRAPER_COMMAND, SCRAPER_WAIT]},
        "scraper.stop": {"anyOf": [SCRAPER_COMMAND, SCRAPER_WAIT]},
        "scraper.command": SCRAPER_COMMAND,
        "scraper.wait": SCRAPER_WAIT,
        "pipeline.cluster": _object(
            {"status": STRING, "message": STRING, "stats": ITEM},
            required=("status", "message", "stats"),
        ),
        "pipeline.similarity": _object(
            {
                "news_1": _object({"id": INTEGER, "title": STRING}, required=("id", "title")),
                "news_2": _object({"id": INTEGER, "title": STRING}, required=("id", "title")),
                "similarity": NUMBER,
                "threshold": NUMBER,
                "is_same_event": BOOLEAN,
            },
            required=("news_1", "news_2", "similarity", "threshold", "is_same_event"),
        ),
        "pipeline.blocklist-apply": _object({"stats": ITEM}, required=("stats",)),
        "pipeline.review": _object(
            {
                "processed": INTEGER,
                "attempted": INTEGER,
                "failed": INTEGER,
                "selected": INTEGER,
                "discarded": INTEGER,
                "enriched": INTEGER,
                "enrichment_failed": INTEGER,
                "enrichment_remaining": INTEGER,
                "total": INTEGER,
                "remaining": INTEGER,
                "results": ITEMS,
            },
            required=(
                "processed",
                "attempted",
                "failed",
                "selected",
                "discarded",
                "enriched",
                "enrichment_failed",
                "enrichment_remaining",
                "total",
                "remaining",
                "results",
            ),
        ),
        "pipeline.cycle": _object(
            {
                "failures": ITEMS,
                "skipped": ITEMS,
                "backlog_pending": BOOLEAN,
                "backlog_unknown": BOOLEAN,
                "remaining_by_kind": _object(additional=INTEGER),
            },
            required=(
                "failures",
                "skipped",
                "backlog_pending",
                "backlog_unknown",
                "remaining_by_kind",
            ),
        ),
        "blocklist.list": _object({"keywords": ITEMS}, required=("keywords",)),
        "blocklist.add": MESSAGE_RESULT,
        "blocklist.remove": MESSAGE_RESULT,
        "delivery.daily": {"anyOf": [DELIVERY_OPERATION, DELIVERY_SKIPPED]},
        "delivery.send": DELIVERY_OPERATION,
        "delivery.retry": DELIVERY_OPERATION,
        "delivery.operations": _object(
            {"items": _array(DELIVERY_OPERATION), "limit": INTEGER, "status": STRING_OR_NULL},
            required=("items", "limit", "status"),
        ),
        "delivery.operation": DELIVERY_OPERATION,
        "delivery.test": _object({"message": STRING}, required=("message",)),
        "config.system.get": _object(
            {"timezone": ITEM, "automation": ITEM, "delivery": ITEM},
            required=("timezone", "automation", "delivery"),
        ),
        "config.timezone.get": _object({"timezone": STRING}, required=("timezone",)),
        "config.schedule.get": _object(
            {"news_time": STRING_OR_NULL, "article_time": STRING_OR_NULL},
            required=("news_time", "article_time"),
        ),
        "config.automation.get": _object(
            {"runtime": ITEM, "news": ITEM, "article": ITEM},
            required=("runtime", "news", "article"),
        ),
        "config.telegram.get": _object(
            {
                "bot_token": STRING,
                "has_bot_token": BOOLEAN,
                "chat_id": STRING,
                "enabled": BOOLEAN,
            },
            required=("bot_token", "has_bot_token", "chat_id", "enabled"),
        ),
        "config.ai.get": _object(
            {
                "providers": ITEMS,
                "analysis_concurrency": INTEGER,
                "enrichment_concurrency": INTEGER,
                "throttle_seconds": NUMBER,
            },
            required=(
                "providers",
                "analysis_concurrency",
                "enrichment_concurrency",
                "throttle_seconds",
            ),
        ),
        "config.telegram.test": _object({"message": STRING}, required=("message",)),
        "config.ai.test": _object(
            {"ok": BOOLEAN, "message": STRING, "error": STRING}, required=("ok",)
        ),
        "config.review.get": _object(
            {
                "prompt": STRING,
                "hours": INTEGER,
                "kind": STRING,
                "profile_slug": STRING_OR_NULL,
            },
            required=("prompt", "hours", "kind", "profile_slug"),
        ),
        "profile.list": _object({"profiles": _array(PROFILE)}, required=("profiles",)),
        "profile.save": PROFILE,
        "rss.list": _object({"sources": _array(RSS_SOURCE)}, required=("sources",)),
        "rss.create": RSS_SOURCE,
        "rss.update": RSS_SOURCE,
        "analyst-key.list": _object({"items": ITEMS}, required=("items",)),
        "analyst-key.create": _object(
            {
                "id": INTEGER,
                "api_key": STRING,
                "key_name": STRING,
                "notes": STRING_OR_NULL,
                "message": STRING,
            },
            required=("id", "api_key", "key_name", "message"),
        ),
    }

    for command_id in (
        "config.system.set",
        "config.timezone.set",
        "config.schedule.set",
        "config.automation.set",
        "config.telegram.set",
        "config.ai.set",
        "config.review.set",
        "rss.delete",
        "analyst-key.enable",
        "analyst-key.disable",
        "analyst-key.delete",
    ):
        schemas[command_id] = MESSAGE_RESULT

    item_commands = {
        "event.get", "event.evidence", "event.update.add", "event.fact.add", "event.fact.update",
        "event.relation.add", "event.classify", "intelligence.classify", "editorial.get", "editorial.update",
        "editorial.restore", "publication.update", "channel.save", "channel.test", "draft.create",
        "draft.update", "draft.preview", "draft.publish", "draft.publish-due", "correction.create", "correction.publish",
        "entity.save", "entity.attach", "narrative.save", "narrative.attach", "watchlist.save",
        "alert.save", "alert.evaluate", "alert.deliver", "source.update", "source.snapshot",
        "source.incident.update", "market.instrument.save", "market.event", "market.refresh",
        "market.snapshot", "market.expectation", "ai-quality.summary", "ai-quality.case.save",
        "ai-quality.evaluate", "analyst-subscription.create", "analyst-subscription.update",
        "analyst-subscription.deliver",
    }
    list_commands = {
        "publication.list", "channel.list", "draft.list", "correction.list", "entity.list",
        "narrative.list", "watchlist.list", "alert.list", "alert.matches", "source.list",
        "source.incidents", "market.instrument.list", "ai-quality.case.list",
        "analyst-subscription.list",
    }
    for command_id in item_commands:
        schemas[command_id] = EXTENSIBLE_RESULT
    for command_id in list_commands:
        schemas[command_id] = _object({"items": ITEMS}, required=("items",))
    schemas["ai-quality.invocations"] = PAGE
    return schemas


__all__ = ["command_output_schemas"]
