import React, { useEffect, useId, useRef } from 'react';
import { formatLocalDateTime } from '../../utils/time';

export function DailyReportItem({ report, index, onClick }) {
    const isLongform = report.type === 'article';
    return (
        <button type="button" className="flex gap-4 px-6 py-5 hover:bg-gray-50 transition group cursor-pointer dark:hover:bg-gray-800/50 w-full text-left" onClick={onClick}>
            <div className="text-gray-300 font-medium text-lg min-w-[20px] dark:text-gray-600">{index}</div>
            <div className="flex-1">
                <h3 className="text-base font-medium text-slate-800 mb-1 dark:text-gray-200 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                    {report.date} {isLongform ? '深度文章合集' : '精选快讯合集'}
                </h3>
                <div className="flex items-center gap-3 text-xs text-gray-400 mt-2 dark:text-gray-500">
                    <span className="bg-blue-100 text-blue-600 px-1.5 py-0.5 rounded dark:bg-blue-900/30 dark:text-blue-300">
                        {isLongform ? '日报' : '快讯'}
                    </span>
                    <span>{report.date}</span>
                    <span>{report.news_count} 条内容</span>
                </div>
            </div>
        </button>
    );
}

export function DailyReportContent({ report }) {
    const items = report.items || [];

    if (items.length === 0) {
        const parser = new DOMParser();
        const text = parser.parseFromString(report.content || '', 'text/html').body.textContent || '这份历史日报没有结构化明细。';
        return <p className="whitespace-pre-wrap text-sm leading-7 text-gray-700 dark:text-gray-300">{text}</p>;
    }

    return (
        <div className="space-y-4">
            {items.map((item, index) => (
                <article key={item.id || index} className="flex gap-3 items-start group border-b border-gray-100 pb-4 last:border-0 dark:border-gray-800">
                    <span className="text-gray-400 font-medium min-w-[24px] text-right mt-0.5">{item.position || index + 1}.</span>
                    <div className="min-w-0 flex-1">
                        <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-gray-500">
                            <span className="rounded bg-blue-50 px-2 py-0.5 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">{item.section || '其他'}</span>
                            <span>{item.source_site}</span>
                            {item.source_count > 1 && <span>{item.source_count} 个来源交叉印证</span>}
                        </div>
                        <a href={item.source_url} target="_blank" rel="noopener noreferrer" className="text-gray-800 dark:text-gray-200 hover:text-blue-600 dark:hover:text-blue-400 font-medium leading-normal transition-colors">
                            {item.title}
                        </a>
                        {(item.enriched_summary || item.review_summary) && <p className="mt-2 text-sm leading-6 text-gray-600 dark:text-gray-400">{item.enriched_summary || item.review_summary}</p>}
                        {item.enriched_impact && <p className="mt-2 text-sm leading-6 text-gray-600 dark:text-gray-400"><strong>影响：</strong>{item.enriched_impact}</p>}
                        {item.enriched_background && <p className="mt-2 text-sm leading-6 text-gray-500 dark:text-gray-500"><strong>背景：</strong>{item.enriched_background}</p>}
                    </div>
                </article>
            ))}
        </div>
    );
}

export default function DailyReportModal({ report, onClose }) {
    const titleId = useId();
    const dialogRef = useRef(null);
    const closeButtonRef = useRef(null);

    useEffect(() => {
        if (!report) return undefined;
        const previousFocus = document.activeElement;
        closeButtonRef.current?.focus();
        const handleKeyDown = (event) => {
            if (event.key === 'Escape') {
                event.preventDefault();
                onClose();
                return;
            }
            if (event.key !== 'Tab' || !dialogRef.current) return;
            const focusable = [...dialogRef.current.querySelectorAll('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])')];
            if (focusable.length === 0) return;
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        };
        document.addEventListener('keydown', handleKeyDown);
        return () => {
            document.removeEventListener('keydown', handleKeyDown);
            previousFocus?.focus?.();
        };
    }, [onClose, report]);

    if (!report) return null;
    const isLongform = report.type === 'article';

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
            <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby={titleId} className="bg-white rounded-xl shadow-2xl w-full max-w-3xl max-h-[85vh] flex flex-col overflow-hidden dark:bg-gray-900 dark:border dark:border-gray-800 animate-in fade-in zoom-in duration-200">
                <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between dark:border-gray-800">
                    <h3 id={titleId} className="text-lg font-bold text-gray-900 dark:text-gray-100">
                        {report.date} {isLongform ? '深度文章合集' : '精选快讯合集'}
                    </h3>
                    <button ref={closeButtonRef} type="button" aria-label="关闭日报" onClick={onClose} className="text-gray-400 hover:text-gray-600 transition-colors dark:hover:text-gray-200">
                        <span className="text-2xl leading-none">&times;</span>
                    </button>
                </div>
                <div className="p-6 overflow-y-auto">
                    <DailyReportContent report={report} />
                </div>
                <div className="px-6 py-3 border-t border-gray-100 bg-gray-50 text-right text-xs text-gray-500 dark:bg-gray-800/50 dark:border-gray-800 dark:text-gray-400">
                    发布于 {formatLocalDateTime(report.created_at)}
                </div>
            </div>
        </div>
    );
}
