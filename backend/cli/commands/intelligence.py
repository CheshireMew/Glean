from __future__ import annotations

from backend.app.models.intelligence import (
    AIEvaluationCaseRequest,
    AIEvaluationRunRequest,
    AnalystSubscriptionCreateRequest,
    AnalystSubscriptionUpdateRequest,
    AlertPolicyRequest,
    CorrectionCreateRequest,
    DraftCreateRequest,
    DraftUpdateRequest,
    EditorialEditRequest,
    EntityRequest,
    EventEntityAttachRequest,
    EventFactPatchRequest,
    EventFactRequest,
    EventNarrativeAttachRequest,
    EventRelationRequest,
    EventUpdateRequest,
    EvidenceUpdateRequest,
    MarketExpectationRequest,
    MarketInstrumentRequest,
    MarketSnapshotRequest,
    NarrativeRequest,
    PublicationChannelRequest,
    PublicationUpdateRequest,
    SourceCatalogUpdateRequest,
    SourceIncidentUpdateRequest,
    WatchlistRequest,
)

from ..models import CommandSpec
from ..registry import arg


def event_get(ctx, args, payload):
    return ctx.services.event_intelligence.get_detail(args.id)


def event_evidence(ctx, args, payload):
    request = EvidenceUpdateRequest.model_validate(payload)
    return ctx.services.event_intelligence.update_source_evidence(args.id, args.news_id, request.model_dump(exclude_unset=True))


def event_add_update(ctx, args, payload):
    request = EventUpdateRequest.model_validate(payload)
    return ctx.services.event_intelligence.add_update(args.id, request.model_dump(), "cli")


def event_add_fact(ctx, args, payload):
    request = EventFactRequest.model_validate(payload)
    return ctx.services.event_intelligence.add_fact(args.id, request.model_dump(), "cli")


def event_update_fact(ctx, args, payload):
    request = EventFactPatchRequest.model_validate(payload)
    return ctx.services.event_intelligence.update_fact(
        args.fact_id, request.model_dump(exclude_unset=True), "cli"
    )


def event_add_relation(ctx, args, payload):
    request = EventRelationRequest.model_validate(payload)
    return ctx.services.event_intelligence.add_relation(args.id, request.model_dump(), "cli")


def event_classify(ctx, args, payload):
    return ctx.services.intelligence_catalog.classify_event(args.id)


def intelligence_classify(ctx, args, payload):
    return ctx.services.intelligence_catalog.classify_recent(args.hours, args.limit)


def editorial_get(ctx, args, payload):
    return ctx.services.editorial_workbench.get_entry(args.id)


def editorial_update(ctx, args, payload):
    request = EditorialEditRequest.model_validate(payload)
    return ctx.services.editorial_workbench.update_entry(args.id, request.model_dump(exclude_unset=True), "cli")


def editorial_restore(ctx, args, payload):
    return ctx.services.editorial_workbench.restore_revision(args.id, args.revision, "cli")


def publication_list(ctx, args, payload):
    return {"items": ctx.services.publications.list_publications()}


def publication_update(ctx, args, payload):
    request = PublicationUpdateRequest.model_validate(payload)
    return ctx.services.publications.update_publication(args.id, request.model_dump(exclude_unset=True))


def channel_list(ctx, args, payload):
    return {"items": ctx.services.publications.list_channels()}


def channel_save(ctx, args, payload):
    request = PublicationChannelRequest.model_validate(payload)
    return ctx.services.publications.save_channel(request.model_dump(), args.id)


async def channel_test(ctx, args, payload):
    return await ctx.services.publication_channel_gateway.test_channel(args.id)


def draft_list(ctx, args, payload):
    return {"items": ctx.services.editorial_workbench.list_drafts(args.status, args.limit)}


def draft_create(ctx, args, payload):
    request = DraftCreateRequest.model_validate(payload)
    return ctx.services.editorial_workbench.create_draft(request.model_dump(), "cli")


def draft_update(ctx, args, payload):
    request = DraftUpdateRequest.model_validate(payload)
    return ctx.services.editorial_workbench.update_draft(args.id, request.model_dump(exclude_unset=True))


