import React from 'react';
import { Tag } from 'antd';

export function createReviewResultColumns(categoryColor) {
    return [
        { title: 'ID', dataIndex: 'id', width: 60 },
        {
            title: '标题',
            dataIndex: 'title',
            render: (text, record) => (
                <a href={record.source_url} target="_blank" rel="noopener noreferrer">{text}</a>
            ),
        },
        {
            title: '内容档案',
            dataIndex: 'profile_name',
            width: 120,
            render: (value) => <Tag>{value || '-'}</Tag>,
        },
        {
            title: '审核结果',
            width: 220,
            render: (_, record) => (
                <span>
                    <Tag color="blue">{record.review_score ?? 0}分</Tag>
                    {record.review_category && <Tag color={categoryColor}>{record.review_category}</Tag>}
                    <span style={{ color: '#666', marginRight: 4 }}>{record.review_reason || '-'}</span>
                </span>
            ),
        },
    ];
}
