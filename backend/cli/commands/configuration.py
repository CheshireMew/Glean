from __future__ import annotations

from shared.content_contract import CONTENT_KINDS
from backend.app.models.config import (
    AIProviderConfigRequest,
    AIReviewConfigRequest,
    AutomationConfigRequest,
    DeliveryScheduleConfig,
    EditorialProfileRequest,
    RssSourceRequest,
    RssPreviewRequest,
    SystemSettingsRequest,
    SystemTimezoneConfig,
    TelegramConfigRequest,
)
from backend.app.models.operations import ApiKeyCreateRequest

from ..errors import CLIUsageError
from ..models import CommandResult, CommandSpec
from ..registry import arg


def system_get_handler(ctx, args, payload):
    return {
        "timezone": ctx.services.system_settings.get_timezone(),
        "automation": ctx.services.automation_settings.get_config(),
        "delivery": ctx.services.delivery_settings.get_schedule(),
    }


def system_set_handler(ctx, args, payload):
    request = SystemSettingsRequest.model_validate(payload)
    result = ctx.services.system_configuration.save(
        request.timezone,
        request.automation.model_dump(),
        request.delivery.news_time,
        request.delivery.article_time,
    )
    return CommandResult(message=result["message"])


def timezone_get_handler(ctx, args, payload):
    return ctx.services.system_settings.get_timezone()


def timezone_set_handler(ctx, args, payload):
    request = SystemTimezoneConfig.model_validate(payload)
    result = ctx.services.system_settings.set_timezone(request.timezone)
    return CommandResult(message=result["message"])


def schedule_get_handler(ctx, args, payload):
    return ctx.services.delivery_settings.get_schedule()


def schedule_set_handler(ctx, args, payload):
    request = DeliveryScheduleConfig.model_validate(payload)
    result = ctx.services.delivery_settings.set_schedule(request.news_time, request.article_time)
    return CommandResult(message=result["message"])


def automation_get_handler(ctx, args, payload):
    return ctx.services.automation_settings.get_config()


def automation_set_handler(ctx, args, payload):
    result = ctx.services.automation_settings.set_config(payload)
    return CommandResult(message=result["message"])


def telegram_get_handler(ctx, args, payload):
    return ctx.services.telegram_settings.get_config()


def telegram_set_handler(ctx, args, payload):
    result = ctx.services.telegram_settings.set_config(payload)
    return CommandResult(message=result["message"])


async def telegram_test_handler(ctx, args, payload):
    result = await ctx.services.telegram_gateway.send_test_message(payload)
    return CommandResult(data=result, message=result["message"])


def ai_get_handler(ctx, args, payload):
    return ctx.services.ai_provider_settings.get_config()


def ai_set_handler(ctx, args, payload):
    result = ctx.services.ai_provider_settings.set_config(payload)
    return CommandResult(message=result["message"])


async def ai_test_handler(ctx, args, payload):
    return await ctx.services.ai_pipeline.test_ai_connection(payload)


def review_get_handler(ctx, args, payload):
    return ctx.services.review_settings.get_config(args.kind)


def review_set_handler(ctx, args, payload):
    request = AIReviewConfigRequest.model_validate(payload)
    result = ctx.services.review_settings.set_config(request.prompt, request.hours, args.kind)
    return CommandResult(message=result["message"])


def profile_list_handler(ctx, args, payload):
    return ctx.services.editorial_profiles.list_profiles(args.kind)


def profile_save_handler(ctx, args, payload):
    if payload["slug"] != args.slug:
        raise CLIUsageError("路径 slug 与 JSON 中的 slug 不一致")
    saved = ctx.services.editorial_profiles.save_profile(payload)
    return CommandResult(data=saved, message="内容档案已保存")


def rss_list_handler(ctx, args, payload):
    return ctx.services.rss_sources.list_sources()


async def rss_preview_handler(ctx, args, payload):
    return await ctx.services.rss_sources.preview(payload)


def rss_create_handler(ctx, args, payload):
    result = ctx.services.rss_sources.create_source(payload)
    return CommandResult(data=result, message="RSS 源已创建")


def rss_update_handler(ctx, args, payload):
    result = ctx.services.rss_sources.update_source(args.id, payload)
    return CommandResult(data=result, message="RSS 源已更新")


def rss_delete_handler(ctx, args, payload):
    result = ctx.services.rss_sources.delete_source(args.id)
    return CommandResult(message=result["message"])


def analyst_key_list_handler(ctx, args, payload):
    return {"items": ctx.services.analyst_access.get_api_keys()}


async def analyst_key_create_handler(ctx, args, payload):
    request = ApiKeyCreateRequest(key_name=args.name, notes=args.notes)
    result = await ctx.services.analyst_access.create_api_key(request.key_name, request.notes)
    return CommandResult(data=result, message=result["message"])


def analyst_key_enable_handler(ctx, args, payload):
    result = ctx.services.analyst_access.set_api_key_enabled(args.id, True)
    return CommandResult(message=result["message"])


