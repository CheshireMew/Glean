import React from 'react';

/**
 * 新闻详情展开组件
 * 用于在表格行展开时显示新闻的详细内容和元数据
 */
const NewsExpandedView = ({ record }) => {
    if (!record) return null;
    let citations = record.enrichment_citations;
    if (typeof citations === 'string') {
        try { citations = JSON.parse(citations); } catch { citations = []; }
    }

    return (
        <div style={{ padding: 16, background: '#fafafa' }}>
            <p><strong>原文链接：</strong> <a href={record.source_url} target="_blank" rel="noopener noreferrer">{record.source_url}</a></p>
            {record.author && <p><strong>作者：</strong> {record.author}</p>}
            {record.content_type && <p><strong>内容类型：</strong> {record.content_type === 'article' ? '文章' : '快讯'}</p>}
            {record.event_id && <p><strong>事件编号：</strong> {record.event_id}</p>}
            {record.site_importance_flag && (
                <p><strong>站点标记：</strong> {record.site_importance_flag}</p>
            )}
            {record.profile_name && <p><strong>内容档案:</strong> {record.profile_name}</p>}
            {record.review_score !== undefined && record.review_score !== null && <p><strong>审核评分：</strong> {record.review_score} / 10</p>}
            {record.review_category && <p><strong>审核栏目：</strong> {record.review_category}</p>}
            {record.review_reason && <p><strong>审核依据：</strong> {record.review_reason}</p>}
            {record.review_tags && <p><strong>标签：</strong> {(typeof record.review_tags === 'string' ? (() => { try { return JSON.parse(record.review_tags).join('、'); } catch { return record.review_tags; } })() : record.review_tags.join('、'))}</p>}
            {record.delivery_status && <p><strong>投递状态：</strong> {record.delivery_status}</p>}
            {record.enrichment_status && <p><strong>补充状态：</strong> {record.enrichment_status}</p>}
            {record.editorial_updated_at && <p><strong>最近人工修订：</strong> {record.editorial_updated_at}（{record.editorial_updated_by || '未知'}）</p>}
            {record.source_count > 1 && <p><strong>事件来源:</strong> {record.source_count} 个来源</p>}
            {record.enriched_summary && <p><strong>综合摘要:</strong> {record.enriched_summary}</p>}
            {record.enriched_impact && <p><strong>为什么重要:</strong> {record.enriched_impact}</p>}
            {record.enriched_background && <p><strong>背景:</strong> {record.enriched_background}</p>}
            {citations?.length > 0 && (
                <div>
                    <strong>引用来源:</strong>
                    <ul>{citations.map((citation) => <li key={citation.news_id}><a href={citation.source_url} target="_blank" rel="noopener noreferrer">{citation.source_site}：{citation.title}</a></li>)}</ul>
                </div>
            )}
            <div style={{ whiteSpace: 'pre-wrap', maxHeight: 400, overflowY: 'auto', marginTop: 8 }}>
                {record.content || <span style={{ color: '#999' }}>暂无正文内容</span>}
            </div>
        </div>
    );
};

export default NewsExpandedView;
