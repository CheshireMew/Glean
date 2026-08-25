import React, { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, ArrowSquareOut, CheckCircle, Clock, WarningCircle } from '@phosphor-icons/react';

import { getPublicEvent } from '../api/editorial';
import { formatLocalDateTime } from '../utils/time';

const ROLE_LABELS = {
    primary: '一手来源',
    independent: '独立报道',
    reporting: '媒体报道',
    repost: '转载',
    commentary: '评论',
};

function readJson(value, fallback = []) {
    if (Array.isArray(value)) return value;
    try { return JSON.parse(value || '[]'); } catch { return fallback; }
}

export default function EventDetail() {
    const { eventId } = useParams();
    const [state, setState] = useState({ loading: true, error: '', detail: null });

    useEffect(() => {
        const controller = new AbortController();
        const timer = window.setTimeout(() => {
            setState({ loading: true, error: '', detail: null });
            getPublicEvent(eventId, controller.signal)
                .then((response) => setState({ loading: false, error: '', detail: response.data }))
                .catch((error) => {
                    if (error.name !== 'CanceledError') {
                        setState({ loading: false, error: error.message || '事件加载失败', detail: null });
                    }
                });
        }, 0);
        return () => {
            window.clearTimeout(timer);
            controller.abort();
        };
    }, [eventId]);

    const review = useMemo(() => state.detail?.reviews?.[0] || null, [state.detail]);
    const citations = readJson(review?.enrichment_citations);

    if (state.loading) {
        return <div className="min-h-screen grid place-items-center bg-slate-50 text-slate-500">正在读取事件证据…</div>;
    }
    if (state.error || !state.detail) {
        return (
            <main className="min-h-screen grid place-items-center bg-slate-50 p-6">
                <div className="max-w-lg rounded-2xl border border-red-200 bg-white p-8 text-center shadow-sm">
                    <WarningCircle size={34} className="mx-auto text-red-500" />
                    <h1 className="mt-3 text-lg font-bold">无法打开这个事件</h1>
                    <p className="mt-2 text-sm text-slate-500">{state.error}</p>
                    <Link to="/" className="mt-5 inline-flex items-center gap-2 text-blue-600"><ArrowLeft />返回内容流</Link>
                </div>
            </main>
        );
    }

    const { event, sources, independent_source_count: independentCount, updates, facts = [], relations = [], entities, narratives, corrections, markets = [] } = state.detail;
    return (
        <div className="min-h-screen bg-slate-50 text-slate-900">
            <header className="border-b border-slate-200 bg-white">
                <div className="mx-auto flex max-w-5xl items-center justify-between px-5 py-4">
                    <Link to="/" className="inline-flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-blue-600"><ArrowLeft />返回 AINews</Link>
                    <span className="text-xs font-semibold uppercase tracking-[0.18em] text-blue-600">可验证事件</span>
                </div>
            </header>
            <main className="mx-auto max-w-5xl px-5 py-8">
                <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm md:p-8">
                    <div className="flex flex-wrap gap-2 text-xs">
                        <span className="rounded-full bg-blue-50 px-3 py-1 font-medium text-blue-700">事件 #{event.id}</span>
                        <span className="rounded-full bg-emerald-50 px-3 py-1 font-medium text-emerald-700">{independentCount} 组独立证据</span>
                        {entities.map((entity) => <Link to={`/entities/${entity.slug}`} key={`${entity.id}-${entity.role}`} className="rounded-full bg-slate-100 px-3 py-1 hover:bg-blue-50 hover:text-blue-700">{entity.symbol || entity.name}</Link>)}
                        {narratives.map((item) => <Link to={`/narratives/${item.slug}`} key={item.id} className="rounded-full bg-violet-50 px-3 py-1 text-violet-700 hover:bg-violet-100">{item.name}</Link>)}
                    </div>
                    <h1 className="mt-5 text-2xl font-bold leading-tight md:text-3xl">{event.title}</h1>
                    <div className="mt-3 flex flex-wrap gap-4 text-sm text-slate-500">
                        <span className="inline-flex items-center gap-1.5"><Clock />首次出现 {formatLocalDateTime(event.first_seen_at)}</span>
                        <span>最近更新 {formatLocalDateTime(event.last_seen_at)}</span>
                        <span>{sources.length} 条来源记录</span>
                    </div>
                    {review?.enriched_summary && <p className="mt-6 text-base leading-8 text-slate-700">{review.enriched_summary}</p>}
                    {review?.enriched_impact && (
                        <div className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-4">
                            <h2 className="font-semibold text-amber-900">为什么重要</h2>
                            <p className="mt-1 text-sm leading-7 text-amber-900/80">{review.enriched_impact}</p>
                        </div>
                    )}
                </section>

                {updates.length > 0 && (
                    <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                        <h2 className="text-lg font-bold">事件进展</h2>
                        <ol className="mt-5 border-l-2 border-blue-100 pl-5">
                            {updates.map((update) => (
                                <li key={update.id} className="relative pb-6 last:pb-0">
                                    <span className="absolute -left-[27px] top-1 h-3 w-3 rounded-full border-2 border-white bg-blue-500" />
                                    <div className="text-xs text-slate-400">{formatLocalDateTime(update.occurred_at)}</div>
                                    <h3 className="mt-1 font-semibold">{update.title}</h3>
                                    {update.summary && <p className="mt-1 text-sm leading-6 text-slate-600">{update.summary}</p>}
                                </li>
                            ))}
                        </ol>
                    </section>
                )}

                {facts.length > 0 && <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><div><h2 className="text-lg font-bold">关键事实</h2><p className="mt-1 text-sm text-slate-500">编辑核验后整理的结构化事实，可追溯到具体来源。</p></div><ul className="mt-5 space-y-3">{facts.map((fact) => <li key={fact.id} className="rounded-xl border border-slate-200 p-4"><div className="flex flex-wrap items-center gap-2"><span className={`rounded-full px-2 py-1 text-xs font-medium ${fact.verification_status === 'verified' ? 'bg-emerald-50 text-emerald-700' : fact.verification_status === 'disputed' ? 'bg-red-50 text-red-700' : 'bg-slate-100 text-slate-600'}`}>{fact.verification_status === 'verified' ? '已核验' : fact.verification_status === 'disputed' ? '有争议' : '待核验'}</span><span className="text-xs text-slate-400">置信度 {Math.round(Number(fact.confidence) * 100)}%</span></div><p className="mt-2 leading-7 text-slate-700">{fact.fact_text}</p>{fact.source_url && <a href={fact.source_url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex items-center gap-1 text-sm text-blue-600 hover:underline">依据：{fact.source_site} · {fact.source_title}<ArrowSquareOut /></a>}</li>)}</ul></section>}

                {relations.length > 0 && <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><div><h2 className="text-lg font-bold">关联事件</h2><p className="mt-1 text-sm text-slate-500">帮助区分前因、结果、后续与相互矛盾的公开事件。</p></div><div className="mt-5 grid gap-3 md:grid-cols-2">{relations.map((relation) => <Link key={relation.id} to={`/events/${relation.related_id}`} className="rounded-xl border border-slate-200 p-4 hover:border-blue-300 hover:text-blue-700"><div className="text-xs font-semibold uppercase tracking-wide text-slate-400">{relation.relation_type}</div><div className="mt-1 font-semibold">{relation.related_title}</div>{relation.notes && <p className="mt-2 text-sm text-slate-500">{relation.notes}</p>}</Link>)}</div></section>}

                <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                    <div className="flex items-end justify-between gap-4">
                        <div><h2 className="text-lg font-bold">来源与证据关系</h2><p className="mt-1 text-sm text-slate-500">来源数量不等于独立证据数量；转载会归入同一证据组。</p></div>
                        <span className="text-sm font-medium text-emerald-700">{independentCount} 组</span>
                    </div>
                    <div className="mt-5 grid gap-3">
                        {sources.map((source) => (
                            <article key={source.id} className="rounded-xl border border-slate-200 p-4">
                                <div className="flex flex-wrap items-center gap-2 text-xs">
                                    <span className="rounded bg-slate-100 px-2 py-1 font-medium">{ROLE_LABELS[source.source_role] || source.source_role}</span>
                                    {source.verification_status === 'verified' && <span className="inline-flex items-center gap-1 text-emerald-700"><CheckCircle />已核验</span>}
                                    <span className="text-slate-400">{source.evidence_group || `独立来源 ${source.id}`}</span>
                                </div>
                                <a href={source.source_url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex items-start gap-2 font-semibold leading-6 hover:text-blue-600">{source.title}<ArrowSquareOut className="mt-1 shrink-0" /></a>
                                <div className="mt-2 text-xs text-slate-500">{source.source_site} · {formatLocalDateTime(source.published_at)}</div>
                                {source.evidence_notes && <p className="mt-2 text-sm text-slate-600">{source.evidence_notes}</p>}
                            </article>
                        ))}
                    </div>
                </section>

                {(review?.enriched_background || citations.length > 0) && (
                    <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                        <h2 className="text-lg font-bold">背景与引用</h2>
                        {review?.enriched_background && <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-600">{review.enriched_background}</p>}
                        {citations.length > 0 && <ul className="mt-4 space-y-2">{citations.map((citation, index) => <li key={citation.news_id || index}><a className="text-sm text-blue-600 hover:underline" href={citation.source_url} target="_blank" rel="noopener noreferrer">{citation.source_site}：{citation.title}</a></li>)}</ul>}
                    </section>
                )}

                {markets.length > 0 && <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><div><h2 className="text-lg font-bold">事件后的市场反应</h2><p className="mt-1 text-sm text-slate-500">按事件发生时点计算，不代表事件是价格变化的唯一原因。</p></div><div className="mt-5 grid gap-3 md:grid-cols-2">{markets.map(({ instrument, assessment, snapshots }) => <article key={instrument.id} className="rounded-xl border border-slate-200 p-4"><div className="flex items-center justify-between"><strong>{instrument.entity_name} · {instrument.symbol}/{instrument.quote_symbol}</strong>{assessment?.realized_direction && <span className={`rounded-full px-2 py-1 text-xs font-medium ${assessment.realized_direction === 'positive' ? 'bg-emerald-50 text-emerald-700' : assessment.realized_direction === 'negative' ? 'bg-red-50 text-red-700' : 'bg-slate-100 text-slate-600'}`}>{assessment.realized_direction}</span>}</div><div className="mt-3 grid grid-cols-3 gap-2 text-center text-sm">{[['15 分钟', assessment?.return_15m], ['1 小时', assessment?.return_1h], ['24 小时', assessment?.return_24h]].map(([label, value]) => <div key={label} className="rounded-lg bg-slate-50 p-2"><div className="text-xs text-slate-400">{label}</div><div className={`mt-1 font-semibold ${value > 0 ? 'text-emerald-600' : value < 0 ? 'text-red-600' : ''}`}>{value == null ? '—' : `${(Number(value) * 100).toFixed(2)}%`}</div></div>)}</div><div className="mt-2 text-xs text-slate-400">已记录 {snapshots.length} 个观察窗口{assessment?.expected_direction ? ` · 事前判断 ${assessment.expected_direction}` : ''}</div></article>)}</div></section>}

                {corrections.length > 0 && (
                    <section className="mt-6 rounded-2xl border border-red-200 bg-red-50 p-6">
                        <h2 className="font-bold text-red-900">更正记录</h2>
                        <ul className="mt-3 space-y-3">{corrections.map((item) => <li key={item.id} className="text-sm leading-6 text-red-900/80"><strong>{item.correction_type}</strong>：{item.message}</li>)}</ul>
                    </section>
                )}
            </main>
        </div>
    );
}
