import React, { useEffect, useRef } from 'react';
import PropTypes from 'prop-types';
import { Alert, Button, Table } from 'antd';

import NewsExpandedView from './NewsExpandedView';
import NewsToolbar from './NewsToolbar';

export default function ContentDataTable({
    listState,
    columns,
    spiders,
    contentKind,
    exportScope,
    onShowExport,
    toolbarChildren,
    showSourceFilter = true,
    searchPlaceholder,
    size,
    wrapperStyle,
    rowSelection,
}) {
    const {
        items,
        loading,
        loaded,
        error,
        stale,
        pagination,
        filterSource,
        filterKeyword,
        setFilterSource,
        setFilterKeyword,
        fetchItems,
    } = listState;
    const searchTimerRef = useRef(null);
    const queryRef = useRef({ source: filterSource, keyword: filterKeyword });

    useEffect(() => {
        queryRef.current = { source: filterSource, keyword: filterKeyword };
    }, [filterKeyword, filterSource]);

    const currentSource = showSourceFilter ? filterSource : undefined;

    useEffect(() => () => {
        if (searchTimerRef.current) window.clearTimeout(searchTimerRef.current);
    }, [contentKind]);

    const handleSearchChange = (value) => {
        queryRef.current = { ...queryRef.current, keyword: value };
        setFilterKeyword(value);
        if (searchTimerRef.current) window.clearTimeout(searchTimerRef.current);
        searchTimerRef.current = window.setTimeout(() => {
            const query = queryRef.current;
            fetchItems(1, pagination.pageSize, query.source, query.keyword);
        }, 500);
    };

    const handleSourceChange = showSourceFilter && setFilterSource
        ? (value) => {
            const nextSource = value || undefined;
            if (searchTimerRef.current) window.clearTimeout(searchTimerRef.current);
            queryRef.current = { ...queryRef.current, source: nextSource };
            setFilterSource(nextSource);
            fetchItems(1, pagination.pageSize, nextSource, queryRef.current.keyword);
        }
        : undefined;

    const handleRefresh = () => {
        if (searchTimerRef.current) window.clearTimeout(searchTimerRef.current);
        const query = queryRef.current;
        fetchItems(pagination.current, pagination.pageSize, query.source, query.keyword);
    };

    const handlePageChange = (page, pageSize) => {
        if (searchTimerRef.current) window.clearTimeout(searchTimerRef.current);
        const query = queryRef.current;
        fetchItems(page, pageSize, query.source, query.keyword);
    };
    const responsiveColumns = columns.map((column) => {
        if (column.title === '操作') return { ...column, fixed: 'right' };
        if (column.title === '标题' && !column.width) {
            return { ...column, width: 320, ellipsis: true };
        }
        return column;
    });
    const paginationConfig = {
        current: pagination.current,
        pageSize: pagination.pageSize || 10,
        total: pagination.total,
        showSizeChanger: true,
        showTotal: (total) => `共 ${total} 条`,
        pageSizeOptions: ['10', '20', '50', '100'],
        onChange: handlePageChange,
        onShowSizeChange: (_, pageSize) => handlePageChange(1, pageSize),
    };

    return (
        <div style={wrapperStyle}>
            <NewsToolbar
                searchValue={filterKeyword}
                onSearchChange={handleSearchChange}
                searchPlaceholder={searchPlaceholder}
                spiders={showSourceFilter ? spiders : undefined}
                selectedSource={currentSource}
                onSourceChange={handleSourceChange}
                contentKind={contentKind}
                onExport={exportScope && onShowExport ? () => onShowExport(exportScope) : undefined}
                onRefresh={handleRefresh}
                loading={loading}
            >
                {toolbarChildren}
            </NewsToolbar>

            {error && (
                <Alert
                    type={stale ? 'warning' : 'error'}
                    showIcon
                    message={stale ? '刷新失败，当前显示上次成功的内容' : '内容加载失败'}
                    description={error}
                    action={<Button size="small" onClick={handleRefresh}>重试</Button>}
                    style={{ marginBottom: 16 }}
                />
            )}

            <Table
                className="admin-data-table"
                columns={responsiveColumns}
                dataSource={items}
                rowKey="id"
                loading={loading}
                locale={{ emptyText: !loaded && error ? '加载失败，请重试' : '暂无数据' }}
                pagination={paginationConfig}
                size={size}
                scroll={{ x: 'max-content' }}
                rowSelection={rowSelection}
                expandable={{
                    expandedRowRender: (record) => <NewsExpandedView record={record} />,
                    rowExpandable: () => true,
                }}
            />
        </div>
    );
}

ContentDataTable.propTypes = {
    listState: PropTypes.shape({
        items: PropTypes.array,
        loading: PropTypes.bool,
        loaded: PropTypes.bool,
        error: PropTypes.string,
        stale: PropTypes.bool,
        pagination: PropTypes.object,
        filterSource: PropTypes.string,
        filterKeyword: PropTypes.string,
        setFilterSource: PropTypes.func,
        setFilterKeyword: PropTypes.func,
        fetchItems: PropTypes.func,
    }).isRequired,
    columns: PropTypes.arrayOf(PropTypes.object).isRequired,
    spiders: PropTypes.arrayOf(PropTypes.object),
    contentKind: PropTypes.string,
    exportScope: PropTypes.string,
    onShowExport: PropTypes.func,
    toolbarChildren: PropTypes.node,
    showSourceFilter: PropTypes.bool,
    searchPlaceholder: PropTypes.string,
    size: PropTypes.string,
    wrapperStyle: PropTypes.object,
    rowSelection: PropTypes.object,
};
