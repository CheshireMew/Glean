import React, { useState } from 'react';
import PropTypes from 'prop-types';
import { Alert, Button, Pagination, Tag } from 'antd';

import { createPaginationConfig } from '../../hooks/usePagination';
import { formatLocalDateTime } from '../../utils/time';
import EventEvidenceDrawer from './EventEvidenceDrawer';

function SummaryBanner({ pagination, summary }) {
    return (
        <div
            className="event-summary-banner"
            style={{
                background: '#e6f7ff',
                border: '1px solid #91d5ff',
                borderRadius: '4px',
                padding: '12px 16px',
                marginBottom: '16px',
            }}
        >
            <div style={{ fontSize: '14px', color: '#1890ff', marginBottom: '4px' }}>
                当前筛选下共有 {pagination.total} 个事件
            </div>
            <div className="event-summary-counts" style={{ fontSize: '13px', color: '#666', display: 'flex', gap: '24px' }}>
                <span>多来源事件：{summary.multi_source}</span>
                <span>单来源事件：{summary.single_source}</span>
            </div>
        </div>
    );
}

SummaryBanner.propTypes = {
    pagination: PropTypes.shape({ total: PropTypes.number.isRequired }).isRequired,
    summary: PropTypes.shape({
        multi_source: PropTypes.number.isRequired,
        single_source: PropTypes.number.isRequired,
    }).isRequired,
};

function EventGroupCard({ group, expandedGroups, toggleGroup, deleteNews, openEvidence }) {
    const groupKey = group.event.id;
    const isExpanded = expandedGroups.has(groupKey);
    const isMultiSource = group.sources.length > 1;

    return (
        <div key={groupKey} className="event-group-card" style={{ marginBottom: '16px', border: '1px solid #f0f0f0', borderRadius: '8px', overflow: 'hidden' }}>
            <div
                className="event-group-header"
                style={{
                    background: isMultiSource ? '#fafafa' : '#f0f9ff',
                    padding: '12px 16px',
                    borderBottom: isMultiSource && isExpanded ? '2px solid #1890ff' : 'none',
                    transition: 'background 0.2s',
                }}
            >
                <div className="event-group-header-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div className="event-group-main" style={{ flex: 1, display: 'flex', alignItems: 'center' }}>
                        {isMultiSource ? (
                            <>
                                <button
                                    type="button"
                                    className="event-group-toggle"
                                    aria-expanded={isExpanded}
                                    aria-controls={`event-sources-${groupKey}`}
                                    aria-label={`${isExpanded ? '收起' : '展开'}事件 ${group.event.id} 的来源`}
                                    onClick={() => toggleGroup(groupKey)}
                                >
                                    {isExpanded ? '▼' : '▶'}
                                </button>
                                <Tag color="blue" style={{ marginRight: 8 }}>事件 {group.event.id}</Tag>
                                <Tag color="orange">{group.sources.length} 个来源</Tag>
                            </>
                        ) : (
                            <>
                                <span style={{ marginRight: 8, fontSize: '14px', color: '#52c41a' }}>✅</span>
                                <Tag color="green" style={{ marginRight: 8 }}>事件 {group.event.id}</Tag>
                            </>
                        )}
                        <a
                            className="event-group-title"
                            href={group.primary.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ fontWeight: 'bold', fontSize: '14px', marginLeft: '8px' }}
                        >
                            {group.event.title}
                        </a>
                    </div>
                    <div className="event-group-meta">
                        <Button size="small" onClick={() => openEvidence(group.event.id)}>证据与进展</Button>
                        <Tag>{group.primary.source_site}</Tag>
                        <span style={{ marginLeft: 8, color: '#999', fontSize: '12px' }}>
                            {formatLocalDateTime(group.event.published_at)}
                        </span>
                    </div>
                </div>
            </div>

            {isMultiSource && isExpanded && group.alternatives.map((source, sourceIndex) => (
                <div id={sourceIndex === 0 ? `event-sources-${groupKey}` : undefined} key={source.id} className="event-source-row" style={{ padding: '12px 16px 12px 40px', borderBottom: sourceIndex < group.alternatives.length - 1 ? '1px solid #f0f0f0' : 'none', background: '#fff' }}>
                    <div className="event-source-layout" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div className="event-source-title" style={{ flex: 1 }}>
                            <Tag color="geekblue" style={{ marginRight: 8 }}>来源 {source.id}</Tag>
                            <a href={source.source_url} target="_blank" rel="noopener noreferrer" style={{ fontSize: '13px' }}>
                                {source.title}
                            </a>
                        </div>
                        <div className="event-source-meta" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                            <Tag>{source.source_site}</Tag>
                            <Tag>{(source.similarity * 100).toFixed(0)}% 匹配</Tag>
                            <span style={{ color: '#999', fontSize: '12px', minWidth: '140px' }}>
                                {formatLocalDateTime(source.published_at)}
                            </span>
                            <Button type="link" danger size="small" onClick={() => deleteNews(source.id)}>
                                移除来源
                            </Button>
                        </div>
                    </div>
                </div>
            ))}
        </div>
    );
}

