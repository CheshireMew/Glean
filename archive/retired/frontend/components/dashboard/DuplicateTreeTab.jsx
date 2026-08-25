import React from 'react';
import PropTypes from 'prop-types';

import { useDuplicateGroups } from '../../hooks/dashboard/useDuplicateGroups';
import { useSimilarityCheck } from '../../hooks/dashboard/useSimilarityCheck';
import NewsToolbar from './NewsToolbar';
import DuplicateGroupsList from './DuplicateGroupsList';
import DuplicateSimilarityCard from './DuplicateSimilarityCard';

/**
 * 重复对照Tab组件
 * 显示所有原始新闻：有重复的（可展开）+ 独立的（无重复）
 */
const DuplicateTreeTab = ({ spiders, contentKind }) => {
    const {
        groups,
        loading,
        pagination,
        summary,
        filterSource,
        filterKeyword,
        expandedGroups,
        setFilterSource,
        setFilterKeyword,
        toggleGroup,
        fetchGroups,
        deleteGroupItem,
    } = useDuplicateGroups(contentKind);
    const {
        newsId1,
        newsId2,
        similarityResult,
        checkingLoading,
        setNewsId1,
        setNewsId2,
        checkSimilarity,
    } = useSimilarityCheck();

    return (
        <>
            <NewsToolbar
                onSearch={(val) => {
                    setFilterKeyword(val);
                    fetchGroups(1, pagination.pageSize, filterSource, val);
                }}
                spiders={spiders}
                selectedSource={filterSource}
                onSourceChange={(val) => {
                    const nextSource = val || undefined;
                    setFilterSource(nextSource);
                    fetchGroups(1, pagination.pageSize, nextSource, filterKeyword);
                }}
                contentKind={contentKind}
                onRefresh={() => fetchGroups(pagination.current, pagination.pageSize, filterSource, filterKeyword)}
                loading={loading}
            />

            <div style={{ padding: '16px' }}>
                <DuplicateSimilarityCard
                    contentKind={contentKind}
                    newsId1={newsId1}
                    newsId2={newsId2}
                    similarityResult={similarityResult}
                    checkingLoading={checkingLoading}
                    setNewsId1={setNewsId1}
                    setNewsId2={setNewsId2}
                    checkSimilarity={checkSimilarity}
                />
                <DuplicateGroupsList
                    loading={loading}
                    groups={groups}
                    pagination={pagination}
                    summary={summary}
                    expandedGroups={expandedGroups}
                    toggleGroup={toggleGroup}
                    deleteNews={deleteGroupItem}
                    onPageChange={(page, pageSize) => fetchGroups(page, pageSize, filterSource, filterKeyword)}
                />
            </div>
        </>
    );
};

DuplicateTreeTab.propTypes = {
    spiders: PropTypes.arrayOf(PropTypes.shape({
        name: PropTypes.string,
        url: PropTypes.string,
    })),
    contentKind: PropTypes.string,
};

export default DuplicateTreeTab;
