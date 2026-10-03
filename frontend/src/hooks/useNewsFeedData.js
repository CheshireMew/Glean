import { useEffect, useMemo, useState } from 'react';

import { CONTENT_KIND, FEED_TAB, PUBLIC_STREAM } from '../contracts/content';
import { useNewsFeedUiState } from './newsfeed/useNewsFeedUiState';
import { usePublicReportFeed } from './newsfeed/usePublicReportFeed';
import { usePublicSearchResults } from './newsfeed/usePublicSearchResults';
import { usePublicSiteConfig } from './newsfeed/usePublicSiteConfig';
import { usePublicStream } from './newsfeed/usePublicStream';
import { useThemePreference } from './newsfeed/useThemePreference';

const REFRESH_INTERVAL_MS = 60000;

export function useNewsFeedData({ active = true, articlesOnly = false } = {}) {
    const ui = useNewsFeedUiState();
    const activeTab = articlesOnly ? FEED_TAB.LONGFORM : ui.activeTab;
    const theme = useThemePreference();
    const publicSiteConfig = usePublicSiteConfig();
    const [selectedPublicationSlug, setSelectedPublicationSlug] = useState('');
    const selectedPublication = (publicSiteConfig.publications || []).find(
        (item) => item.public_slug === selectedPublicationSlug,
    ) || null;
    const channelByKind = useMemo(() => ({
        [CONTENT_KIND.ARTICLE]: selectedPublication?.content_type === CONTENT_KIND.ARTICLE ? selectedPublication.public_slug : null,
        [CONTENT_KIND.NEWS]: selectedPublication?.content_type === CONTENT_KIND.NEWS ? selectedPublication.public_slug : null,
    }), [selectedPublication]);
    const longform = usePublicStream(PUBLIC_STREAM.LONGFORM, channelByKind[CONTENT_KIND.ARTICLE]);
    const briefs = usePublicStream(PUBLIC_STREAM.BRIEFS, channelByKind[CONTENT_KIND.NEWS]);
    const reportSearch = active ? ui.debouncedSearchQuery : '';
    const articleReports = usePublicReportFeed(CONTENT_KIND.ARTICLE, reportSearch, channelByKind[CONTENT_KIND.ARTICLE]);
    const briefReports = usePublicReportFeed(CONTENT_KIND.NEWS, reportSearch, channelByKind[CONTENT_KIND.NEWS]);
    const searchChannels = useMemo(() => ({
        article: channelByKind[CONTENT_KIND.ARTICLE],
        news: channelByKind[CONTENT_KIND.NEWS],
    }), [channelByKind]);
    const search = usePublicSearchResults(reportSearch, searchChannels);

    const descriptors = useMemo(() => {
        const longformState = search.enabled
            ? {
                ...search.state.article,
                items: search.state.articleItems,
                loading: search.state.loading,
                error: search.state.error,
                refreshError: null,
            }
            : longform.state;
        const briefsState = search.enabled
            ? {
                ...search.state.brief,
                items: search.state.briefItems,
                loading: search.state.loading,
                error: search.state.error,
                refreshError: null,
            }
            : briefs.state;
        return {
            [FEED_TAB.LONGFORM]: {
                state: longformState,
                ensureLoaded: longform.ensureLoaded,
                retry: search.enabled ? search.retry : longform.retry,
                loadMore: search.enabled
                    ? () => search.loadMore(CONTENT_KIND.ARTICLE)
                    : longform.loadMore,
            },
            [FEED_TAB.BRIEFS]: {
                state: briefsState,
                ensureLoaded: briefs.ensureLoaded,
                retry: search.enabled ? search.retry : briefs.retry,
                loadMore: search.enabled
                    ? () => search.loadMore(CONTENT_KIND.NEWS)
                    : briefs.loadMore,
            },
            [FEED_TAB.ARTICLE_REPORTS]: {
                state: articleReports.state,
                ensureLoaded: articleReports.ensureLoaded,
                retry: articleReports.retry,
                loadMore: articleReports.loadMore,
            },
            [FEED_TAB.BRIEF_REPORTS]: {
                state: briefReports.state,
                ensureLoaded: briefReports.ensureLoaded,
                retry: briefReports.retry,
                loadMore: briefReports.loadMore,
            },
        };
    }, [articleReports, briefReports, briefs, longform, search]);

    const activeDescriptor = descriptors[activeTab] || descriptors[FEED_TAB.BRIEFS];
    const longformDescriptor = descriptors[FEED_TAB.LONGFORM];
    const briefsDescriptor = descriptors[FEED_TAB.BRIEFS];
    const ensureActiveLoaded = activeDescriptor.ensureLoaded;
    const ensureBriefsLoaded = briefs.ensureLoaded;

    useEffect(() => {
        if (!active) return;
        const timer = window.setTimeout(() => {
            if (!articlesOnly) void ensureBriefsLoaded();
            if (activeTab !== FEED_TAB.BRIEFS) {
                void ensureActiveLoaded();
            }
        }, 0);
        return () => window.clearTimeout(timer);
    }, [active, articlesOnly, ensureActiveLoaded, ensureBriefsLoaded, activeTab]);

    useEffect(() => {
        if (!active) return;
        const handleScroll = () => {
            const current = activeDescriptor.state;
            if (current.loaded === false || !current.hasMore || current.loadingMore) return;
            const nearBottom = window.innerHeight + window.scrollY
                >= document.documentElement.scrollHeight - 500;
            if (nearBottom) void activeDescriptor.loadMore();
        };
        window.addEventListener('scroll', handleScroll);
        return () => window.removeEventListener('scroll', handleScroll);
    }, [active, activeDescriptor]);

    useEffect(() => {
        if (!active) return;
        const refreshLoaded = () => {
            if (document.visibilityState !== 'visible') return;
            if (search.enabled) return;
            if (!articlesOnly) void briefs.refresh();
            if (longform.state.loaded) void longform.refresh();
            if (!articlesOnly && articleReports.state.loaded) void articleReports.refresh();
            if (!articlesOnly && briefReports.state.loaded) void briefReports.refresh();
        };
        const interval = window.setInterval(refreshLoaded, REFRESH_INTERVAL_MS);
        document.addEventListener('visibilitychange', refreshLoaded);
        return () => {
            window.clearInterval(interval);
            document.removeEventListener('visibilitychange', refreshLoaded);
        };
    }, [active, articlesOnly, articleReports, briefReports, briefs, longform, search.enabled]);

    return {
        state: {
            activeTab,
            loading: activeDescriptor.state.loading,
            loadingMore: activeDescriptor.state.loadingMore,
            searchQuery: ui.searchQuery,
            debouncedSearchQuery: ui.debouncedSearchQuery,
            selectedReport: ui.selectedReport,
            menuOpen: ui.menuOpen,
            darkMode: theme.darkMode,
            hasMoreLongform: longformDescriptor.state.hasMore,
            hasMoreBriefs: briefsDescriptor.state.hasMore,
            briefsLoadingMore: briefsDescriptor.state.loadingMore,
            hasMoreCurrent: activeDescriptor.state.hasMore,
            articleReports: articleReports.state.items,
            briefReports: briefReports.state.items,
            visibleLongformItems: longformDescriptor.state.items,
            visibleBriefItems: briefsDescriptor.state.items,
            currentItems: activeDescriptor.state.items,
            error: activeDescriptor.state.error,
            refreshError: activeDescriptor.state.refreshError,
            publicLinks: publicSiteConfig.links,
            publications: publicSiteConfig.publications || [],
            selectedPublicationSlug,
        },
        actions: {
            setActiveTab: ui.setActiveTab,
            setSearchQuery: ui.setSearchQuery,
            setSelectedReport: ui.setSelectedReport,
            setMenuOpen: ui.setMenuOpen,
            setDarkMode: theme.setDarkMode,
            retryCurrent: activeDescriptor.retry,
            loadMoreCurrent: activeDescriptor.loadMore,
            loadMoreBriefs: briefsDescriptor.loadMore,
            setSelectedPublicationSlug,
        },
    };
}
