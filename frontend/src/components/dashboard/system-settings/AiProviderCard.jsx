import React from 'react';
import { Alert, Button, Card, Form, Input, InputNumber, Space, Typography } from 'antd';
import { ApiOutlined, DeleteOutlined, PlusOutlined, SaveOutlined } from '@ant-design/icons';
import { useAiProviderSettings } from '../../../hooks/dashboard/system-settings/useAiProviderSettings';

export default function AiProviderCard() {
    const { config, setConfig, loadState, action, dirty, reload, reset, save, test, updateProvider, addProvider, removeProvider } = useAiProviderSettings();

    return (
        <Card title={<Space><ApiOutlined /> AI 服务配置</Space>} loading={loadState.loading} style={{ marginBottom: 20 }}>
            {loadState.error && <Alert type="error" showIcon title="当前配置读取失败" description={loadState.error} action={<Button onClick={reload}>重新读取</Button>} style={{ marginBottom: 16 }} />}
            <Form layout="vertical" disabled={!loadState.loaded || Boolean(action)}>
                {config.providers.map((provider, index) => (
                    <Card key={`${provider.name}-${index}`} type="inner" title={index === 0 ? '主端点' : `备用端点 ${index}`} style={{ marginBottom: 12 }} extra={index > 0 && <Button danger type="text" icon={<DeleteOutlined />} onClick={() => removeProvider(index)}>移除</Button>}>
                        <Form.Item label="端点名称"><Input value={provider.name} onChange={(event) => updateProvider(index, 'name', event.target.value)} /></Form.Item>
                        <Form.Item label="API Key"><Input.Password value={provider.api_key} onChange={(event) => updateProvider(index, 'api_key', event.target.value)} placeholder="sk-..." /></Form.Item>
                        <Form.Item label="OpenAI 兼容接口地址"><Input value={provider.base_url} onChange={(event) => updateProvider(index, 'base_url', event.target.value)} /></Form.Item>
                        <Form.Item label="模型"><Input value={provider.model} onChange={(event) => updateProvider(index, 'model', event.target.value)} /></Form.Item>
                        <Space wrap size="large">
                            <Form.Item label="输入价格（美元 / 百万 Token）"><InputNumber min={0} precision={6} value={provider.input_price_per_million || 0} onChange={(value) => updateProvider(index, 'input_price_per_million', value || 0)} /></Form.Item>
                            <Form.Item label="输出价格（美元 / 百万 Token）"><InputNumber min={0} precision={6} value={provider.output_price_per_million || 0} onChange={(value) => updateProvider(index, 'output_price_per_million', value || 0)} /></Form.Item>
                        </Space>
                    </Card>
                ))}
                <Button icon={<PlusOutlined />} onClick={addProvider} style={{ marginBottom: 16 }}>添加备用端点</Button>
                <Space size="large" wrap>
                    <Form.Item label="审核并发"><InputNumber min={1} max={20} value={config.analysis_concurrency} onChange={(value) => setConfig((prev) => ({ ...prev, analysis_concurrency: value }))} /></Form.Item>
                    <Form.Item label="补充并发"><InputNumber min={1} max={10} value={config.enrichment_concurrency} onChange={(value) => setConfig((prev) => ({ ...prev, enrichment_concurrency: value }))} /></Form.Item>
                    <Form.Item label="请求间隔（秒）"><InputNumber min={0} max={60} step={0.1} value={config.throttle_seconds} onChange={(value) => setConfig((prev) => ({ ...prev, throttle_seconds: value }))} /></Form.Item>
                </Space>
                <Space wrap>
                    <Button type="primary" icon={<SaveOutlined />} loading={action === 'save'} onClick={save} disabled={!dirty}>保存配置</Button>
                    <Button loading={action === 'test'} onClick={test}>测试当前填写内容</Button>
                    <Button onClick={reset} disabled={!dirty}>撤销修改</Button>
                    {dirty && <Typography.Text type="warning">有未保存修改</Typography.Text>}
                </Space>
                <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0, fontSize: 12 }}>
                    测试使用当前表单内容，不会自动保存。
                </Typography.Paragraph>
            </Form>
        </Card>
    );
}
