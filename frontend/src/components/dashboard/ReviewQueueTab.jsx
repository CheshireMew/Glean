
import React from 'react';
import PropTypes from 'prop-types';
import { Button, Space, Tag } from 'antd';

import { useReviewQueueTab } from '../../hooks/dashboard/useReviewQueueTab';
import ContentDataTable from './ContentDataTable';
import ReviewRunnerPanel from './ReviewRunnerPanel';
import { EXPORT_SCOPE } from '../../contracts/content';
import { formatLocalDateTime } from '../../utils/time';

const ReviewQueueTab = ({ spiders, onAddToFeatured, onShowExport, active, contentKind }) => {
    const listState = useReviewQueueTab(contentKind, active);

    const columns = [
        { title: 'ID', dataIndex: 'id', width: 60 },
        {
            title: '标题',
            dataIndex: 'title',
            ellipsis: true,
            render: (text, record) => <a href={record.source_url} target="_blank" rel="noopener noreferrer">{text}</a>,
        },
        { title: '内容档案', dataIndex: 'profile_name', width: 120, render: (value) => <Tag>{value || '-'}</Tag> },
        { title: '来源', dataIndex: 'source_site', width: 120 },
        {
            title: '发布时间',
            dataIndex: 'published_at',
            width: 160,
            render: formatLocalDateTime,
        },
        {
            title: '操作',
            width: 120,
            render: (_, record) => (
                <Space>
                    <Button type="primary" size="small" onClick={() => onAddToFeatured && onAddToFeatured(record)}>
                        加入输出
                    </Button>
                </Space>
            ),
        },
    ];

    return (
        <div style={{ padding: '0 10px' }}>
            <ReviewRunnerPanel contentKind={contentKind} />
            <ContentDataTable
                listState={listState}
                columns={columns}
                spiders={spiders}
                contentKind={contentKind}
                exportScope={EXPORT_SCOPE.REVIEW}
                onShowExport={onShowExport}
            />
        </div>
    );
};

ReviewQueueTab.propTypes = {
    spiders: PropTypes.arrayOf(PropTypes.object),
    onAddToFeatured: PropTypes.func,
    onShowExport: PropTypes.func,
    active: PropTypes.bool,
    contentKind: PropTypes.string,
};

export default ReviewQueueTab;
