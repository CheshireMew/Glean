import React from 'react';
import PropTypes from 'prop-types';
import { Button, Space, Popconfirm } from 'antd';

import { useArchiveContentTab } from '../../hooks/dashboard/useArchiveContentTab';
import ContentDataTable from './ContentDataTable';
import { EXPORT_SCOPE } from '../../contracts/content';
import { formatLocalDateTime } from '../../utils/time';

const ArchiveTab = ({ spiders, onAddToFeatured, onShowExport, contentKind }) => {
    const listState = useArchiveContentTab(contentKind);
    const { restoreItem, deleteItem } = listState;

    const columns = [
        { title: 'ID', dataIndex: 'id', width: 70 },
        {
            title: '标题',
            dataIndex: 'title',
            ellipsis: true,
            render: (text, record) => (
                <a href={record.source_url} target="_blank" rel="noopener noreferrer">
                    {text}
                </a>
            ),
        },
        { title: '来源', dataIndex: 'source_site', width: 120 },
        {
            title: '发布时间',
            dataIndex: 'published_at',
            width: 180,
            render: formatLocalDateTime,
        },
        {
            title: '操作',
            width: 220,
            render: (_, record) => (
                <Space>
                    <Button size="small" type="primary" onClick={() => onAddToFeatured && onAddToFeatured(record)}>
                        加入输出
                    </Button>
                    <Button size="small" onClick={() => restoreItem(record.id)}>
                        还原
                    </Button>
                    <Popconfirm title="确定删除这条内容？" onConfirm={() => deleteItem(record.id)}>
                        <Button size="small" danger>
                            删除
                        </Button>
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    return (
        <ContentDataTable
            listState={listState}
            columns={columns}
            spiders={spiders}
            contentKind={contentKind}
            exportScope={EXPORT_SCOPE.ARCHIVE}
            onShowExport={onShowExport}
        />
    );
};

ArchiveTab.propTypes = {
    spiders: PropTypes.arrayOf(PropTypes.object),
    onAddToFeatured: PropTypes.func,
    onShowExport: PropTypes.func,
    contentKind: PropTypes.string,
};

export default ArchiveTab;
