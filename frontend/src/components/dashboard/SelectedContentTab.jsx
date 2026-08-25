import React, { useState } from 'react';
import PropTypes from 'prop-types';
import { Space, Button, Form, Input, Modal, Popconfirm, Select, message } from 'antd';

import { useSelectedContentTab } from '../../hooks/dashboard/useSelectedContentTab';
import ContentDataTable from './ContentDataTable';
import { EXPORT_SCOPE } from '../../contracts/content';
import { formatLocalDateTime } from '../../utils/time';
import { createReviewResultColumns } from './reviewResultColumns';
import EditorialEntryModal from './EditorialEntryModal';
import { createPublicationDraft } from '../../api/editorial';
import { listPublications } from '../../api/publications';

const SelectedContentTab = ({ spiders, onAddToFeatured, onShowExport, contentKind }) => {
    const listState = useSelectedContentTab(contentKind);
    const { deleteItem } = listState;
    const [editingId, setEditingId] = useState(null);
    const [selectedIds, setSelectedIds] = useState([]);
    const [draftOpen, setDraftOpen] = useState(false);
    const [publications, setPublications] = useState([]);
    const [draftForm] = Form.useForm();

    const openDraft = async () => {
        try {
            const response = await listPublications();
            const options = (response.data || []).filter((item) => item.enabled && item.content_type === contentKind);
            if (!options.length) throw new Error('当前内容类型没有启用的发布频道');
            setPublications(options); setDraftOpen(true);
            draftForm.setFieldsValue({ publication_id: options[0].id, title: '', section: '其他' });
        } catch (error) { message.error(error.message || '发布频道加载失败'); }
    };
    const createDraft = async () => {
        try {
            const values = await draftForm.validateFields();
            await createPublicationDraft({ publication_id: values.publication_id, content_type: contentKind, title: values.title, items: selectedIds.map((id, position) => ({ review_entry_id: id, position, section: values.section, included: true, overrides: {} })) });
            message.success('发布草稿已建立，可到“发布中心”排期或发布'); setDraftOpen(false); setSelectedIds([]);
        } catch (error) { if (!error?.errorFields) message.error(error.message || '草稿创建失败'); }
    };

    const columns = [
        ...createReviewResultColumns('green'),
        {
            title: '发布时间',
            dataIndex: 'published_at',
            width: 160,
            render: formatLocalDateTime,
        },
        { title: '来源', dataIndex: 'source_site', width: 100 },
        {
            title: '操作',
            key: 'action',
            width: 230,
            render: (_, record) => (
                <Space>
                    <Button size="small" onClick={() => setEditingId(record.id)}>编辑</Button>
                    <Button type="primary" size="small" onClick={() => onAddToFeatured && onAddToFeatured(record)}>
                        加入输出
                    </Button>
                    <Popconfirm title="确定删除?" onConfirm={() => deleteItem(record.id)}>
                        <Button type="link" danger size="small">删除</Button>
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    return (
        <>
        <ContentDataTable
            listState={listState}
            columns={columns}
            spiders={spiders}
            contentKind={contentKind}
            exportScope={EXPORT_SCOPE.SELECTED}
            onShowExport={onShowExport}
            toolbarChildren={<Button type="primary" disabled={!selectedIds.length} onClick={openDraft}>建立发布草稿（{selectedIds.length}）</Button>}
            rowSelection={{ selectedRowKeys: selectedIds, preserveSelectedRowKeys: true, onChange: (keys) => setSelectedIds(keys) }}
            wrapperStyle={{ padding: '0 10px' }}
        />
        <EditorialEntryModal entryId={editingId} open={editingId !== null} onClose={() => setEditingId(null)} onSaved={() => listState.fetchItems()} />
        <Modal title="建立发布草稿" open={draftOpen} onCancel={() => setDraftOpen(false)} onOk={createDraft} destroyOnClose><Form form={draftForm} layout="vertical"><Form.Item name="publication_id" label="发布频道" rules={[{ required: true }]}><Select options={publications.map((item) => ({ value: item.id, label: item.display_name }))} /></Form.Item><Form.Item name="title" label="草稿标题" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="section" label="默认栏目" rules={[{ required: true }]}><Input /></Form.Item><p>已选择 {selectedIds.length} 条内容，建立后可在发布中心调整顺序、栏目和是否包含。</p></Form></Modal>
        </>
    );
};

SelectedContentTab.propTypes = {
    spiders: PropTypes.arrayOf(PropTypes.object),
    onAddToFeatured: PropTypes.func,
    onShowExport: PropTypes.func,
    contentKind: PropTypes.string,
};

export default SelectedContentTab;
