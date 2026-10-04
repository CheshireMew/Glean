import React, { useCallback, useEffect, useState } from 'react';
import { getPublicAIContent } from '../../api/aiContent';
import { useAIContentRefresh } from '../../hooks/useAIContentRefresh';
import { ArticleItem } from './ArticleList';

const PAGE_SIZE = 20;
const SOURCE_NOTES = {
    hacker_news: '按最近一次获取的 Hacker News 官网首页顺序展示。',
    'rss__juejin-weekly': '来自掘金本周最热 RSS，按周榜顺序展示。',
    waytoagi: '来自 WaytoAGI 文档的近期更新日志，日期为日志日期，介绍取自原文档。',
    'rss__v2ex-tech': '来自 V2EX 首页“技术”栏的官方订阅，顺序以订阅源为准。',
};

export default function AIChannel({ query = '' }) {
    const [source, setSource] = useState('');
    const [pagination, setPagination] = useState({ query, source: '', page: 1 });
    const page = pagination.query === query && pagination.source === source ? pagination.page : 1;
    const [refresh, setRefresh] = useState(0);
    const [result, setResult] = useState({ key: '', data: null, error: '' });
    const requestKey = JSON.stringify([source, query, page]);
    const reloadContent = useCallback(() => setRefresh((value) => value + 1), []);
    const { update, refreshNow } = useAIContentRefresh(reloadContent);
    const pausedSources = (update.sources || []).filter((item) => ['error', 'paused'].includes(item.status));
    const loading = result.key !== requestKey;
    const data = !loading ? result.data : null;
    const error = !loading ? result.error : '';
    const sources = result.data?.sources || [];

    useEffect(() => {
        const controller = new AbortController();
        let active = true;
        getPublicAIContent({ source, query, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE, signal: controller.signal })
            .then((response) => {
                if (active) setResult({ key: requestKey, data: response.data, error: '' });
            })
            .catch((failure) => {
                if (active) setResult((previous) => ({ key: requestKey, data: previous.key === requestKey ? previous.data : null, error: failure.message || '加载失败' }));
            });
        return () => { active = false; controller.abort(); };
    }, [source, query, page, requestKey, refresh]);

    return <section aria-label="AI 资讯" className="w-full bg-white rounded-xl shadow-sm border border-gray-100 min-h-[80vh] dark:bg-gray-900 dark:border-gray-800 transition-colors duration-300">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-100 px-6 py-4 dark:border-gray-800">
            <h2 className="font-bold text-gray-800 dark:text-gray-200">AI 资讯</h2>
            <button type="button" onClick={refreshNow} disabled={update.updating} className="rounded border border-gray-300 px-3 py-1.5 text-xs text-gray-500 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800">{update.updating ? '正在更新…' : '检查更新'}</button>
        </div>
        <nav aria-label="AI 资讯来源" className="flex flex-wrap gap-2 px-6 pt-4">
            <button type="button" aria-pressed={!source} onClick={() => setSource('')} className={`rounded-lg px-3 py-1.5 text-xs ${!source ? 'bg-blue-600 text-white' : 'text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800'}`}>全部来源</button>
            {sources.map((item) => <button key={item.key} type="button" aria-pressed={source === item.key} onClick={() => setSource(item.key)} className={`rounded-lg px-3 py-1.5 text-xs ${source === item.key ? 'bg-blue-600 text-white' : 'text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800'}`}>{item.name}<span className="ml-2 opacity-60">{item.total}</span></button>)}
        </nav>
        <p className="px-6 py-3 text-xs leading-relaxed text-gray-400 dark:text-gray-500">{SOURCE_NOTES[source] || '后台按采集设置自动更新，页面会自动显示最新内容。'}英文内容自动翻译为中文。</p>
        {update.message && <p role="status" className="px-6 pb-3 text-xs text-amber-700 dark:text-amber-400">{update.message}</p>}
        {pausedSources.length > 0 && <details className="px-6 pb-3 text-xs text-amber-700 dark:text-amber-400"><summary>部分来源暂未更新，已有内容仍可阅读</summary>{pausedSources.map((item) => <p key={item.key} className="mt-2">{item.name}：{item.message}</p>)}</details>}
        {error && <div role="alert" className="m-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">加载失败：{error}<button type="button" onClick={reloadContent} className="ml-4 underline">重试</button></div>}
        {loading ? <p role="status" className="p-6 text-center text-sm text-gray-400">加载中...</p> : data && <>
                <p role="status" className="px-6 py-2 text-xs text-gray-400">共 {data?.total || 0} 条{query ? `，搜索“${query}”` : ''}</p>
                <div aria-label="AI 资讯列表" className="divide-y divide-gray-50 dark:divide-gray-800">
                    {data?.items.map((item, index) => <ArticleItem key={item.id} item={item} index={(page - 1) * PAGE_SIZE + index + 1} />)}
                </div>
                {!data?.items.length && <p className="p-6 text-center text-sm text-gray-400">{query ? '无匹配结果' : '暂无采集记录'}</p>}
                <nav aria-label="AI 资讯分页" className="flex items-center justify-center gap-4 border-t border-gray-100 p-4 text-xs text-gray-500 dark:border-gray-800 dark:text-gray-400">
                    <button type="button" disabled={page <= 1} onClick={() => setPagination({ query, source, page: page - 1 })} className="rounded border border-gray-300 px-3 py-1.5 hover:bg-gray-50 disabled:opacity-40 dark:border-gray-700 dark:hover:bg-gray-800">上一页</button>
                    <span>第 {page} 页 / 共 {Math.max(1, Math.ceil((data?.total || 0) / PAGE_SIZE))} 页</span>
                    <button type="button" disabled={page * PAGE_SIZE >= (data?.total || 0)} onClick={() => setPagination({ query, source, page: page + 1 })} className="rounded border border-gray-300 px-3 py-1.5 hover:bg-gray-50 disabled:opacity-40 dark:border-gray-700 dark:hover:bg-gray-800">下一页</button>
                </nav>
            </>}
    </section>;
}
