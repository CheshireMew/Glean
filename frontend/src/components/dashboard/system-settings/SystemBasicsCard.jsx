import React from 'react';
import { Alert, Button, Card, Form, Input, InputNumber, Select, Space, Switch, Typography } from 'antd';
import { GlobalOutlined, SaveOutlined } from '@ant-design/icons';
import { useSystemBasicsSettings } from '../../../hooks/dashboard/system-settings/useSystemBasicsSettings';
import TimeRangeSelect from '../TimeRangeSelect';

const { Option } = Select;
const { Text } = Typography;

export default function SystemBasicsCard() {
    const { timezone, saving, loadState, newsConfig, articleConfig, deliverySchedule, runtimeConfig, dirty, setTimezone, setDeliverySchedule, setRuntimeConfig, updateHours, reload, reset, save } = useSystemBasicsSettings();

    return (
        <Card title={<Space><GlobalOutlined /> 系统基础配置</Space>} loading={loadState.loading}>
            {loadState.error && (
                <Alert
                    type="error"
                    showIcon
                    title="当前配置读取失败"
                    description={loadState.error}
                    action={<Button onClick={reload}>重新读取</Button>}
                    style={{ marginBottom: 16 }}
                />
            )}
            <Form layout="inline" disabled={!loadState.loaded || saving} style={{ flexWrap: 'wrap' }}>
                <Form.Item label="系统时区" style={{ marginBottom: 16, minWidth: 'min(300px, 100%)' }}>
                    <Select value={timezone} onChange={setTimezone} style={{ width: 250, maxWidth: '100%' }} showSearch>
                        <Option value="Asia/Shanghai">Asia/Shanghai (北京时间)</Option>
                        <Option value="UTC">UTC (世界协调时)</Option>
                        <Option value="America/New_York">America/New_York (美东)</Option>
                        <Option value="America/Los_Angeles">America/Los_Angeles (美西)</Option>
                        <Option value="Europe/London">Europe/London (伦敦)</Option>
                        <Option value="Asia/Tokyo">Asia/Tokyo (东京)</Option>
                        <Option value="Asia/Singapore">Asia/Singapore (新加坡)</Option>
                        <Option value="Australia/Sydney">Australia/Sydney (悉尼)</Option>
                    </Select>
                </Form.Item>

                <div style={{ width: '100%', marginBottom: 16 }} />
                <div style={{ width: '100%', marginBottom: 8 }}>
                    <Text strong>自动任务运行计划</Text>
                </div>
                <Form.Item label="启用" style={{ marginBottom: 16 }}>
                    <Switch checked={runtimeConfig.enabled} onChange={(enabled) => setRuntimeConfig((prev) => ({ ...prev, enabled }))} />
                </Form.Item>
                <Form.Item label="开始时间" style={{ marginBottom: 16 }}>
                    <Input value={runtimeConfig.start_time} onChange={(event) => setRuntimeConfig((prev) => ({ ...prev, start_time: event.target.value }))} style={{ width: 100 }} />
                </Form.Item>
                <Form.Item label="结束时间" style={{ marginBottom: 16 }}>
                    <Input value={runtimeConfig.end_time} onChange={(event) => setRuntimeConfig((prev) => ({ ...prev, end_time: event.target.value }))} style={{ width: 100 }} />
                </Form.Item>
                <Form.Item label="周期（分钟）" style={{ marginBottom: 16 }}>
                    <InputNumber min={5} max={1440} value={runtimeConfig.interval_minutes} onChange={(value) => setRuntimeConfig((prev) => ({ ...prev, interval_minutes: value }))} />
                </Form.Item>
                <Form.Item label="审核批次" style={{ marginBottom: 16 }}>
                    <InputNumber min={1} max={500} value={runtimeConfig.review_batch_size} onChange={(value) => setRuntimeConfig((prev) => ({ ...prev, review_batch_size: value }))} />
                </Form.Item>
                <Form.Item label="补充分析批次" style={{ marginBottom: 16 }}>
                    <InputNumber min={1} max={500} value={runtimeConfig.enrichment_batch_size} onChange={(value) => setRuntimeConfig((prev) => ({ ...prev, enrichment_batch_size: value }))} />
                </Form.Item>
                <Form.Item label="单周期最多审核批数" style={{ marginBottom: 16 }}>
                    <InputNumber min={1} max={100} value={runtimeConfig.max_review_batches_per_cycle} onChange={(value) => setRuntimeConfig((prev) => ({ ...prev, max_review_batches_per_cycle: value }))} />
                </Form.Item>
                <Form.Item label="积压追尾间隔（秒）" style={{ marginBottom: 16 }}>
                    <InputNumber min={5} max={3600} value={runtimeConfig.backlog_retry_seconds} onChange={(value) => setRuntimeConfig((prev) => ({ ...prev, backlog_retry_seconds: value }))} />
                </Form.Item>
                <Form.Item label="采集器并发上限" style={{ marginBottom: 16 }}>
                    <InputNumber min={1} max={8} value={runtimeConfig.scraper_concurrency} onChange={(value) => setRuntimeConfig((prev) => ({ ...prev, scraper_concurrency: value }))} />
                </Form.Item>
                <Form.Item label="数据库维护间隔（小时）" style={{ marginBottom: 16 }}>
                    <InputNumber min={1} max={168} value={runtimeConfig.maintenance_interval_hours} onChange={(value) => setRuntimeConfig((prev) => ({ ...prev, maintenance_interval_hours: value }))} />
                </Form.Item>
                <Form.Item label="运行记录保留（天）" style={{ marginBottom: 16 }}>
                    <InputNumber min={7} max={365} value={runtimeConfig.operational_retention_days} onChange={(value) => setRuntimeConfig((prev) => ({ ...prev, operational_retention_days: value }))} />
                </Form.Item>
                <Form.Item label="内容保留（天）" style={{ marginBottom: 16 }}>
                    <InputNumber min={30} max={3650} value={runtimeConfig.content_retention_days} onChange={(value) => setRuntimeConfig((prev) => ({ ...prev, content_retention_days: value }))} />
                </Form.Item>

                <div style={{ width: '100%', marginBottom: 16 }} />
                <div style={{ width: '100%', marginBottom: 8 }}>
                    <Text strong>快讯配置</Text>
                </div>
                <Form.Item label="事件匹配窗口" style={{ marginBottom: 16 }}>
                    <TimeRangeSelect value={newsConfig.cluster_window_hours} onChange={(value) => updateHours('news', 'cluster_window_hours', value)} />
                </Form.Item>
                <Form.Item label="聚合扫描范围" style={{ marginBottom: 16 }}>
                    <TimeRangeSelect value={newsConfig.cluster_hours} onChange={(value) => updateHours('news', 'cluster_hours', value)} />
                </Form.Item>
                <Form.Item label="过滤时间范围" style={{ marginBottom: 16 }}>
                    <TimeRangeSelect value={newsConfig.filter_hours} onChange={(value) => updateHours('news', 'filter_hours', value)} />
                </Form.Item>
                <Form.Item label="AI打分时间范围" style={{ marginBottom: 16 }}>
                    <TimeRangeSelect value={newsConfig.ai_scoring_hours} onChange={(value) => updateHours('news', 'ai_scoring_hours', value)} />
                </Form.Item>
                <Form.Item label="推送时间范围" style={{ marginBottom: 16 }}>
                    <TimeRangeSelect value={newsConfig.push_hours} onChange={(value) => updateHours('news', 'push_hours', value)} />
                </Form.Item>

                <div style={{ width: '100%', marginBottom: 8, marginTop: 16 }}>
                    <Text strong>深度文章配置</Text>
                </div>
                <Form.Item label="事件匹配窗口" style={{ marginBottom: 16 }}>
                    <TimeRangeSelect value={articleConfig.cluster_window_hours} onChange={(value) => updateHours('article', 'cluster_window_hours', value)} />
                </Form.Item>
                <Form.Item label="聚合扫描范围" style={{ marginBottom: 16 }}>
                    <TimeRangeSelect value={articleConfig.cluster_hours} onChange={(value) => updateHours('article', 'cluster_hours', value)} />
                </Form.Item>
                <Form.Item label="过滤时间范围" style={{ marginBottom: 16 }}>
                    <TimeRangeSelect value={articleConfig.filter_hours} onChange={(value) => updateHours('article', 'filter_hours', value)} />
                </Form.Item>
                <Form.Item label="AI打分时间范围" style={{ marginBottom: 16 }}>
                    <TimeRangeSelect value={articleConfig.ai_scoring_hours} onChange={(value) => updateHours('article', 'ai_scoring_hours', value)} />
                </Form.Item>
                <Form.Item label="推送时间范围" style={{ marginBottom: 16 }}>
                    <TimeRangeSelect value={articleConfig.push_hours} onChange={(value) => updateHours('article', 'push_hours', value)} />
                </Form.Item>

                <div style={{ width: '100%', marginBottom: 8, marginTop: 16 }}>
                    <Text strong>日报推送时间</Text>
                </div>
                <Form.Item label="快讯日报" style={{ marginBottom: 16 }}>
                    <Input
                        value={deliverySchedule.news_time}
                        onChange={(event) => setDeliverySchedule((prev) => ({ ...prev, news_time: event.target.value }))}
                        style={{ width: 120 }}
                        placeholder="HH:MM"
                    />
                </Form.Item>
                <Form.Item label="文章日报" style={{ marginBottom: 16 }}>
                    <Input
                        value={deliverySchedule.article_time}
                        onChange={(event) => setDeliverySchedule((prev) => ({ ...prev, article_time: event.target.value }))}
                        style={{ width: 120 }}
                        placeholder="HH:MM"
                    />
                </Form.Item>

                <div style={{ width: '100%', marginTop: 16 }}>
                    <Space wrap>
                        <Button type="primary" icon={<SaveOutlined />} onClick={save} loading={saving} disabled={!dirty}>
                            保存设置
                        </Button>
                        <Button onClick={reset} disabled={!dirty}>撤销未保存修改</Button>
                        {dirty && <Text type="warning">有未保存修改</Text>}
                    </Space>
                </div>
                <div style={{ marginTop: 8, color: '#666', fontSize: 13, width: '100%' }}>
                    * 此设置会影响定时任务、数据处理窗口和日报投递时间。
                </div>
            </Form>
        </Card>
    );
}
