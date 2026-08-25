import React from 'react';
import { formatLocalTime } from '../../utils/time';
import VirtualWindowList from './VirtualWindowList';
import { Link } from 'react-router-dom';

export function NewsItem({ item }) {
    return (
        <div className="relative pl-6 mb-4">
            <div className="absolute left-[7px] top-1.5 w-1.5 h-1.5 bg-gray-300 rounded-full border border-white dark:bg-gray-600 dark:border-gray-800"></div>
            <div className="flex items-center gap-2 mb-1">
                <span className="text-xs text-gray-400 dark:text-gray-500">{formatLocalTime(item.published_at)}</span>
                {item.ai_tag && <span className="text-[10px] px-1.5 py-0.5 rounded uppercase bg-blue-50 text-blue-700 font-medium dark:bg-blue-900/30 dark:text-blue-300">{item.ai_tag}</span>}
            </div>
            <p className="text-sm leading-snug line-clamp-2">
                {item.event_id ? (
                    <Link to={`/events/${item.event_id}`} className="text-gray-700 hover:text-blue-600 transition-colors dark:text-gray-300 dark:hover:text-blue-400">{item.title}</Link>
                ) : (
                    <a href={item.source_url} target="_blank" rel="noopener noreferrer" className="text-gray-700 hover:text-blue-600 transition-colors dark:text-gray-300 dark:hover:text-blue-400">{item.title}</a>
                )}
            </p>
            {(item.enriched_summary || item.review_summary) && (
                <p className="mt-1 text-xs leading-relaxed text-gray-500 dark:text-gray-400 line-clamp-2">{item.enriched_summary || item.review_summary}</p>
            )}
            {item.source_count > 1 && <span className="mt-1 inline-block text-[10px] text-blue-600 dark:text-blue-400">{item.source_count} 个来源交叉印证</span>}
        </div>
    );
}

export default function NewsTimeline({ items, loadingMore, hasMore, searchQuery, compact = false }) {
    const containerClass = compact ? 'relative' : 'p-4 relative';
    return (
        <>
            <div className={containerClass}>
                <div className="absolute left-6 top-4 bottom-4 w-px bg-gray-200 dark:bg-gray-800"></div>
                <VirtualWindowList
                    items={items}
                    estimateSize={112}
                    ariaLabel="快讯列表"
                    renderItem={(item) => <NewsItem item={item} />}
                />
            </div>
            <div className={`${compact ? 'p-4' : 'mt-4'} text-center text-xs text-gray-400 relative z-10 bg-white dark:bg-gray-900`}>
                {loadingMore && <span>{compact ? '正在加载更多...' : '加载中...'}</span>}
                {!hasMore && items.length > 0 && <span>{compact ? '已加载全部内容' : '已加载全部快讯'}</span>}
                {searchQuery && items.length === 0 && <span>无匹配结果</span>}
            </div>
        </>
    );
}
