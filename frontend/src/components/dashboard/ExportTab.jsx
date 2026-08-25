import React from 'react';
import PropTypes from 'prop-types';
import { Alert, Button, List, Space, Tag } from 'antd';
import { useExportDelivery } from '../../hooks/dashboard/useExportDelivery';
import { useExportItems } from '../../hooks/dashboard/useExportItems';
import { useSelectionSet } from '../../hooks/dashboard/useSelectionSet';
import ExportFiltersPanel from './ExportFiltersPanel';
import ExportItemsTable from './ExportItemsTable';
import ExportSelectionToolbar from './ExportSelectionToolbar';

const ExportTab = ({ manuallyFeatured, setManuallyFeatured, contentKind }) => {
    const {
        exportTimeRange,
        exportMinScore,
        visibleItems,
        loading,
        setExportTimeRange,
        setExportMinScore,
        loadItems,
    } = useExportItems(contentKind, manuallyFeatured);
    const {
        selectedIds,
        setSelectedIds,
        clearSelection,
        toggleSelectAll,
        invertSelection,
    } = useSelectionSet(visibleItems);
    const {
        sendingToTg,
        triggeringDaily,
        copyPlainText,
        copyMarkdown,
        copyTelegramHtml,
        sendToTelegram,
        triggerDailyDelivery,
        pendingOperations,
        retryPendingOperation,
    } = useExportDelivery(contentKind, visibleItems, selectedIds);

    return (
        <div style={{ padding: '0 10px' }}>
            <ExportFiltersPanel
                exportTimeRange={exportTimeRange}
                exportMinScore={exportMinScore}
                loading={loading}
                setExportTimeRange={setExportTimeRange}
                setExportMinScore={setExportMinScore}
                loadItems={loadItems}
                triggerDailyDelivery={triggerDailyDelivery}
                triggeringDaily={triggeringDaily}
            />
            {pendingOperations.length > 0 && (
                <Alert
                    style={{ marginBottom: 16 }}
                    type="warning"
                    showIcon
                    title="存在未完成的交付任务"
                    description={(
                        <List
                            size="small"
                            dataSource={pendingOperations}
                            renderItem={(operation) => (
                                <List.Item
                                    actions={[
                                        <Button key="retry" size="small" onClick={() => retryPendingOperation(operation.operation_key)}>
                                            恢复发送
                                        </Button>,
                                    ]}
                                >
                                    <Space wrap>
                                        <code>{operation.operation_key}</code>
                                        <Tag>{operation.status}</Tag>
                                        <span>{operation.sent_parts}/{operation.parts} 段已送达</span>
                                    </Space>
                                </List.Item>
                            )}
                        />
                    )}
                />
            )}
            <ExportSelectionToolbar
                visibleCount={visibleItems.length}
                selectedCount={selectedIds.length}
                sendingToTg={sendingToTg}
                clearSelection={clearSelection}
                toggleSelectAll={toggleSelectAll}
                invertSelection={invertSelection}
                copyPlainText={copyPlainText}
                copyMarkdown={copyMarkdown}
                copyTelegramHtml={copyTelegramHtml}
                sendToTelegram={sendToTelegram}
            />
            <ExportItemsTable
                visibleItems={visibleItems}
                loading={loading}
                selectedIds={selectedIds}
                setSelectedIds={setSelectedIds}
                onRemoveFeatured={(outputKey) => {
                    setManuallyFeatured((items) => items.filter((item) => item.outputKey !== outputKey));
                    setSelectedIds((keys) => keys.filter((key) => key !== outputKey));
                }}
            />
        </div>
    );
};

ExportTab.propTypes = {
    manuallyFeatured: PropTypes.arrayOf(PropTypes.object),
    setManuallyFeatured: PropTypes.func,
    contentKind: PropTypes.string,
};

export default ExportTab;
