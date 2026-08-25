import React from 'react';
import PropTypes from 'prop-types';
import { Button, Table, Space, Tag } from 'antd';

export default function ExportItemsTable({
    visibleItems,
    loading,
    selectedIds,
    setSelectedIds,
    onRemoveFeatured,
}) {
    const columns = [
        {
            title: '评分',
            dataIndex: 'review_score',
            width: 140,
            render: (score, record) => (
                <Space>
                    {record.isFeatured && <Tag color="gold">手动</Tag>}
                    <Tag color={(score ?? 0) >= 8 ? 'green' : (score ?? 0) >= 7 ? 'blue' : 'default'}>{score ?? 0}分</Tag>
                </Space>
            ),
        },
        {
            title: '标题',
            dataIndex: 'title',
            width: 300,
            ellipsis: true,
            render: (text, record) => <a href={record.source_url} target="_blank" rel="noopener noreferrer">{text}</a>,
        },
        {
            title: '来源',
            dataIndex: 'source_site',
            width: 100,
            render: (text) => <Tag>{text}</Tag>,
        },
        {
            title: '审核理由',
            dataIndex: 'review_reason',
            width: 220,
            ellipsis: true,
            render: (text) => <span style={{ fontSize: 12, color: '#666' }}>{text || '-'}</span>,
        },
        {
            title: '操作',
            width: 90,
            fixed: 'right',
            render: (_, record) => record.isFeatured
                ? <Button type="link" danger onClick={() => onRemoveFeatured(record.outputKey)}>移出</Button>
                : '-',
        },
    ];

    return (
        <Table
            className="admin-data-table export-items-table"
            dataSource={visibleItems}
            rowKey="outputKey"
            loading={loading}
            pagination={false}
            rowSelection={{
                selectedRowKeys: selectedIds,
                onChange: (keys) => setSelectedIds(keys),
            }}
            expandable={{
                expandedRowRender: (record) => (
                    <div style={{ padding: '12px 24px', backgroundColor: '#fafafa' }}>
                        <p style={{ margin: 0, whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>
                            {record.content || record.review_summary || '暂无内容'}
                        </p>
                    </div>
                ),
                rowExpandable: (record) => !!record.content || !!record.review_summary,
            }}
            columns={columns}
            scroll={{ x: 900 }}
        />
    );
}

ExportItemsTable.propTypes = {
    visibleItems: PropTypes.arrayOf(PropTypes.object).isRequired,
    loading: PropTypes.bool.isRequired,
    selectedIds: PropTypes.arrayOf(PropTypes.string).isRequired,
    setSelectedIds: PropTypes.func.isRequired,
    onRemoveFeatured: PropTypes.func.isRequired,
};
