import React from 'react';
import PropTypes from 'prop-types';
import { Card, Select, Button, Space } from 'antd';

import TimeRangeSelect from './TimeRangeSelect';

const { Option } = Select;

export default function ExportFiltersPanel({
    exportTimeRange,
    exportMinScore,
    loading,
    setExportTimeRange,
    setExportMinScore,
    loadItems,
    triggerDailyDelivery,
    triggeringDaily,
}) {
    return (
        <Card style={{ marginBottom: 16 }}>
            <Space size="large" wrap className="export-filter-actions">
                <div>
                    <span style={{ marginRight: 8 }}>时间范围:</span>
                    <TimeRangeSelect value={exportTimeRange} onChange={setExportTimeRange} />
                </div>
                <div>
                    <span style={{ marginRight: 8 }}>最低评分:</span>
                    <Select value={exportMinScore} style={{ width: 100 }} onChange={setExportMinScore}>
                        <Option value={4}>≥ 4分</Option>
                        <Option value={5}>≥ 5分</Option>
                        <Option value={6}>≥ 6分</Option>
                        <Option value={7}>≥ 7分</Option>
                        <Option value={8}>≥ 8分</Option>
                        <Option value={9}>≥ 9分</Option>
                    </Select>
                </div>
                <Button type="primary" onClick={loadItems} loading={loading}>
                    加载内容
                </Button>
                <Button onClick={triggerDailyDelivery} loading={triggeringDaily}>
                    触发日报推送
                </Button>
            </Space>
        </Card>
    );
}

ExportFiltersPanel.propTypes = {
    exportTimeRange: PropTypes.number.isRequired,
    exportMinScore: PropTypes.number.isRequired,
    loading: PropTypes.bool.isRequired,
    setExportTimeRange: PropTypes.func.isRequired,
    setExportMinScore: PropTypes.func.isRequired,
    loadItems: PropTypes.func.isRequired,
    triggerDailyDelivery: PropTypes.func.isRequired,
    triggeringDaily: PropTypes.bool.isRequired,
};