EventGroupCard.propTypes = {
    group: PropTypes.shape({
        type: PropTypes.string.isRequired,
        event: PropTypes.object.isRequired,
        primary: PropTypes.object.isRequired,
        sources: PropTypes.arrayOf(PropTypes.object).isRequired,
        alternatives: PropTypes.arrayOf(PropTypes.object).isRequired,
    }).isRequired,
    expandedGroups: PropTypes.instanceOf(Set).isRequired,
    toggleGroup: PropTypes.func.isRequired,
    deleteNews: PropTypes.func.isRequired,
    openEvidence: PropTypes.func.isRequired,
};

export default function EventGroupsList({
    loading,
    loaded,
    error,
    stale,
    groups,
    pagination,
    summary,
    expandedGroups,
    toggleGroup,
    deleteNews,
    onPageChange,
    onRetry,
}) {
    const [evidenceEventId, setEvidenceEventId] = useState(null);
    if (loading && !loaded) {
        return <div style={{ textAlign: 'center', padding: '50px' }}>加载中...</div>;
    }

    if (error && !loaded) {
        return (
            <Alert
                type="error"
                showIcon
                message="事件加载失败"
                description={error}
                action={<Button size="small" onClick={onRetry}>重试</Button>}
            />
        );
    }

    if (groups.length === 0 && loaded && !error) {
        return (
            <div style={{ textAlign: 'center', padding: '50px', color: '#999' }}>
                暂无已聚合事件
            </div>
        );
    }

    return (
        <>
            {error && stale && (
                <Alert
                    type="warning"
                    showIcon
                    message="刷新失败，当前显示上次成功的事件"
                    description={error}
                    action={<Button size="small" onClick={onRetry}>重试</Button>}
                    style={{ marginBottom: 16 }}
                />
            )}
            <SummaryBanner pagination={pagination} summary={summary} />
            {groups.map((group) => (
                <EventGroupCard
                    key={group.event.id}
                    group={group}
                    expandedGroups={expandedGroups}
                    toggleGroup={toggleGroup}
                    deleteNews={deleteNews}
                    openEvidence={setEvidenceEventId}
                />
            ))}
            <div style={{ marginTop: '20px', display: 'flex', justifyContent: 'flex-end' }}>
                <Pagination
                    {...createPaginationConfig(pagination, onPageChange, 20)}
                />
            </div>
            <EventEvidenceDrawer eventId={evidenceEventId} open={evidenceEventId !== null} onClose={() => setEvidenceEventId(null)} onSaved={onRetry} />
        </>
    );
}

EventGroupsList.propTypes = {
    loading: PropTypes.bool.isRequired,
    loaded: PropTypes.bool.isRequired,
    error: PropTypes.string,
    stale: PropTypes.bool.isRequired,
    groups: PropTypes.arrayOf(PropTypes.object).isRequired,
    pagination: PropTypes.object.isRequired,
    summary: PropTypes.shape({
        multi_source: PropTypes.number.isRequired,
        single_source: PropTypes.number.isRequired,
    }).isRequired,
    expandedGroups: PropTypes.instanceOf(Set).isRequired,
    toggleGroup: PropTypes.func.isRequired,
    deleteNews: PropTypes.func.isRequired,
    onPageChange: PropTypes.func.isRequired,
    onRetry: PropTypes.func.isRequired,
};
