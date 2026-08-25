import React from 'react';
import { Alert, Button, Card, Form, Input, Space, Switch, Typography } from 'antd';
import { SaveOutlined, SendOutlined } from '@ant-design/icons';
import { useTelegramSettings } from '../../../hooks/dashboard/system-settings/useTelegramSettings';

export default function TelegramSettingsCard() {
    const { config, setConfig, loadState, action, dirty, reload, reset, save, test } = useTelegramSettings();

    return (
        <Card title={<Space><SendOutlined /> Telegram 推送配置</Space>} loading={loadState.loading} style={{ marginBottom: 20 }}>
            {loadState.error && <Alert type="error" showIcon title="当前配置读取失败" description={loadState.error} action={<Button onClick={reload}>重新读取</Button>} style={{ marginBottom: 16 }} />}
            <Form layout="vertical" disabled={!loadState.loaded || Boolean(action)}>
                <Form.Item label="Bot Token">
                    <Input.Password value={config.bot_token} onChange={(event) => setConfig((prev) => ({ ...prev, bot_token: event.target.value }))} placeholder="123456789:ABCDef..." />
                    <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>从 @BotFather 获取</div>
                </Form.Item>
                <Form.Item label="Chat ID">
                    <Input value={config.chat_id} onChange={(event) => setConfig((prev) => ({ ...prev, chat_id: event.target.value }))} placeholder="@channel_name or -100xxx" />
                    <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>目标频道/群组 ID，需先将 Bot 拉入并设为管理员</div>
                </Form.Item>
                <Form.Item label="启用推送">
                    <Switch checked={config.enabled} onChange={(enabled) => setConfig((prev) => ({ ...prev, enabled }))} />
                    <span style={{ marginLeft: 8, color: '#999' }}>(仅推送已选入内容)</span>
                </Form.Item>
                <Space wrap>
                    <Button type="primary" icon={<SaveOutlined />} loading={action === 'save'} onClick={save} disabled={!dirty}>保存配置</Button>
                    <Button loading={action === 'test'} onClick={test}>测试当前填写内容</Button>
                    <Button onClick={reset} disabled={!dirty}>撤销修改</Button>
                    {dirty && <Typography.Text type="warning">有未保存修改</Typography.Text>}
                </Space>
                <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0, fontSize: 12 }}>
                    测试会向当前表单中的目标发送一条消息，不会自动保存配置。
                </Typography.Paragraph>
            </Form>
        </Card>
    );
}