def draft_preview(ctx, args, payload):
    return ctx.services.publication_workflow.preview_draft(args.id)


async def draft_publish(ctx, args, payload):
    return await ctx.services.publication_workflow.publish_draft(args.id)


async def draft_publish_due(ctx, args, payload):
    return await ctx.services.publication_workflow.publish_due_drafts(args.limit)


def correction_list(ctx, args, payload):
    return {"items": ctx.services.publication_workflow.list_corrections(args.published, args.limit)}


def correction_create(ctx, args, payload):
    request = CorrectionCreateRequest.model_validate(payload)
    return ctx.services.editorial_workbench.add_correction(request.model_dump(), "cli")


async def correction_publish(ctx, args, payload):
    return await ctx.services.publication_workflow.publish_correction(args.id)


def entity_list(ctx, args, payload):
    return {"items": ctx.services.intelligence_catalog.list_entities(args.type, args.query)}


def entity_save(ctx, args, payload):
    request = EntityRequest.model_validate(payload)
    return ctx.services.intelligence_catalog.save_entity(request.model_dump(), args.id)


def entity_attach(ctx, args, payload):
    request = EventEntityAttachRequest.model_validate(payload)
    return ctx.services.intelligence_catalog.attach_entity(args.event_id, request.model_dump())


def narrative_list(ctx, args, payload):
    return {"items": ctx.services.intelligence_catalog.list_narratives(args.enabled_only)}


def narrative_save(ctx, args, payload):
    request = NarrativeRequest.model_validate(payload)
    return ctx.services.intelligence_catalog.save_narrative(request.model_dump(), args.id)


def narrative_attach(ctx, args, payload):
    request = EventNarrativeAttachRequest.model_validate(payload)
    return ctx.services.intelligence_catalog.attach_narrative(args.event_id, request.model_dump())


def watchlist_list(ctx, args, payload):
    return {"items": ctx.services.intelligence_catalog.list_watchlists()}


def watchlist_save(ctx, args, payload):
    request = WatchlistRequest.model_validate(payload)
    return ctx.services.intelligence_catalog.save_watchlist(request.model_dump(), args.id)


def alert_list(ctx, args, payload):
    return {"items": ctx.services.intelligence_catalog.list_alert_policies()}


def alert_save(ctx, args, payload):
    request = AlertPolicyRequest.model_validate(payload)
    return ctx.services.intelligence_catalog.save_alert_policy(request.model_dump(), args.id)


def alert_evaluate(ctx, args, payload):
    return ctx.services.intelligence_catalog.evaluate_alerts(args.id, args.hours)


def alert_matches(ctx, args, payload):
    return {"items": ctx.services.intelligence_catalog.list_alert_matches(args.status, args.limit)}


async def alert_deliver(ctx, args, payload):
    return await ctx.services.publication_workflow.deliver_alert_matches(args.limit)


def analyst_subscription_list(ctx, args, payload):
    return {"items": ctx.services.analyst_subscriptions.list_subscriptions()}


def analyst_subscription_create(ctx, args, payload):
    request = AnalystSubscriptionCreateRequest.model_validate(payload)
    return ctx.services.analyst_subscriptions.create(request.model_dump())


def analyst_subscription_update(ctx, args, payload):
    request = AnalystSubscriptionUpdateRequest.model_validate(payload)
    return ctx.services.analyst_subscriptions.update(
        args.id, request.model_dump(exclude_unset=True)
    )


async def analyst_subscription_deliver(ctx, args, payload):
    return await ctx.services.analyst_subscriptions.deliver(args.id)


def source_list(ctx, args, payload):
    return {"items": ctx.services.source_operations.list_sources()}


def source_update(ctx, args, payload):
    request = SourceCatalogUpdateRequest.model_validate(payload)
    return ctx.services.source_operations.update_source(args.key, request.model_dump(exclude_unset=True))


def source_snapshot(ctx, args, payload):
    return ctx.services.source_operations.snapshot(args.key, args.hours)


