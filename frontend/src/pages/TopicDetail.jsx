import React, { useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import { ArrowLeft, Buildings, Path } from '@phosphor-icons/react';
import { Link, useParams } from 'react-router-dom';

import { getPublicEntity, getPublicNarrative } from '../api/intelligence';
import { formatLocalDateTime } from '../utils/time';

export default function TopicDetail({ type }) {
    const { slug } = useParams();
    const [state, setState] = useState({ loading: true, error: '', topic: null });
    useEffect(() => {
        let cancelled = false;
        const request = type === 'entity' ? getPublicEntity(slug, { limit: 100 }) : getPublicNarrative(slug, { limit: 100 });
        request.then((response) => { if (!cancelled) setState({ loading: false, error: '', topic: response.data }); })
            .catch((error) => { if (!cancelled) setState({ loading: false, error: error.message || '专题加载失败', topic: null }); });
        return () => { cancelled = true; };
    }, [slug, type]);
    if (state.loading) return <div className="min-h-screen grid place-items-center bg-slate-50 text-slate-500">正在读取专题…</div>;
    if (state.error || !state.topic) return <main className="min-h-screen grid place-items-center bg-slate-50 p-6"><div className="rounded-2xl border bg-white p-8 text-center"><p>{state.error}</p><Link to="/" className="mt-4 inline-flex items-center gap-2 text-blue-600"><ArrowLeft />返回首页</Link></div></main>;
    const topic = state.topic; const events = topic.events || { items: [], total: 0 };
    return <div className="min-h-screen bg-slate-50 text-slate-900">
        <header className="border-b border-slate-200 bg-white"><div className="mx-auto max-w-5xl px-5 py-4"><Link to="/" className="inline-flex items-center gap-2 text-sm text-slate-600 hover:text-blue-600"><ArrowLeft />返回 Glean</Link></div></header>
        <main className="mx-auto max-w-5xl px-5 py-8">
            <section className="rounded-2xl border border-slate-200 bg-white p-7 shadow-sm">
                <div className="flex items-start gap-4"><div className={`grid h-12 w-12 shrink-0 place-items-center rounded-xl ${type === 'entity' ? 'bg-blue-50 text-blue-600' : 'bg-violet-50 text-violet-600'}`}>{type === 'entity' ? <Buildings size={26} /> : <Path size={26} />}</div><div><div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">{type === 'entity' ? topic.entity_type : 'Narrative'}</div><h1 className="mt-1 text-3xl font-bold">{topic.name}{topic.symbol && <span className="ml-3 text-xl text-slate-400">{topic.symbol}</span>}</h1><p className="mt-3 max-w-3xl leading-7 text-slate-600">{topic.description || '暂无说明'}</p>{topic.aliases?.length > 0 && <p className="mt-3 text-sm text-slate-400">别名：{topic.aliases.join('、')}</p>}</div></div>
            </section>
            {type === 'narrative' && topic.trend?.points?.length > 0 && <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><div className="flex items-end justify-between"><div><h2 className="text-lg font-bold">90 天叙事趋势</h2><p className="mt-1 text-sm text-slate-500">按公开事件首次出现日期统计。</p></div><span className="text-sm text-slate-400">{topic.trend.total} 个事件</span></div><div className="mt-5 flex h-32 items-end gap-1" aria-label="叙事趋势图">{topic.trend.points.map((point) => { const peak = Math.max(...topic.trend.points.map((item) => item.count), 1); return <div key={point.date} title={`${point.date}：${point.count}`} className="min-w-1 flex-1 rounded-t bg-violet-400" style={{ height: `${Math.max(8, (point.count / peak) * 100)}%` }} />; })}</div></section>}
            <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><div className="flex items-end justify-between"><div><h2 className="text-lg font-bold">相关事件</h2><p className="mt-1 text-sm text-slate-500">只展示已经公开发布的事件。</p></div><span className="text-sm text-slate-400">{events.total} 个</span></div><div className="mt-5 divide-y divide-slate-100">{events.items.map((event) => <Link key={event.id} to={`/events/${event.id}`} className="block py-4 first:pt-0 last:pb-0 hover:text-blue-600"><div className="font-semibold">{event.title}</div><div className="mt-1 text-xs text-slate-400">{formatLocalDateTime(event.last_seen_at || event.published_at)} · {event.content_type === 'news' ? '快讯' : '文章'}</div></Link>)}{events.items.length === 0 && <div className="py-10 text-center text-slate-400">暂无公开事件</div>}</div></section>
        </main>
    </div>;
}

TopicDetail.propTypes = { type: PropTypes.oneOf(['entity', 'narrative']).isRequired };
