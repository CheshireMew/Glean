import React, { useState, useEffect, useRef } from 'react';
import PropTypes from 'prop-types';
import { Card, Col, Select, Button, Tag } from 'antd';
import { PlayCircleOutlined, PauseCircleOutlined } from '@ant-design/icons';

const { Option } = Select;
const STATUS_LABELS = {
    idle: '就绪',
    queued: '等待运行',
    running: '运行中',
    error: '运行失败',
};

/**
 * 爬虫控制卡片组件
 * 用于显示单个爬虫的状态和控制面板
 */
const ScraperCard = ({ name, displayName, contentKind, status, onRun, onCancel, onConfigChange }) => {
    const isRunning = status.status === 'running';
    const isBusy = status.status === 'queued' || isRunning;

    // Optimistic UI: Initialize with props, but allow immediate local input
    // Default to 20 to match backend default configuration
    const [localLimit, setLocalLimit] = useState(status.limit || 20);
    const [localInterval, setLocalInterval] = useState(() => {
        if (status.interval) return String(status.interval);
        return "manual"; // Default to manual if undefined
    });
    const [savingConfig, setSavingConfig] = useState(null);

    useEffect(() => {
        const timer = setTimeout(() => {
            if (status.limit !== undefined) {
                setLocalLimit(status.limit);
            }
            if (status.interval !== undefined && status.interval !== null) {
                setLocalInterval(String(status.interval));
            } else {
                setLocalInterval("manual");
            }
        }, 0);
        return () => clearTimeout(timer);
    }, [status.limit, status.interval]);

    // Console Auto-scroll Logic
    const logContainerRef = useRef(null);
    const [shouldAutoScroll, setShouldAutoScroll] = useState(true);

    useEffect(() => {
        if (shouldAutoScroll && logContainerRef.current) {
            logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
        }
    }, [status.logs, shouldAutoScroll]);

    const handleScroll = () => {
        if (logContainerRef.current) {
            const { scrollTop, scrollHeight, clientHeight } = logContainerRef.current;
            // tolerance of 10px
            const isAtBottom = scrollHeight - scrollTop - clientHeight < 20;
            setShouldAutoScroll(isAtBottom);
        }
    };

    const handleConfigUpdate = async (key, val) => {
        const previousValue = key === 'limit' ? localLimit : localInterval;
        if (key === 'limit') setLocalLimit(val);
        if (key === 'interval') setLocalInterval(val);
        setSavingConfig(key);
        const saved = await onConfigChange(name, { [key]: val });
        if (!saved) {
            if (key === 'limit') setLocalLimit(previousValue);
            if (key === 'interval') setLocalInterval(previousValue);
        }
        setSavingConfig(null);
    };

    return (
        <Col xs={24} md={12} xl={8}>
            <Card
                title={displayName}
                extra={<Tag color={isRunning ? 'processing' : (status.status === 'error' ? 'error' : 'success')}>{STATUS_LABELS[status.status] || '状态未知'}</Tag>}
            >
                <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
                    <span style={{ fontSize: 12 }}>限制条数:</span>
                    <Select
                        listHeight={180}
                        value={localLimit}
                        style={{ width: 80 }}
                        size="small"
                        loading={savingConfig === 'limit'}
                        disabled={Boolean(savingConfig)}
                        onChange={(val) => handleConfigUpdate('limit', val)}
                    >
                        <Option value={5}>5</Option>
                        <Option value={10}>10</Option>
                        <Option value={15}>15</Option>
                        <Option value={20}>20</Option>
                        <Option value={30}>30</Option>
                    </Select>


                    <span style={{ fontSize: 12 }}>频率:</span>
                    <Select
                        listHeight={180}
                        value={localInterval}
                        style={{ width: 90 }}
                        size="small"
                        loading={savingConfig === 'interval'}
                        disabled={Boolean(savingConfig)}
                        onChange={(val) => handleConfigUpdate('interval', val)}
                    >
                        <Option value="manual">手动</Option>
                        {/* 文章爬虫使用不同的频率选项（包括foresight专栏和article后缀的爬虫） */}
                        {contentKind === 'article' ? (
                            <>
                                <Option value="60">1小时</Option>
                                <Option value="120">2小时</Option>
                                <Option value="240">4小时</Option>
                                <Option value="480">8小时</Option>
                                <Option value="720">12小时</Option>
                                <Option value="1440">24小时</Option>
                            </>
                        ) : (
                            <>
                                <Option value="15">15分钟</Option>
                                <Option value="30">30分钟</Option>
                                <Option value="60">1小时</Option>
                                <Option value="120">2小时</Option>
                                <Option value="180">3小时</Option>
                                <Option value="300">5小时</Option>
                            </>
                        )}
                    </Select>

                    {isBusy ? (
                        <Button
                            type="primary"
                            danger
                            size="small"
                            icon={<PauseCircleOutlined />}
                            onClick={() => onCancel(name)}
                        >
                            停止
                        </Button>
                    ) : (
                        <Button
                            type="primary"
                            size="small"
                            icon={<PlayCircleOutlined />}
                            loading={isBusy}
                            onClick={() => onRun(name, localLimit)}
                        >
                            运行
                        </Button>
                    )}
                </div>

                <div
                    ref={logContainerRef}
                    onScroll={handleScroll}
                    style={{
                        background: '#000',
                        color: '#0f0',
                        padding: '8px 12px',
                        borderRadius: 4,
                        fontSize: 12,
                        height: 150,
                        overflowY: 'auto',
                        fontFamily: 'monospace'
                    }}
                >
                    <div style={{ color: '#8c8c8c', marginBottom: 4, borderBottom: '1px solid #333', paddingBottom: 4 }}>
                        &gt; 运行日志
                    </div>
                    {status.logs && status.logs.length > 0 ? (
                        status.logs.map((log, idx) => (
                            <div key={idx} style={{ lineHeight: '1.4', whiteSpace: 'pre-wrap' }}>{log}</div>
                        ))
                    ) : (
                        <div style={{ color: '#666', textAlign: 'center', marginTop: 40 }}>
                            {status.status === 'idle' && status.last_result ? status.last_result : '等待运行日志…'}
                        </div>
                    )}
                </div>
            </Card>
        </Col>
    );
};

ScraperCard.propTypes = {
    name: PropTypes.string.isRequired,
    displayName: PropTypes.string,
    contentKind: PropTypes.string,
    status: PropTypes.object,
    onRun: PropTypes.func.isRequired,
    onCancel: PropTypes.func.isRequired,
    onConfigChange: PropTypes.func.isRequired,
};

export default ScraperCard;
