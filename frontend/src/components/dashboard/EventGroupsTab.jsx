import React, { useEffect, useRef } from 'react';
import PropTypes from 'prop-types';

import { useEventGroups } from '../../hooks/dashboard/useEventGroups';
import { useSimilarityCheck } from '../../hooks/dashboard/useSimilarityCheck';
import NewsToolbar from './NewsToolbar';
import EventGroupsList from './EventGroupsList';
import EventSimilarityCard from './EventSimilarityCard';

/**
 * 事件聚合组件：每个事件保留全部来源和一个规范来源。
 */
const EventGroupsTab = ({ spiders, contentKind }) => {
    const {
        groups,
        loading,
        loaded,
        error,
        stale,
        pagination,
        summary,
        filterSource,
        filterKeyword,
        expandedGroups,
        setFilterSource,
        setFilterKeyword,
        toggleGroup,
        fetchGroups,
        retry,
        deleteGroupItem,
    } = useEventGroups(contentKind);
    const {
        newsId1,
        newsId2,
        similarityResult,
        checkingLoading,
        setNewsId1,
        setNewsId2,
        checkSimilarity,
    } = useSimilarityCheck();
    const searchTimerRef = useRef(null);
    const queryRef = useRef({ source: filterSource, keyword: filterKeyword });

    useEffect(() => {
        queryRef.current = { source: filterSource, keyword: filterKeyword };
    }, [filterKeyword, filterSource]);

    useEffect(() => () => {
        if (searchTimerRef.current) window.clearTimeout(searchTimerRef.current);
    }, [contentKind]);

    const handleSearchChange = (keyword) => {
        queryRef.current = { ...queryRef.current, keyword };
        setFilterKeyword(keyword);
        if (searchTimerRef.current) window.clearTimeout(searchTimerRef.current);
        searchTimerRef.current = window.setTimeout(() => {
            const query = queryRef.current;
            fetchGroups(1, pagination.pageSize, query.source, query.keyword);
        }, 500);
    };

    const handleSourceChange = (source) => {
        const nextSource = source || undefined;
        if (searchTimerRef.current) window.clearTimeout(searchTimerRef.current);
        queryRef.current = { ...queryRef.current, source: nextSource };
        setFilterSource(nextSource);
        fetchGroups(1, pagination.pageSize, nextSource, queryRef.current.keyword);
    };

    const handleRefresh = () => {
        if (searchTimerRef.current) window.clearTimeout(searchTimerRef.current);
        const query = queryRef.current;
        fetchGroups(pagination.current, pagination.pageSize, query.source, query.keyword);
    };

    return (
        <>
            <NewsToolbar
                searchValue={filterKeyword}
                onSearchChange={handleSearchChange}
                spiders={spiders}
                selectedSource={filterSource}
                onSourceChange={handleSourceChange}
                contentKind={contentKind}
                onRefresh={handleRefresh}
                loading={loading}
            />

            <div style={{ padding: '16px' }}>
                <EventSimilarityCard
                    contentKind={contentKind}
                    newsId1={newsId1}
                    newsId2={newsId2}
                    similarityResult={similarityResult}
                    checkingLoading={checkingLoading}
                    setNewsId1={setNewsId1}
                    setNewsId2={setNewsId2}
                    checkSimilarity={checkSimilarity}
                />
                <EventGroupsList
                    loading={loading}
                    loaded={loaded}
                    error={error}
                    stale={stale}
                    groups={groups}
                    pagination={pagination}
                    summary={summary}
                    expandedGroups={expandedGroups}
                    toggleGroup={toggleGroup}
                    deleteNews={deleteGroupItem}
                    onPageChange={(page, pageSize) => fetchGroups(page, pageSize, filterSource, filterKeyword)}
                    onRetry={retry}
                />
            </div>
        </>
    );
};

EventGroupsTab.propTypes = {
    spiders: PropTypes.arrayOf(PropTypes.shape({
        name: PropTypes.string,
        url: PropTypes.string,
    })),
    contentKind: PropTypes.string,
};

export default EventGroupsTab;
