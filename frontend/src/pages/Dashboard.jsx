import React, { lazy, Suspense, useState } from 'react';
import { Alert, ConfigProvider, Layout, Button, Card, Row, Col, Statistic, Segmented, Tabs, Modal, message } from 'antd';
import { LogoutOutlined, RobotOutlined, DatabaseOutlined, DownloadOutlined, AppstoreOutlined, BellOutlined, CloudUploadOutlined, RadarChartOutlined } from '@ant-design/icons';

import { logout } from '../api/auth';
import { CONTENT_KIND } from '../contracts/content';
import { useDashboardData } from '../hooks/useDashboardData';
import DashboardExportModal from '../components/dashboard/DashboardExportModal';
import { UnsavedChangesProvider } from '../hooks/dashboard/UnsavedChangesContext';
import { useUnsavedChangesStatus } from '../hooks/dashboard/useUnsavedChanges';

const { Header, Content } = Layout;

const NewsManagementTab = lazy(() => import('../components/dashboard/NewsManagementTab'));
const EventGroupsTab = lazy(() => import('../components/dashboard/EventGroupsTab'));
const ArchiveTab = lazy(() => import('../components/dashboard/ArchiveTab'));
const ReviewQueueTab = lazy(() => import('../components/dashboard/ReviewQueueTab'));
const DiscardedContentTab = lazy(() => import('../components/dashboard/DiscardedContentTab'));
const SelectedContentTab = lazy(() => import('../components/dashboard/SelectedContentTab'));
const SpiderControlTab = lazy(() => import('../components/dashboard/SpiderControlTab'));
const SystemSettingsTab = lazy(() => import('../components/dashboard/SystemSettingsTab'));
const ExportTab = lazy(() => import('../components/dashboard/ExportTab'));
const BlocklistTab = lazy(() => import('../components/dashboard/BlocklistTab'));
const AiQualityTab = lazy(() => import('../components/dashboard/AiQualityTab'));
const PublicationCenterTab = lazy(() => import('../components/dashboard/PublicationCenterTab'));
const IntelligenceCenterTab = lazy(() => import('../components/dashboard/IntelligenceCenterTab'));
const SourceOperationsTab = lazy(() => import('../components/dashboard/SourceOperationsTab'));
const WechatSourceManager = lazy(() => import('../components/dashboard/WechatSourceManager'));

