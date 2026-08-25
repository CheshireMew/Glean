import React from 'react';
import { Button, Input, Select, Space } from 'antd';
import { SearchOutlined, DownloadOutlined, ReloadOutlined } from '@ant-design/icons';

const { Option } = Select;
// const { Search } = Input; // remove Search since we use Input now

/**
 * 通用新闻工具栏组件
 * 提供搜索、来源筛选、导出、刷新等标准功能，并支持扩展
 */
const NewsToolbar = ({
    searchValue,
    onSearchChange,
    searchPlaceholder = "搜索新闻...",

    spiders,            // 爬虫列表 (用于来源筛选) - 数组中元素为 {name: 'techflow', type: 'news'}
    selectedSource,     // 当前选中的来源
    onSourceChange,     // 来源变更回调 (value) => {}
    contentKind,        // 当前内容类型 ('news' | 'article') - 用于过滤对应类型的爬虫

    onExport,           // 导出回调 () => {}

    onRefresh,          // 刷新回调 () => {}
    loading,            // 加载状态

    children,           // 额外操作按钮 (如手动去重、时间筛选等)
    style               // 自定义样式
}) => {
    const filteredSpiders = spiders && contentKind
        ? spiders.filter(s => s.type === contentKind)
        : spiders;

    return (
        <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8, ...style }}>
            <Space size={12} wrap align="center">
                {/* 1. 搜索框 */}
                {onSearchChange && (
                    <Input
                        placeholder={searchPlaceholder}
                        allowClear
                        prefix={<SearchOutlined style={{ color: 'rgba(0,0,0,0.25)' }} />}
                        value={searchValue}
                        onChange={(event) => onSearchChange(event.target.value)}
                        style={{ width: 300, maxWidth: '80vw' }}
                    />
                )}

                {/* 2. 来源筛选 */}
                {filteredSpiders && onSourceChange && (
                    <Space size={4}>
                        <span style={{ fontSize: 14 }}>来源:</span>
                        <Select
                            value={selectedSource}
                            style={{ width: 160 }}
                            onChange={onSourceChange}
                        >
                            <Option value="">全部来源</Option>
                            {filteredSpiders.map(s => (
                                <Option key={s.name} value={s.source_site || s.display_name || s.name}>
                                    {s.display_name || s.source_site || s.name}
                                </Option>
                            ))}
                        </Select>
                    </Space>
                )}

                {/* 3. 导出按钮 */}
                {onExport && (
                    <Button icon={<DownloadOutlined />} onClick={onExport}>导出</Button>
                )}

                {/* 4. 额外操作 (插槽) */}
                {children}
            </Space>

            {/* 5. 刷新按钮 (靠右) */}
            <Space>
                {onRefresh && (
                    <Button icon={<ReloadOutlined />} onClick={onRefresh} loading={loading}>刷新</Button>
                )}
            </Space>
        </div>
    );
};

export default NewsToolbar;
