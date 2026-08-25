import React, { useEffect, useState } from 'react';
import { ArrowUp } from '@phosphor-icons/react';

import { useNewsFeedData } from '../hooks/useNewsFeedData';
import NewsFeedHeader from '../components/newsfeed/NewsFeedHeader';
import NewsFeedTabs from '../components/newsfeed/NewsFeedTabs';
import ArticleList from '../components/newsfeed/ArticleList';
import NewsTimeline from '../components/newsfeed/NewsTimeline';
import DailyReportModal, { DailyReportItem } from '../components/newsfeed/DailyReportModal';
import { FEED_TAB } from '../contracts/content';

export default function NewsFeed() {
    const { state, actions } = useNewsFeedData();
    const {
        activeTab,
        loading,
        loadingMore,
        searchQuery,
        selectedReport,
        menuOpen,
        darkMode,
        hasMoreLongform,
        hasMoreBriefs,
        briefsLoadingMore,
        hasMoreCurrent,
        articleReports,
        briefReports,
        visibleLongformItems,
        visibleBriefItems,
        currentItems,
        error,
        refreshError,
        publicLinks,
        publications,
        selectedPublicationSlug,
    } = state;
    const {
        setActiveTab,
        setSearchQuery,
        setSelectedReport,
        setMenuOpen,
        setDarkMode,
        retryCurrent,
        loadMoreCurrent,
        loadMoreBriefs,
        setSelectedPublicationSlug,
    } = actions;
    const [showBackToTop, setShowBackToTop] = useState(false);

    useEffect(() => {
        const updateBackToTop = () => setShowBackToTop(window.scrollY > 480);
        updateBackToTop();
        window.addEventListener('scroll', updateBackToTop, { passive: true });
        return () => window.removeEventListener('scroll', updateBackToTop);
    }, []);

    return (
        <div className="bg-gray-100 min-h-screen dark:bg-gray-950 transition-colors duration-300">
            <NewsFeedHeader
                searchQuery={searchQuery}
                onSearchChange={setSearchQuery}
                menuOpen={menuOpen}
                onToggleMenu={() => setMenuOpen(!menuOpen)}
                darkMode={darkMode}
                onToggleDarkMode={() => setDarkMode(!darkMode)}
                links={publicLinks}
            />

            {publications.length > 0 && <nav aria-label="内容频道" className="max-w-7xl mx-auto px-4 pt-5 w-full">
                <div className="flex items-center gap-2 overflow-x-auto rounded-xl border border-gray-100 bg-white p-2 shadow-sm dark:border-gray-800 dark:bg-gray-900">
                    <button type="button" onClick={() => setSelectedPublicationSlug('')} className={`shrink-0 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${!selectedPublicationSlug ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800'}`}>全部默认频道</button>
                    {publications.map((publication) => <button key={publication.public_slug} type="button" onClick={() => setSelectedPublicationSlug(publication.public_slug)} className={`shrink-0 rounded-lg px-4 py-2 text-left text-sm transition-colors ${selectedPublicationSlug === publication.public_slug ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800'}`}><span className="font-medium">{publication.display_name}</span><span className={`ml-2 text-xs ${selectedPublicationSlug === publication.public_slug ? 'text-blue-100' : 'text-gray-400'}`}>{publication.content_type === 'news' ? '快讯' : '文章'}</span></button>)}
                </div>
            </nav>}

            <main className="max-w-7xl mx-auto px-4 py-6 w-full flex flex-col md:flex-row gap-6 items-stretch">
                <div className="w-full md:w-2/3 bg-white rounded-xl shadow-sm border border-gray-100 min-h-[80vh] flex flex-col dark:bg-gray-900 dark:border-gray-800 transition-colors duration-300">
                    <NewsFeedTabs activeTab={activeTab} onChange={setActiveTab} />

                    {refreshError && (
                        <div role="status" className="m-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
                            自动刷新失败，当前显示上次成功内容：{refreshError}
                        </div>
                    )}

                    {error && (
                        <div role="alert" className="m-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
                            <p>{error}</p>
                            <button type="button" onClick={() => void retryCurrent()} className="mt-2 rounded bg-red-700 px-3 py-1.5 font-medium text-white hover:bg-red-800">重试</button>
                        </div>
                    )}

                    <div
                        id={`feed-panel-${activeTab}`}
                        role="tabpanel"
                        aria-labelledby={`feed-tab-${activeTab}`}
                        aria-live="polite"
                        className="divide-y divide-gray-50 dark:divide-gray-800"
                    >
                        {loading && !loadingMore ? (
                            <div className="p-6 text-center text-gray-400">加载中...</div>
                        ) : activeTab === FEED_TAB.LONGFORM ? (
                            <ArticleList items={visibleLongformItems} loadingMore={loadingMore} hasMore={hasMoreLongform} searchQuery={searchQuery} />
                        ) : activeTab === FEED_TAB.ARTICLE_REPORTS ? (
                            articleReports.map((report, index) => (
                                <DailyReportItem key={report.id} report={report} index={index + 1} onClick={() => setSelectedReport(report)} />
                            ))
                        ) : activeTab === FEED_TAB.BRIEF_REPORTS ? (
                            briefReports.map((report, index) => (
                                <DailyReportItem key={report.id} report={report} index={index + 1} onClick={() => setSelectedReport(report)} />
                            ))
                        ) : activeTab === FEED_TAB.BRIEFS ? (
                            <NewsTimeline items={visibleBriefItems} loadingMore={loadingMore} hasMore={hasMoreBriefs} searchQuery={searchQuery} compact />
                        ) : null}
                    </div>

                    {!loading && !error && [FEED_TAB.ARTICLE_REPORTS, FEED_TAB.BRIEF_REPORTS].includes(activeTab) && currentItems.length > 0 && (
                        <div className="border-t border-gray-100 p-4 text-center text-sm text-gray-500 dark:border-gray-800 dark:text-gray-400">
                            {hasMoreCurrent ? (
                                <button
                                    type="button"
                                    disabled={loadingMore}
                                    onClick={() => void loadMoreCurrent()}
                                    className="rounded border border-gray-300 px-4 py-2 hover:bg-gray-50 disabled:cursor-wait disabled:opacity-60 dark:border-gray-700 dark:hover:bg-gray-800"
                                >
                                    {loadingMore ? '加载中...' : `继续加载（已显示 ${currentItems.length} 条）`}
                                </button>
                            ) : `已显示全部 ${currentItems.length} 条日报`}
                        </div>
                    )}

                    {!loading && !error && currentItems.length === 0 && (
                        <div className="p-6 text-center text-gray-400">暂无数据</div>
                    )}
                </div>

                <aside className="hidden md:flex w-full md:w-1/3 bg-white rounded-xl shadow-sm border border-gray-100 flex-col dark:bg-gray-900 dark:border-gray-800 transition-colors duration-300">
                    <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 sticky top-16 z-30 bg-white rounded-t-xl dark:bg-gray-900 dark:border-gray-800 transition-colors duration-300">
                        <div className="flex items-center gap-2">
                            <span className="w-1.5 h-1.5 rounded-full bg-red-500"></span>
                            <h2 className="font-bold text-gray-800 text-sm dark:text-gray-200">7x24h 快讯</h2>
                        </div>
                    </div>
                    <NewsTimeline items={visibleBriefItems} loadingMore={briefsLoadingMore} hasMore={hasMoreBriefs} searchQuery={searchQuery} />
                    <div className="border-t border-gray-100 p-4 text-center text-sm text-gray-500 dark:border-gray-800 dark:text-gray-400">
                        {hasMoreBriefs ? (
                            <button
                                type="button"
                                disabled={briefsLoadingMore}
                                onClick={() => void loadMoreBriefs()}
                                className="rounded border border-gray-300 px-4 py-2 hover:bg-gray-50 disabled:cursor-wait disabled:opacity-60 dark:border-gray-700 dark:hover:bg-gray-800"
                            >
                                {briefsLoadingMore ? '加载中...' : `继续加载快讯（已显示 ${visibleBriefItems.length} 条）`}
                            </button>
                        ) : `已显示全部 ${visibleBriefItems.length} 条快讯`}
                    </div>
                </aside>
            </main>

            <DailyReportModal report={selectedReport} onClose={() => setSelectedReport(null)} />

            {showBackToTop && <div className="fixed bottom-5 right-5 md:bottom-8 md:right-8 flex flex-col items-end gap-3 z-50">
                <button
                    type="button"
                    aria-label="回到页面顶部"
                    onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
                    className="w-12 h-12 bg-white text-gray-600 rounded-full shadow-lg border border-gray-100 flex items-center justify-center hover:bg-gray-50 hover:text-blue-600 transition-all active:scale-95 dark:bg-gray-800 dark:text-gray-300 dark:border-gray-700 dark:hover:bg-gray-700"
                    title="回到顶部"
                >
                    <ArrowUp size={20} />
                </button>
            </div>}
        </div>
    );
}
