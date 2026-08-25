import React from 'react';
import { Alert, Button, Card, Form, Input, InputNumber, Select, Space, Switch, Tag } from 'antd';
import { PlusOutlined, SaveOutlined } from '@ant-design/icons';

import { useEditorialProfiles } from '../../../hooks/dashboard/system-settings/useEditorialProfiles';

export default function EditorialProfilesCard() {
    const { profiles, savingSlug, loadState, isProfileDirty, update, add, resetProfile, reload, save } = useEditorialProfiles();
    return (
        <Card title="内容档案" loading={loadState.loading} extra={<Button icon={<PlusOutlined />} disabled={!loadState.loaded} onClick={add}>新增档案</Button>} style={{ marginBottom: 20 }}>
            {loadState.error && <Alert type="error" showIcon title="当前内容档案读取失败" description={loadState.error} action={<Button onClick={reload}>重新读取</Button>} style={{ marginBottom: 16 }} />}
            <p style={{ color: '#666' }}>每个启用的档案都会独立审核新事件；默认档案的结果用于日报和公开内容。</p>
            {profiles.map((profile) => (
                <Card key={profile.slug} type="inner" title={profile.name} extra={isProfileDirty(profile) ? <Tag color="gold">未保存</Tag> : null} style={{ marginBottom: 12 }}>
                    <Form layout="vertical" disabled={!loadState.loaded || savingSlug === profile.slug}>
                        <Space wrap style={{ width: '100%' }}>
                            <Form.Item label="标识"><Input value={profile.slug} disabled /></Form.Item>
                            <Form.Item label="名称"><Input value={profile.name} onChange={(event) => update(profile.slug, 'name', event.target.value)} /></Form.Item>
                            <Form.Item label="内容类型">
                                <Select value={profile.content_type} style={{ width: 120 }} onChange={(value) => update(profile.slug, 'content_type', value)} options={[{ value: 'news', label: '快讯' }, { value: 'article', label: '文章' }]} />
                            </Form.Item>
                            <Form.Item label="最低分"><InputNumber min={1} max={10} value={profile.min_score} onChange={(value) => update(profile.slug, 'min_score', value)} /></Form.Item>
                            <Form.Item label="日报条数"><InputNumber min={1} max={100} value={profile.max_items} onChange={(value) => update(profile.slug, 'max_items', value)} /></Form.Item>
                            <Form.Item label="每类上限"><InputNumber min={1} max={100} value={profile.max_per_category} onChange={(value) => update(profile.slug, 'max_per_category', value)} /></Form.Item>
                            <Form.Item label="每来源上限"><InputNumber min={1} max={100} value={profile.max_per_source} onChange={(value) => update(profile.slug, 'max_per_source', value)} /></Form.Item>
                            <Form.Item label="启用"><Switch checked={profile.enabled} disabled={profile.is_default} onChange={(value) => update(profile.slug, 'enabled', value)} /></Form.Item>
                            <Form.Item label="默认"><Switch checked={profile.is_default} disabled={profile.is_default} onChange={(value) => update(profile.slug, 'is_default', value)} /></Form.Item>
                        </Space>
                        <Form.Item label="审核标准"><Input.TextArea rows={4} value={profile.review_prompt} onChange={(event) => update(profile.slug, 'review_prompt', event.target.value)} /></Form.Item>
                        <Form.Item label="入选后补充要求"><Input.TextArea rows={3} value={profile.enrichment_prompt} onChange={(event) => update(profile.slug, 'enrichment_prompt', event.target.value)} /></Form.Item>
                        <Space wrap>
                            <Button type="primary" icon={<SaveOutlined />} disabled={!isProfileDirty(profile)} loading={savingSlug === profile.slug} onClick={() => save(profile)}>保存</Button>
                            <Button disabled={!isProfileDirty(profile)} onClick={() => resetProfile(profile.slug)}>撤销修改</Button>
                        </Space>
                    </Form>
                </Card>
            ))}
        </Card>
    );
}
