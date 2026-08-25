import React from 'react';
import PropTypes from 'prop-types';
import { Card, Button, Space, Popconfirm } from 'antd';

import { useDiscardedContentActions } from '../../hooks/dashboard/useDiscardedContentActions';
import { useDiscardedContentList } from '../../hooks/dashboard/useDiscardedContentList';
import ContentDataTable from './ContentDataTable';
import { formatLocalDateTime } from '../../utils/time';
import { createReviewResultColumns } from './reviewResultColumns';

const DiscardedContentTab = ({ onAddToFeatured, contentKind }) => {
    const listState = useDiscardedContentList(contentKind);
    const {
        requeueItem,
        deleteItem,
        requeueAll,
        clearAll,
    } = useDiscardedContentActions(contentKind);

    const columns = [
        ...createReviewResultColumns('orange'),
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
                    <Button type="link" onClick={() => requeueItem(record.id)}>还原</Button>
                    <Popconfirm title="确定删除这条内容？" description="此操作将彻底删除对应内容" onConfirm={() => deleteItem(record.id)}>
                        <Button type="link" danger>删除</Button>
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    return (
        <div style={{ padding: '0 10px' }}>
            <Card title="已舍弃内容">
                <ContentDataTable
                    listState={listState}
                    columns={columns}
                    contentKind={contentKind}
                    showSourceFilter={false}
                    toolbarChildren={(
                        <>
                            <Popconfirm title="确定恢复全部?" description="将把所有已舍弃内容恢复为待审核状态" onConfirm={requeueAll}>
                                <Button>批量恢复</Button>
                            </Popconfirm>
                            <Popconfirm title="确定清除所有审核结果？" description="将把所有已审核内容恢复为待审核状态" onConfirm={clearAll}>
                                <Button danger>清空审核结果</Button>
                            </Popconfirm>
                        </>
                    )}
                />
            </Card>
        </div>
    );
};

DiscardedContentTab.propTypes = {
    onAddToFeatured: PropTypes.func,
    contentKind: PropTypes.string,
};

export default DiscardedContentTab;
