import React from 'react';
import PropTypes from 'prop-types';
import { Button, Pagination, Tag } from 'antd';

import { createPaginationConfig } from '../../hooks/usePagination';

function SummaryBanner({ pagination, summary }) {
    return (
        <div
            style={{
                background: '#e6f7ff',
                border: '1px solid #91d5ff',
                borderRadius: '4px',
                padding: '12px 16px',
                marginBottom: '16px',
            }}
        >
            <div style={{ fontSize: '14px', color: '#1890ff', marginBottom: '4px' }}>
                ℹ️ 当前筛选下共有 {pagination.total} 组源内容
            </div>
            <div style={{ fontSize: '13px', color: '#666', display: 'flex', gap: '24px' }}>
                <span>▶ 有重复: {summary.groups} 组</span>
                <span>✅ 独立: {summary.independent} 组</span>
            </div>
        </div>
    );
}

SummaryBanner.propTypes = {
    pagination: PropTypes.shape({ total: PropTypes.number.isRequired }).isRequired,
    summary: PropTypes.shape({
        groups: PropTypes.number.isRequired,
        independent: PropTypes.number.isRequired,
    }).isRequired,
};

function DuplicateGroupCard({ group, expandedGroups, toggleGroup, deleteNews }) {
    const groupKey = group.master.id;
    const isExpanded = expandedGroups.has(groupKey);
    const isGroup = group.type === 'group';

    return (
        <div key={groupKey} style={{ marginBottom: '16px', border: '1px solid #f0f0f0', borderRadius: '8px', overflow: 'hidden' }}>
            <div
                style={{
                    background: isGroup ? '#fafafa' : '#f0f9ff',
                    padding: '12px 16px',
                    borderBottom: isGroup && isExpanded ? '2px solid #1890ff' : 'none',
                    cursor: isGroup ? 'pointer' : 'default',
                    transition: 'background 0.2s',
                }}
                onClick={isGroup ? () => toggleGroup(groupKey) : undefined}
                onMouseEnter={isGroup ? (event) => { event.currentTarget.style.background = '#f0f0f0'; } : undefined}
                onMouseLeave={isGroup ? (event) => { event.currentTarget.style.background = '#fafafa'; } : undefined}
            >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ flex: 1, display: 'flex', alignItems: 'center' }}>
                        {isGroup ? (
                            <>
                                <span style={{ marginRight: 8, fontSize: '14px', color: '#999' }}>
                                    {isExpanded ? '▼' : '▶'}
                                </span>
                                <Tag color="blue" style={{ marginRight: 8 }}>原始 ID:{group.master.id}</Tag>
                                <Tag color="orange">{group.duplicates.length}条重复</Tag>
                            </>
                        ) : (
                            <>
                                <span style={{ marginRight: 8, fontSize: '14px', color: '#52c41a' }}>✅</span>
                                <Tag color="green" style={{ marginRight: 8 }}>独立 ID:{group.master.id}</Tag>
                            </>
                        )}
                        <a
                            href={group.master.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ fontWeight: 'bold', fontSize: '14px', marginLeft: '8px' }}
                            onClick={(event) => event.stopPropagation()}
                        >
                            {group.master.title}
                        </a>
                    </div>
                    <div>
                        <Tag>{group.master.source_site}</Tag>
                        <span style={{ marginLeft: 8, color: '#999', fontSize: '12px' }}>
                            {new Date(group.master.published_at).toLocaleString()}
                        </span>
                    </div>
                </div>
            </div>

            {isGroup && isExpanded && group.duplicates.map((dup, dupIndex) => (
                <div key={dupIndex} style={{ padding: '12px 16px 12px 40px', borderBottom: dupIndex < group.duplicates.length - 1 ? '1px solid #f0f0f0' : 'none', background: '#fff' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ flex: 1 }}>
                            <Tag color="volcano" style={{ marginRight: 8 }}>重复 ID:{dup.id}</Tag>
                            <a href={dup.source_url} target="_blank" rel="noopener noreferrer" style={{ fontSize: '13px' }}>
                                {dup.title}
                            </a>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                            <Tag>{dup.source_site}</Tag>
                            <span style={{ color: '#999', fontSize: '12px', minWidth: '140px' }}>
                                {new Date(dup.published_at).toLocaleString()}
                            </span>
                            <Button type="link" danger size="small" onClick={() => deleteNews(dup.id)}>
                                删除
                            </Button>
                        </div>
                    </div>
                </div>
            ))}
        </div>
    );
}

DuplicateGroupCard.propTypes = {
    group: PropTypes.shape({
        type: PropTypes.string.isRequired,
        master: PropTypes.object.isRequired,
        duplicates: PropTypes.arrayOf(PropTypes.object).isRequired,
    }).isRequired,
    expandedGroups: PropTypes.instanceOf(Set).isRequired,
    toggleGroup: PropTypes.func.isRequired,
    deleteNews: PropTypes.func.isRequired,
};

export default function DuplicateGroupsList({
    loading,
    groups,
    pagination,
    summary,
    expandedGroups,
    toggleGroup,
    deleteNews,
    onPageChange,
}) {
    if (loading) {
        return <div style={{ textAlign: 'center', padding: '50px' }}>加载中...</div>;
    }

    if (groups.length === 0) {
        return (
            <div style={{ textAlign: 'center', padding: '50px', color: '#999' }}>
                ✅ 没有源内容
            </div>
        );
    }

    return (
        <>
            <SummaryBanner pagination={pagination} summary={summary} />
            {groups.map((group) => (
                <DuplicateGroupCard
                    key={group.master.id}
                    group={group}
                    expandedGroups={expandedGroups}
                    toggleGroup={toggleGroup}
                    deleteNews={deleteNews}
                />
            ))}
            <div style={{ marginTop: '20px', display: 'flex', justifyContent: 'flex-end' }}>
                <Pagination
                    {...createPaginationConfig(pagination, onPageChange, 20)}
                />
            </div>
        </>
    );
}

DuplicateGroupsList.propTypes = {
    loading: PropTypes.bool.isRequired,
    groups: PropTypes.arrayOf(PropTypes.object).isRequired,
    pagination: PropTypes.object.isRequired,
    summary: PropTypes.shape({
        groups: PropTypes.number.isRequired,
        independent: PropTypes.number.isRequired,
    }).isRequired,
    expandedGroups: PropTypes.instanceOf(Set).isRequired,
    toggleGroup: PropTypes.func.isRequired,
    deleteNews: PropTypes.func.isRequired,
    onPageChange: PropTypes.func.isRequired,
};