def incident_list(ctx, args, payload):
    return {"items": ctx.services.source_operations.list_incidents(args.status, args.limit)}


def incident_update(ctx, args, payload):
    request = SourceIncidentUpdateRequest.model_validate(payload)
    return ctx.services.source_operations.update_incident(args.id, request.status)


def market_list(ctx, args, payload):
    return {"items": ctx.services.market_intelligence.list_instruments()}


def market_save(ctx, args, payload):
    request = MarketInstrumentRequest.model_validate(payload)
    return ctx.services.market_intelligence.save_instrument(request.model_dump(), args.id)


def market_event(ctx, args, payload):
    return ctx.services.market_intelligence.get_event_market(args.event_id)


async def market_refresh(ctx, args, payload):
    return await ctx.services.market_intelligence.refresh_event(args.event_id)


def market_snapshot(ctx, args, payload):
    request = MarketSnapshotRequest.model_validate(payload)
    return ctx.services.market_intelligence.save_snapshot(args.event_id, args.instrument_id, request.model_dump())


def market_expectation(ctx, args, payload):
    request = MarketExpectationRequest.model_validate(payload)
    return ctx.services.market_intelligence.save_expectation(args.event_id, args.instrument_id, request.model_dump())


def ai_summary(ctx, args, payload):
    return ctx.services.ai_quality.summary(args.days)


def ai_invocations(ctx, args, payload):
    result = ctx.services.ai_quality.list_invocations(args.page, args.limit, args.days, args.stage, args.provider, args.profile, args.success)
    return {"items": result["results"], "pagination": {key: result[key] for key in ("total", "page", "limit")}}


def ai_case_list(ctx, args, payload):
    return {"items": ctx.services.ai_quality.list_cases(args.enabled)}


def ai_case_save(ctx, args, payload):
    request = AIEvaluationCaseRequest.model_validate(payload)
    return ctx.services.ai_quality.save_case(request.model_dump(), args.id)


async def ai_evaluate(ctx, args, payload):
    request = AIEvaluationRunRequest.model_validate(payload or {})
    return await ctx.services.ai_quality.run_evaluation(request.case_ids, request.provider_name)


def _input_spec(command_id, path, help_text, handler, model, arguments=()):
    return CommandSpec(command_id, path, help_text, handler, arguments=arguments, input_model=model, input_required=True)