const DashboardContent = () => {
    const [activeKey, setActiveKey] = useState(() => new URLSearchParams(window.location.search).get('tab') === 'wechat' ? 'wechat' : '1');
    const [contentKind, setContentKind] = useState(CONTENT_KIND.NEWS);
    const [loggingOut, setLoggingOut] = useState(false);
    const {
        stats,
        spiders,
        spiderStatus,
        rssSources,
        runtimeError,
        overview,
        overviewState,
        manuallyFeatured,
        setManuallyFeatured,
        exportState,
        actions,
    } = useDashboardData(contentKind, activeKey);
    const { hasUnsavedChanges, discardUnsavedChanges } = useUnsavedChangesStatus();

    const runWithUnsavedGuard = (action) => {
        if (!hasUnsavedChanges) {
            action();
            return;
        }
        Modal.confirm({
            title: '放弃未保存的配置？',
            content: '系统配置中还有未保存的修改。离开后这些修改将丢失。',
            okText: '放弃修改并离开',
            cancelText: '继续编辑',
            okButtonProps: { danger: true },
            onOk() {
                discardUnsavedChanges();
                action();
            },
        });
    };

    const handleLogout = () => {
        runWithUnsavedGuard(async () => {
            setLoggingOut(true);
            try {
                await logout();
                window.location.href = '/login';
            } catch (error) {
                message.error(`退出失败，请重试：${error.message}`);
            } finally {
                setLoggingOut(false);
            }
        });
    };

    const handleTabChange = (key) => {
        if (key === activeKey) return;
        runWithUnsavedGuard(() => {
            setActiveKey(key);
            actions.fetchOverview();
            if (key === '1') {
                actions.fetchStats();
            }
        });
    };

    const overviewValue = (key) => overviewState.loaded && overview ? overview[key] : '—';

    const tabItems = [
        {
            key: 'wechat',
            label: <span><RadarChartOutlined />公众号采集</span>,
            children: <WechatSourceManager />,
        },
        {
            key: '1',
            label: <span><DatabaseOutlined />采集池 ({overviewValue('incoming')})</span>,
            children: <NewsManagementTab spiders={spiders} onShowExport={exportState.open} contentKind={contentKind} />
        },
        {
            key: '1.5',
            label: <span><AppstoreOutlined />事件聚合</span>,
            children: <EventGroupsTab spiders={spiders} contentKind={contentKind} />
        },
        {
            key: '3',
            label: <span><DatabaseOutlined />归档池 ({overviewValue('archive')})</span>,
            children: <ArchiveTab spiders={spiders} onAddToFeatured={(record) => actions.handleAddToFeatured(record, 'archive')} onShowExport={exportState.open} contentKind={contentKind} />
        },
        {
            key: '4',
            label: <span><DatabaseOutlined />已拦截 ({overviewValue('blocked')})</span>,
            children: <BlocklistTab onAddToFeatured={(record) => actions.handleAddToFeatured(record, 'blocked')} active={activeKey === '4'} contentKind={contentKind} />
        },
        {
            key: '5',
            label: <span><DatabaseOutlined />待审核 ({overviewValue('review')})</span>,
            children: <ReviewQueueTab spiders={spiders} onAddToFeatured={(record) => actions.handleAddToFeatured(record, 'review')} onShowExport={exportState.open} active={activeKey === '5'} contentKind={contentKind} />
        },
        {
            key: '8',
            label: <span><RobotOutlined />已舍弃 ({overviewValue('discarded')})</span>,
            children: <DiscardedContentTab onAddToFeatured={(record) => actions.handleAddToFeatured(record, 'discarded')} contentKind={contentKind} />
        },
        {
            key: '9',
            label: <span><DatabaseOutlined />已选入 ({overviewValue('selected')})</span>,
            children: <SelectedContentTab spiders={spiders} onAddToFeatured={(record) => actions.handleAddToFeatured(record, 'selected')} onShowExport={exportState.open} contentKind={contentKind} />
        },
        {
            key: '2',
            label: <span><RobotOutlined />爬虫控制</span>,
            children: (
                <SpiderControlTab
                    spiders={spiders}
                    spiderStatus={spiderStatus}
                    rssSources={rssSources}
                    runtimeError={runtimeError}
                    onRetryRuntime={() => actions.refreshRuntime()}
                    onRun={actions.handleRunSpider}
                    onCancel={actions.handleStopSpider}
                    onConfigChange={actions.handleConfigChange}
                    onCreateRssSource={actions.handleCreateRssSource}
                    onUpdateRssSource={actions.handleUpdateRssSource}
                    onDeleteRssSource={actions.handleDeleteRssSource}
                    contentKind={contentKind}
                />
            )
        },
        {
            key: '6',
            label: <span><RobotOutlined />系统配置</span>,
            children: <SystemSettingsTab />
        },
        {
            key: '10',
            label: <span><RobotOutlined />AI 质量</span>,
            children: <AiQualityTab />
        },
        {
            key: '11',
            label: <span><CloudUploadOutlined />发布中心</span>,
            children: <PublicationCenterTab />
        },
        {
            key: '12',
            label: <span><RadarChartOutlined />情报目录</span>,
            children: <IntelligenceCenterTab />
        },
        {
            key: '13',
            label: <span><BellOutlined />来源运营</span>,
            children: <SourceOperationsTab />
        },
        {
            key: '7',
            label: <span><DownloadOutlined />结果输出</span>,
            children: <ExportTab manuallyFeatured={manuallyFeatured} setManuallyFeatured={setManuallyFeatured} contentKind={contentKind} />
        }
    ];

    const activeTabItem = tabItems.find((item) => item.key === activeKey) ?? tabItems[0];

    return (
        <ConfigProvider theme={{ token: { colorPrimary: '#2563eb', borderRadius: 10, colorBgLayout: '#f1f5f9', fontFamily: 'Inter, "Segoe UI", "Microsoft YaHei", sans-serif' } }}>
        <Layout className="admin-shell">
            <Header className="admin-header">
                <div className="admin-brand">
                    <span className="admin-brand-mark">AI</span>
                    <span>
                        <h1>Glean</h1>
                        <small>内容运营后台</small>
                    </span>
                </div>
                <div className="admin-actions">
                    <Segmented
                        options={[
                            { label: '⚡️ 快讯', value: CONTENT_KIND.NEWS },
                            { label: '📄 文章', value: CONTENT_KIND.ARTICLE }
                        ]}
                        value={contentKind}
                        onChange={setContentKind}
                    />
                        <Button type="primary" danger icon={<LogoutOutlined />} onClick={handleLogout} loading={loggingOut}>
                        退出
                    </Button>
                </div>
            </Header>
            <Content className="admin-content">
                {overviewState.error && (
                    <Alert
                        type="error"
                        showIcon
                        title={overviewState.loaded ? '统计刷新失败，当前显示上次成功结果' : '统计读取失败，数量暂不可用'}
                        description={overviewState.error}
                        action={<Button onClick={() => actions.fetchStats()}>重新读取</Button>}
                        style={{ marginBottom: 16 }}
                    />
                )}
                <div className="admin-stats" style={{ marginBottom: 20 }}>
                    {overviewState.loading && !overviewState.loaded && <span role="status" className="admin-loading-note">正在读取统计数据…</span>}
                    <Row gutter={[16, 16]}>
                        {stats.map((item) => (
                            <Col xs={12} sm={8} md={8} lg={6} xl={4} key={item.source}>
                                <Card size="small" className="admin-stat-card">
                                    <Statistic
                                        title={item.source}
                                        value={item.count}
                                        formatter={(value) => <span style={{ color: '#3f8600' }}>{value}</span>}
                                        prefix={<DatabaseOutlined />}
                                    />
                                </Card>
                            </Col>
                        ))}
                    </Row>
                </div>

                <div className="admin-panel">
                    <Tabs
                        destroyOnHidden
                        activeKey={activeKey}
                        onChange={handleTabChange}
                        items={tabItems.map((item) => ({
                            key: item.key,
                            label: item.label,
                            children: item.key === activeTabItem.key ? <Suspense fallback={<div role="status" style={{ padding: 24, textAlign: 'center' }}>正在加载后台模块…</div>}>{item.children}</Suspense> : null,
                        }))}
                    />
                </div>
            </Content>

            <DashboardExportModal exportState={exportState} />
        </Layout>
        </ConfigProvider>
    );
};

export default function Dashboard() {
    return (
        <UnsavedChangesProvider>
            <DashboardContent />
        </UnsavedChangesProvider>
    );
}
