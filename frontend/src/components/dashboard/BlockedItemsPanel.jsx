import React from 'react';
import PropTypes from 'prop-types';
import { Button, Space, Popconfirm, Divider } from 'antd';

import ContentDataTable from './ContentDataTable';
import { formatLocalDateTime } from '../../utils/time';

export default function BlockedItemsPanel({
    onAddToFeatured,
    blockedList,
    restoreItem,
    deleteBlockedItem,
    contentKind,
}) {
    const blockedColumns = [
        { title: 'ID', dataIndex: 'id', width: 60 },
        {
            title: '标题',
            dataIndex: 'title',
            render: (text, record) => <a href={record.source_url} target="_blank" rel="noopener noreferrer">{text}</a>,
        },
        {
            title: '拦截原因',
            dataIndex: 'block_reason',
            width: 150,
            render: (text) => text || '-',
        },
        { title: '来源', dataIndex: 'source_site', width: 100 },
        {
            title: '发布时间',
            dataIndex: 'published_at',
            width: 160,
            render: formatLocalDateTime,
        },
        {
            title: '操作',
            width: 220,
            render: (_, record) => (
                <Space>
                    <Button type="primary" size="small" onClick={() => onAddToFeatured && onAddToFeatured(record)}>
                        加入输出
                    </Button>
                    <Button type="link" size="small" onClick={() => restoreItem(record.id)}>
                        还原
                    </Button>
                    <Popconfirm title="确定删除?" onConfirm={() => deleteBlockedItem(record.id)}>
                        <Button type="link" danger size="small">删除</Button>
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    return (
        <>
            <Divider />
            <div style={{ marginTop: 20 }}>
                <div style={{ marginBottom: 16 }}>
                    <h3>3. 已拦截内容</h3>
                </div>
                <ContentDataTable
                    listState={blockedList}
                    columns={blockedColumns}
                    contentKind={contentKind}
                    showSourceFilter={false}
                    size="small"
                />
            </div>
        </>
    );
}

BlockedItemsPanel.propTypes = {
    onAddToFeatured: PropTypes.func,
    blockedList: PropTypes.object.isRequired,
    restoreItem: PropTypes.func.isRequired,
    deleteBlockedItem: PropTypes.func.isRequired,
    contentKind: PropTypes.string,
};