def command_specs():
    id_optional = (arg("--id", type=int),)
    limit = arg("--limit", type=int, default=200)
    return [
        CommandSpec("event.get", ("event", "get"), "读取事件证据、进展、实体、叙事和审核结果", event_get, arguments=(arg("id", type=int),)),
        _input_spec("event.evidence", ("event", "evidence"), "更新事件来源的证据关系", event_evidence, EvidenceUpdateRequest, (arg("id", type=int), arg("news_id", type=int))),
        _input_spec("event.update.add", ("event", "update", "add"), "添加事件进展", event_add_update, EventUpdateRequest, (arg("id", type=int),)),
        _input_spec("event.fact.add", ("event", "fact", "add"), "添加结构化关键事实", event_add_fact, EventFactRequest, (arg("id", type=int),)),
        _input_spec("event.fact.update", ("event", "fact", "update"), "更新结构化关键事实", event_update_fact, EventFactPatchRequest, (arg("fact_id", type=int),)),
        _input_spec("event.relation.add", ("event", "relation", "add"), "关联前因、结果或相关事件", event_add_relation, EventRelationRequest, (arg("id", type=int),)),
        CommandSpec("event.classify", ("event", "classify"), "根据实体别名和叙事关键词自动识别事件", event_classify, arguments=(arg("id", type=int),)),
        CommandSpec("intelligence.classify", ("intelligence", "classify"), "批量识别近期事件的实体和叙事", intelligence_classify, arguments=(arg("--hours", type=int, default=168), arg("--limit", type=int, default=500))),
        CommandSpec("editorial.get", ("editorial", "get"), "读取编辑稿和修订记录", editorial_get, arguments=(arg("id", type=int),)),
        _input_spec("editorial.update", ("editorial", "update"), "保存人工编辑并生成修订", editorial_update, EditorialEditRequest, (arg("id", type=int),)),
        CommandSpec("editorial.restore", ("editorial", "restore"), "恢复指定编辑修订", editorial_restore, arguments=(arg("id", type=int), arg("revision", type=int))),
        CommandSpec("publication.list", ("publication", "list"), "列出内容档案对应的发布频道", publication_list),
        _input_spec("publication.update", ("publication", "update"), "更新发布频道、模板和投递目标", publication_update, PublicationUpdateRequest, (arg("id", type=int),)),
        CommandSpec("channel.list", ("channel", "list"), "列出 Telegram、邮件和 Webhook 渠道", channel_list),
        _input_spec("channel.save", ("channel", "save"), "创建或更新投递渠道", channel_save, PublicationChannelRequest, id_optional),
        CommandSpec("channel.test", ("channel", "test"), "发送渠道测试消息", channel_test, arguments=(arg("id", type=int),), requires_yes=True),
        CommandSpec("draft.list", ("draft", "list"), "列出发布草稿", draft_list, arguments=(arg("--status"), arg("--limit", type=int, default=100))),
        _input_spec("draft.create", ("draft", "create"), "创建可审阅的发布草稿", draft_create, DraftCreateRequest),
        _input_spec("draft.update", ("draft", "update"), "更新、排期或取消发布草稿", draft_update, DraftUpdateRequest, (arg("id", type=int),)),
        CommandSpec("draft.preview", ("draft", "preview"), "生成最终排版但不投递", draft_preview, arguments=(arg("id", type=int),)),
        CommandSpec("draft.publish", ("draft", "publish"), "向草稿配置的全部渠道发布", draft_publish, arguments=(arg("id", type=int),), requires_yes=True),
        CommandSpec("draft.publish-due", ("draft", "publish-due"), "发布所有到期草稿", draft_publish_due, arguments=(arg("--limit", type=int, default=100),), requires_yes=True),
        CommandSpec("correction.list", ("correction", "list"), "列出发布更正", correction_list, arguments=(arg("--published", action="store_true", default=None), limit)),
        _input_spec("correction.create", ("correction", "create"), "创建发布更正", correction_create, CorrectionCreateRequest),
        CommandSpec("correction.publish", ("correction", "publish"), "向关联发布频道发送更正", correction_publish, arguments=(arg("id", type=int),), requires_yes=True),
        CommandSpec("entity.list", ("entity", "list"), "查询实体目录", entity_list, arguments=(arg("--type"), arg("--query"))),
        _input_spec("entity.save", ("entity", "save"), "创建或更新实体", entity_save, EntityRequest, id_optional),
        _input_spec("entity.attach", ("entity", "attach"), "把实体关联到事件", entity_attach, EventEntityAttachRequest, (arg("event_id", type=int),)),
        CommandSpec("narrative.list", ("narrative", "list"), "列出叙事", narrative_list, arguments=(arg("--enabled-only", action="store_true"),)),
        _input_spec("narrative.save", ("narrative", "save"), "创建或更新叙事", narrative_save, NarrativeRequest, id_optional),
        _input_spec("narrative.attach", ("narrative", "attach"), "把叙事关联到事件", narrative_attach, EventNarrativeAttachRequest, (arg("event_id", type=int),)),
        CommandSpec("watchlist.list", ("watchlist", "list"), "列出关注列表", watchlist_list),
        _input_spec("watchlist.save", ("watchlist", "save"), "创建或更新关注列表", watchlist_save, WatchlistRequest, id_optional),
        CommandSpec("alert.list", ("alert", "list"), "列出提醒规则", alert_list),
        _input_spec("alert.save", ("alert", "save"), "创建或更新提醒规则", alert_save, AlertPolicyRequest, id_optional),
        CommandSpec("alert.evaluate", ("alert", "evaluate"), "评估提醒规则并生成匹配", alert_evaluate, arguments=(arg("--id", type=int), arg("--hours", type=int, default=24))),
        CommandSpec("alert.matches", ("alert", "matches"), "列出提醒匹配", alert_matches, arguments=(arg("--status"), limit)),
        CommandSpec("alert.deliver", ("alert", "deliver"), "投递待处理提醒", alert_deliver, arguments=(limit,), requires_yes=True),
        CommandSpec("analyst-subscription.list", ("analyst-subscription", "list"), "列出结构化变更 Webhook 订阅", analyst_subscription_list),
        _input_spec("analyst-subscription.create", ("analyst-subscription", "create"), "创建结构化变更 Webhook 订阅", analyst_subscription_create, AnalystSubscriptionCreateRequest),
        _input_spec("analyst-subscription.update", ("analyst-subscription", "update"), "更新结构化变更 Webhook 订阅", analyst_subscription_update, AnalystSubscriptionUpdateRequest, (arg("id", type=int),)),
        CommandSpec("analyst-subscription.deliver", ("analyst-subscription", "deliver"), "检查并投递分析师变更", analyst_subscription_deliver, arguments=(arg("--id", type=int),), requires_yes=True),
        CommandSpec("source.list", ("source", "list"), "列出来源目录和最新健康度", source_list),
        _input_spec("source.update", ("source", "update"), "更新来源权威级别和一手来源标记", source_update, SourceCatalogUpdateRequest, (arg("key"),)),
        CommandSpec("source.snapshot", ("source", "snapshot"), "生成来源质量快照和异常", source_snapshot, arguments=(arg("--key"), arg("--hours", type=int, default=24))),
        CommandSpec("source.incidents", ("source", "incidents"), "列出来源异常", incident_list, arguments=(arg("--status"), limit)),
        _input_spec("source.incident.update", ("source", "incident", "update"), "确认或解决来源异常", incident_update, SourceIncidentUpdateRequest, (arg("id", type=int),)),
        CommandSpec("market.instrument.list", ("market", "instrument", "list"), "列出实体行情品种", market_list),
        _input_spec("market.instrument.save", ("market", "instrument", "save"), "创建或更新行情品种", market_save, MarketInstrumentRequest, id_optional),
        CommandSpec("market.event", ("market", "event"), "读取事件行情窗口和影响评估", market_event, arguments=(arg("event_id", type=int),)),
        CommandSpec("market.refresh", ("market", "refresh"), "从行情提供方刷新事件窗口", market_refresh, arguments=(arg("event_id", type=int),)),
        _input_spec("market.snapshot", ("market", "snapshot"), "写入手工行情快照", market_snapshot, MarketSnapshotRequest, (arg("event_id", type=int), arg("instrument_id", type=int))),
        _input_spec("market.expectation", ("market", "expectation"), "保存事前方向和影响判断", market_expectation, MarketExpectationRequest, (arg("event_id", type=int), arg("instrument_id", type=int))),
        CommandSpec("ai-quality.summary", ("ai-quality", "summary"), "读取 AI 成功率、耗时、费用和反馈", ai_summary, arguments=(arg("--days", type=int, default=30),)),
        CommandSpec("ai-quality.invocations", ("ai-quality", "invocations"), "查询 AI 调用明细", ai_invocations, arguments=(arg("--page", type=int, default=1), arg("--limit", type=int, default=50), arg("--days", type=int, default=30), arg("--stage"), arg("--provider"), arg("--profile"), arg("--success", action="store_true", default=None))),
        CommandSpec("ai-quality.case.list", ("ai-quality", "case", "list"), "列出固定 AI 评测样例", ai_case_list, arguments=(arg("--enabled", action="store_true", default=None),)),
        _input_spec("ai-quality.case.save", ("ai-quality", "case", "save"), "创建或更新固定 AI 评测样例", ai_case_save, AIEvaluationCaseRequest, id_optional),
        CommandSpec("ai-quality.evaluate", ("ai-quality", "evaluate"), "执行固定 AI 评测", ai_evaluate, input_model=AIEvaluationRunRequest, input_required=False, requires_yes=True),
    ]