def analyst_key_disable_handler(ctx, args, payload):
    result = ctx.services.analyst_access.set_api_key_enabled(args.id, False)
    return CommandResult(message=result["message"])


async def analyst_key_delete_handler(ctx, args, payload):
    result = await ctx.services.analyst_access.delete_api_key(args.id)
    return CommandResult(message=result["message"])


def _config_specs(resource: str, get_handler, set_handler, input_model):
    return [
        CommandSpec(
            f"config.{resource}.get",
            ("config", resource, "get"),
            f"读取 {resource} 配置",
            get_handler,
        ),
        CommandSpec(
            f"config.{resource}.set",
            ("config", resource, "set"),
            f"保存 {resource} 配置",
            set_handler,
            input_model=input_model,
            input_required=True,
        ),
    ]


def command_specs():
    specs = [
        *_config_specs("system", system_get_handler, system_set_handler, SystemSettingsRequest),
        *_config_specs("timezone", timezone_get_handler, timezone_set_handler, SystemTimezoneConfig),
        *_config_specs("schedule", schedule_get_handler, schedule_set_handler, DeliveryScheduleConfig),
        *_config_specs("automation", automation_get_handler, automation_set_handler, AutomationConfigRequest),
        *_config_specs("telegram", telegram_get_handler, telegram_set_handler, TelegramConfigRequest),
        *_config_specs("ai", ai_get_handler, ai_set_handler, AIProviderConfigRequest),
        CommandSpec(
            "config.telegram.test",
            ("config", "telegram", "test"),
            "使用保存或临时配置发送 Telegram 测试消息",
            telegram_test_handler,
            input_model=TelegramConfigRequest,
            input_required=False,
            requires_yes=True,
        ),
        CommandSpec(
            "config.ai.test",
            ("config", "ai", "test"),
            "测试保存或临时提供的 AI 端点",
            ai_test_handler,
            input_model=AIProviderConfigRequest,
            input_required=False,
        ),
        CommandSpec(
            "config.review.get",
            ("config", "review", "get"),
            "读取指定内容类型的审核设置",
            review_get_handler,
            arguments=(arg("--kind", choices=CONTENT_KINDS, default="news"),),
        ),
        CommandSpec(
            "config.review.set",
            ("config", "review", "set"),
            "保存指定内容类型的审核设置",
            review_set_handler,
            arguments=(arg("--kind", choices=CONTENT_KINDS, default="news"),),
            input_model=AIReviewConfigRequest,
            input_required=True,
        ),
        CommandSpec(
            "profile.list",
            ("profile", "list"),
            "列出内容档案",
            profile_list_handler,
            arguments=(arg("--kind", choices=CONTENT_KINDS),),
        ),
        CommandSpec(
            "profile.save",
            ("profile", "save"),
            "按 slug 创建或更新内容档案",
            profile_save_handler,
            arguments=(arg("slug"),),
            input_model=EditorialProfileRequest,
            input_required=True,
        ),
        CommandSpec("rss.list", ("rss", "list"), "列出 RSS 源", rss_list_handler),
        CommandSpec(
            "rss.preview", ("rss", "preview"), "预览 RSS 内容，不保存或发布", rss_preview_handler,
            input_model=RssPreviewRequest, input_required=True, database_mode="none",
        ),
        CommandSpec(
            "rss.create",
            ("rss", "create"),
            "创建 RSS 源",
            rss_create_handler,
            input_model=RssSourceRequest,
            input_required=True,
        ),
        CommandSpec(
            "rss.update",
            ("rss", "update"),
            "按 ID 更新 RSS 源",
            rss_update_handler,
            arguments=(arg("id", type=int),),
            input_model=RssSourceRequest,
            input_required=True,
        ),
        CommandSpec(
            "rss.delete",
            ("rss", "delete"),
            "删除 RSS 源",
            rss_delete_handler,
            arguments=(arg("id", type=int),),
            requires_yes=True,
        ),
        CommandSpec(
            "analyst-key.list",
            ("analyst-key", "list"),
            "列出分析接口密钥",
            analyst_key_list_handler,
        ),
        CommandSpec(
            "analyst-key.create",
            ("analyst-key", "create"),
            "创建分析接口密钥；明文只返回一次",
            analyst_key_create_handler,
            arguments=(arg("--name", required=True), arg("--notes")),
        ),
        CommandSpec(
            "analyst-key.enable",
            ("analyst-key", "enable"),
            "启用分析接口密钥",
            analyst_key_enable_handler,
            arguments=(arg("id", type=int),),
        ),
        CommandSpec(
            "analyst-key.disable",
            ("analyst-key", "disable"),
            "停用分析接口密钥",
            analyst_key_disable_handler,
            arguments=(arg("id", type=int),),
        ),
        CommandSpec(
            "analyst-key.delete",
            ("analyst-key", "delete"),
            "删除分析接口密钥",
            analyst_key_delete_handler,
            arguments=(arg("id", type=int),),
            requires_yes=True,
        ),
    ]
    return specs
