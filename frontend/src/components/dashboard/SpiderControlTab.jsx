import React from 'react';
import PropTypes from 'prop-types';
import { Alert, Row } from 'antd';
import ScraperCard from './ScraperCard';
import RssSourceManager from './RssSourceManager';

/**
 * 爬虫控制Tab组件
 * 用于管理所有爬虫的运行状态和配置
 * Updated: Force Refresh
 */
const SpiderControlTab = ({
    spiders,
    spiderStatus,
    rssSources,
    runtimeError,
    onRetryRuntime,
    onRun,
    onCancel,
    onConfigChange,
    onCreateRssSource,
    onUpdateRssSource,
    onDeleteRssSource,
    contentKind,
}) => {
    const filteredSpiders = spiders.filter(spider => {
        if (typeof spider === 'object' && spider.type) {
            return spider.type === contentKind;
        }
        return contentKind === 'news';
    });

    return (
        <div style={{ padding: '0 10px' }}>
            {runtimeError && (
                <Alert
                    type="error"
                    showIcon
                    title="无法读取爬虫运行状态"
                    description={runtimeError}
                    action={<button type="button" onClick={onRetryRuntime}>重试</button>}
                    style={{ marginBottom: 16 }}
                />
            )}
            <RssSourceManager
                sources={rssSources}
                contentKind={contentKind}
                onCreate={onCreateRssSource}
                onUpdate={onUpdateRssSource}
                onDelete={onDeleteRssSource}
            />
            <Row gutter={[16, 16]}>
                {filteredSpiders.map(spider => {
                    const spiderName = typeof spider === 'object' ? spider.name : spider;
                    return (
                        <ScraperCard
                            key={spiderName}
                            name={spiderName}
                            displayName={spider.display_name || spider.source_site || spiderName}
                            contentKind={spider.type || contentKind}
                            status={spiderStatus[spiderName] || {}}
                            onRun={onRun}
                            onCancel={onCancel}
                            onConfigChange={onConfigChange}
                        />
                    );
                })}
            </Row>
        </div>
    );
};

SpiderControlTab.propTypes = {
    spiders: PropTypes.arrayOf(PropTypes.object).isRequired,
    spiderStatus: PropTypes.object.isRequired,
    rssSources: PropTypes.arrayOf(PropTypes.object).isRequired,
    runtimeError: PropTypes.string,
    onRetryRuntime: PropTypes.func.isRequired,
    onRun: PropTypes.func.isRequired,
    onCancel: PropTypes.func.isRequired,
    onConfigChange: PropTypes.func.isRequired,
    onCreateRssSource: PropTypes.func.isRequired,
    onUpdateRssSource: PropTypes.func.isRequired,
    onDeleteRssSource: PropTypes.func.isRequired,
    contentKind: PropTypes.string.isRequired,
};

export default SpiderControlTab;
