import React from 'react';
import PropTypes from 'prop-types';
import { Button, Popconfirm, Tag } from 'antd';

import { useIncomingContentTab } from '../../hooks/dashboard/useIncomingContentTab';
import ContentDataTable from './ContentDataTable';
import { EXPORT_SCOPE } from '../../contracts/content';
import { formatLocalDateTime } from '../../utils/time';


const NewsManagementTab = ({ spiders, onShowExport, contentKind }) => {
    const listState = useIncomingContentTab(contentKind);
    const { deleteItem } = listState;

    const columns = [
        { title: 'ID', dataIndex: 'id', width: 60 },
        {
            title: '标题',
            dataIndex: 'title',
            ellipsis: true,
            render: (text, record) => (
                <a href={record.source_url} target="_blank" rel="noopener noreferrer">
                    {text}
                </a>
            )
        },
        { title: '来源', dataIndex: 'source_site', width: 120 },
        {
            title: '作者',
            dataIndex: 'author',
            width: 140,
            render: (text) => text || '-'
        },
        {
            title: '状态',
            dataIndex: 'stage',
            width: 90,
            render: () => <Tag color="green">待归档</Tag>
        },
        {
            title: '发布时间',
            dataIndex: 'published_at',
            width: 160,
            render: formatLocalDateTime,
        },
        {
            title: '操作',
            width: 80,
            render: (_, record) => (
                <Popconfirm
                    title="确认删除这条采集来源？"
                    description={record.source_count > 1
                        ? '这会移除当前来源；同一事件的其他来源和后续处理结果会保留。'
                        : '如果这是事件的最后一个来源，关联事件、归档和审核结果也会一并删除，且无法恢复。'}
                    okText="确认删除"
                    cancelText="取消"
                    okButtonProps={{ danger: true }}
                    onConfirm={() => deleteItem(record.id)}
                >
                    <Button type="link" danger size="small">删除</Button>
                </Popconfirm>
            )
        }
    ];

    return (
        <ContentDataTable
            listState={listState}
            columns={columns}
            spiders={spiders}
            contentKind={contentKind}
            exportScope={EXPORT_SCOPE.INCOMING}
            onShowExport={onShowExport}
        />
    );
};

NewsManagementTab.propTypes = {
    spiders: PropTypes.arrayOf(PropTypes.object),
    onShowExport: PropTypes.func,
    contentKind: PropTypes.string,
};

export default NewsManagementTab;
